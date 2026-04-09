#!/usr/bin/env python3
"""
Hermes Scale Worker

Pulls messages from Redis queues, processes them through AIAgent,
saves results to Postgres, and pushes responses back to Redis.

Stateless — reads everything from Postgres, processes one message,
writes back, moves on. Run as many workers as you need.

Usage:
    python scale/worker.py
    python scale/worker.py --workers 4  # multiprocess mode

Env vars:
    DATABASE_URL   postgresql://hermes:pass@localhost:5432/hermes
    REDIS_URL      redis://localhost:6379
"""

import asyncio
import json
import logging
import os
import signal
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import asyncpg
import redis.asyncio as aioredis

# Add hermes to path so we can import AIAgent
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [worker] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("hermes.worker")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def generate_session_id() -> str:
    """Generate timestamped session ID matching Hermes format."""
    now = datetime.now()
    short_uuid = uuid.uuid4().hex[:8]
    return f"{now.strftime('%Y%m%d_%H%M%S')}_{short_uuid}"


def build_session_key(
    platform: str, chat_id: str, user_id: str = None, chat_type: str = "dm"
) -> str:
    """Deterministic session key — same logic as Hermes gateway."""
    if chat_type in ("group", "supergroup") and user_id:
        return f"{platform}:{chat_id}:{user_id}"
    return f"{platform}:{chat_id}"


def should_reset(session: dict) -> bool:
    """Check if session should auto-reset based on policy."""
    mode = session.get("reset_mode", "both")
    if mode == "none":
        return False

    updated = session["updated_at"]
    now = datetime.now(updated.tzinfo or timezone.utc)

    if mode in ("idle", "both"):
        idle_minutes = session.get("reset_idle_minutes", 1440)
        if now - updated > timedelta(minutes=idle_minutes):
            return True

    if mode in ("daily", "both"):
        at_hour = session.get("reset_at_hour", 4)
        today_reset = now.replace(hour=at_hour, minute=0, second=0, microsecond=0)
        if updated < today_reset <= now:
            return True

    return False


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class HermesWorker:
    """Single worker process that pulls from Redis and runs AIAgent."""

    def __init__(self, worker_id: int = 0):
        self.worker_id = worker_id
        self.db: Optional[asyncpg.Pool] = None
        self.redis: Optional[aioredis.Redis] = None
        self.running = True
        self._messages_processed = 0
        self._errors = 0

    async def start(self):
        """Connect to Postgres and Redis, then enter the main loop."""
        database_url = os.getenv("DATABASE_URL", "postgresql://hermes:hermes@localhost:5432/hermes")
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

        self.db = await asyncpg.create_pool(database_url, min_size=2, max_size=5)
        self.redis = aioredis.from_url(redis_url, decode_responses=True)

        logger.info("Worker %d started — Postgres ✓  Redis ✓", self.worker_id)

        # Graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._shutdown)

        await self._main_loop()

    def _shutdown(self):
        logger.info("Worker %d shutting down (processed %d msgs, %d errors)",
                     self.worker_id, self._messages_processed, self._errors)
        self.running = False

    async def _main_loop(self):
        """Pull messages from all tenant queues, round-robin."""
        while self.running:
            try:
                # Get all active tenant IDs
                tenant_ids = [
                    str(r["id"])
                    for r in await self.db.fetch("SELECT id FROM tenants WHERE active = true")
                ]
                if not tenant_ids:
                    await asyncio.sleep(2)
                    continue

                # Build queue list for BRPOP
                queues = [f"hermes:queue:{tid}" for tid in tenant_ids]

                # Block up to 5 seconds waiting for a message
                result = await self.redis.brpop(queues, timeout=5)
                if result is None:
                    continue

                queue_name, data = result
                msg = json.loads(data)
                await self._process_message(msg)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Worker %d main loop error: %s", self.worker_id, e, exc_info=True)
                self._errors += 1
                await asyncio.sleep(1)

        # Cleanup
        if self.db:
            await self.db.close()
        if self.redis:
            await self.redis.close()

    async def _process_message(self, msg: dict):
        """Process a single inbound message."""
        tenant_id = msg["tenant_id"]
        platform = msg["platform"]
        chat_id = msg["chat_id"]
        user_id = msg.get("user_id")
        user_message = msg["text"]
        chat_type = msg.get("chat_type", "dm")

        # 1. Build session key
        session_key = build_session_key(platform, chat_id, user_id, chat_type)
        logger.info("Processing: tenant=%s session=%s msg=%s...",
                     tenant_id[:8], session_key, user_message[:50])

        # 2. Acquire session lock (prevent concurrent processing of same conversation)
        lock_key = f"hermes:lock:{session_key}"
        lock_acquired = await self.redis.set(lock_key, str(self.worker_id), nx=True, ex=120)
        if not lock_acquired:
            # Another worker is on it — requeue with small delay
            logger.debug("Session %s locked, requeueing", session_key)
            await asyncio.sleep(0.5)
            await self.redis.lpush(f"hermes:queue:{tenant_id}", json.dumps(msg))
            return

        try:
            # 3. Load tenant config
            tenant = await self.db.fetchrow("SELECT * FROM tenants WHERE id = $1", uuid.UUID(tenant_id))
            if not tenant:
                logger.error("Tenant %s not found, dropping message", tenant_id)
                return

            # 4. Load or create session
            session = await self.db.fetchrow(
                "SELECT * FROM sessions WHERE session_key = $1", session_key
            )

            if session is None:
                session_id = generate_session_id()
                conversation_history = []
                system_prompt = None
            else:
                session = dict(session)
                session_id = session["session_id"]
                conversation_history = json.loads(session["conversation_history"] or "[]")
                system_prompt = session.get("system_prompt")

                if should_reset(session):
                    logger.info("Session %s reset (policy: %s)", session_key, session.get("reset_mode"))
                    session_id = generate_session_id()
                    conversation_history = []
                    system_prompt = None

            # 5. Build system prompt from tenant config + memory
            if system_prompt is None:
                memories = await self.db.fetch(
                    "SELECT memory_type, content FROM tenant_memory WHERE tenant_id = $1",
                    uuid.UUID(tenant_id),
                )
                memory_text = "\n\n".join(
                    f"## {m['memory_type']}\n{m['content']}" for m in memories
                )
                template = tenant["system_prompt_template"]
                if template:
                    base_prompt = template
                else:
                    base_prompt = (
                        f"You are a helpful AI assistant for {tenant['name']}. "
                        f"Help customers with their questions."
                    )
                system_prompt = base_prompt
                if memory_text:
                    system_prompt += f"\n\n{memory_text}"

            # 6. Initialize AIAgent
            from run_agent import AIAgent

            model = tenant["model"] or "openrouter/google/gemini-2.0-flash-exp:free"
            # Strip openrouter/ prefix — we set provider/base_url explicitly
            or_model = model[len("openrouter/"):] if model.startswith("openrouter/") else model
            or_key = os.getenv("OPENROUTER_API_KEY", "")

            agent = AIAgent(
                model=or_model,
                api_key=or_key,
                base_url="https://openrouter.ai/api/v1",
                provider="openrouter",
                max_iterations=tenant["max_turns"] or 90,
                quiet_mode=True,
                ephemeral_system_prompt=system_prompt,
                session_id=session_id,
                platform=platform,
                enabled_toolsets=list(tenant["enabled_toolsets"] or ["web", "search", "image_gen", "booking"]),
                skip_memory=False,
                skip_context_files=True,
            )

            # 7. Run conversation
            start_time = time.time()
            result = agent.run_conversation(
                user_message=user_message,
                conversation_history=conversation_history,
            )
            duration_ms = int((time.time() - start_time) * 1000)

            final_response = result.get("final_response", "Sorry, I couldn't process that.")
            new_history = json.dumps(result.get("messages", []))
            input_tokens = result.get("input_tokens", 0) or 0
            output_tokens = result.get("output_tokens", 0) or 0
            total_tokens = input_tokens + output_tokens
            cost_usd = result.get("estimated_cost_usd", 0) or 0

            # 8. Save session to Postgres (upsert)
            await self.db.execute("""
                INSERT INTO sessions (
                    session_key, tenant_id, session_id, platform,
                    chat_id, user_id, chat_type, system_prompt,
                    conversation_history, total_tokens,
                    last_prompt_tokens, last_completion_tokens, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, now())
                ON CONFLICT (session_key) DO UPDATE SET
                    session_id = $3,
                    conversation_history = $9,
                    system_prompt = $8,
                    total_tokens = sessions.total_tokens + $10,
                    last_prompt_tokens = $11,
                    last_completion_tokens = $12,
                    updated_at = now()
            """,
                session_key, uuid.UUID(tenant_id), session_id, platform,
                chat_id, user_id, chat_type, system_prompt,
                new_history, total_tokens, input_tokens, output_tokens,
            )

            # 9. Log for billing
            await self.db.execute("""
                INSERT INTO message_log (
                    tenant_id, session_key, direction, platform,
                    user_id, message_text, response_text,
                    input_tokens, output_tokens, cost_usd, duration_ms
                ) VALUES ($1, $2, 'inbound', $3, $4, $5, $6, $7, $8, $9, $10)
            """,
                uuid.UUID(tenant_id), session_key, platform, user_id,
                user_message, final_response,
                input_tokens, output_tokens, cost_usd, duration_ms,
            )

            # 10. Push response back to gateway
            await self.redis.lpush("hermes:responses", json.dumps({
                "tenant_id": tenant_id,
                "platform": platform,
                "chat_id": chat_id,
                "message_id": msg.get("message_id"),
                "response": final_response,
            }))

            self._messages_processed += 1
            logger.info(
                "Done: session=%s tokens=%d cost=$%.4f time=%dms",
                session_key, total_tokens, cost_usd, duration_ms,
            )

        except Exception as e:
            logger.error("Error processing message: %s", e, exc_info=True)
            self._errors += 1

            # Push error response so user isn't left hanging
            await self.redis.lpush("hermes:responses", json.dumps({
                "tenant_id": tenant_id,
                "platform": platform,
                "chat_id": chat_id,
                "message_id": msg.get("message_id"),
                "response": "Sorry, something went wrong. Please try again in a moment.",
            }))

        finally:
            await self.redis.delete(lock_key)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    worker = HermesWorker(worker_id=int(os.getenv("WORKER_ID", "0")))
    await worker.start()


if __name__ == "__main__":
    asyncio.run(main())
