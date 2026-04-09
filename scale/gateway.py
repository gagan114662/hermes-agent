#!/usr/bin/env python3
"""
Hermes Scale Gateway

FastAPI app that:
- Polls Telegram for all active tenant bots (one asyncio task per bot)
- Pushes inbound messages to per-tenant Redis queues
- Listens for worker responses on Redis and sends replies back

Usage:
    uvicorn scale.gateway:app --host 0.0.0.0 --port 8443
    # or directly:
    python scale/gateway.py

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
from contextlib import asynccontextmanager
from typing import Dict, Optional

import asyncpg
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [gateway] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("hermes.gateway")

# Try to import python-telegram-bot
try:
    from telegram import Bot, Update
    from telegram.error import TelegramError
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False
    logger.warning("python-telegram-bot not installed — Telegram polling disabled")


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

db_pool: Optional[asyncpg.Pool] = None
redis_client: Optional[aioredis.Redis] = None

# tenant_id -> Bot instance
tenant_bots: Dict[str, "Bot"] = {}

# tenant_id -> asyncio.Task (polling task)
polling_tasks: Dict[str, asyncio.Task] = {}

# bot_token -> tenant_id (reverse lookup)
token_to_tenant: Dict[str, str] = {}

# chat_id -> asyncio.Task (typing indicator tasks)
typing_tasks: Dict[str, asyncio.Task] = {}

# Track message stats
stats = {"messages_in": 0, "messages_out": 0, "errors": 0, "started_at": None}


# ---------------------------------------------------------------------------
# Telegram Polling
# ---------------------------------------------------------------------------

async def _send_typing_loop(bot: Bot, chat_id: int):
    """Send typing action every 4s until cancelled."""
    try:
        while True:
            await bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass
    except Exception:
        pass


async def poll_telegram(tenant_id: str, bot: Bot, tenant_name: str):
    """Long-poll Telegram for updates, push to Redis queue."""
    # Persist offset in Redis so restarts don't replay old messages
    offset_key = f"hermes:offset:{tenant_id}"
    stored = await redis_client.get(offset_key)
    offset = int(stored) if stored else 0
    logger.info("Polling started for tenant %s (%s) offset=%d", tenant_name, tenant_id[:8], offset)

    while True:
        try:
            updates = await bot.get_updates(offset=offset, timeout=30, allowed_updates=["message"])
            for update in updates:
                if update.message and update.message.text:
                    msg = {
                        "tenant_id": tenant_id,
                        "platform": "telegram",
                        "chat_id": str(update.message.chat_id),
                        "user_id": str(update.message.from_user.id) if update.message.from_user else None,
                        "user_name": (
                            update.message.from_user.first_name
                            if update.message.from_user else "Unknown"
                        ),
                        "chat_type": update.message.chat.type,
                        "text": update.message.text,
                        "message_id": str(update.message.message_id),
                        "timestamp": time.time(),
                    }
                    await redis_client.lpush(
                        f"hermes:queue:{tenant_id}",
                        json.dumps(msg),
                    )
                    stats["messages_in"] += 1

                    # Start typing indicator — cancelled when response is sent
                    typing_key = f"{tenant_id}:{msg['chat_id']}"
                    if typing_key in typing_tasks and not typing_tasks[typing_key].done():
                        typing_tasks[typing_key].cancel()
                    typing_tasks[typing_key] = asyncio.create_task(
                        _send_typing_loop(bot, int(msg["chat_id"]))
                    )

                    logger.info(
                        "Queued: tenant=%s user=%s msg=%s...",
                        tenant_name, msg["user_name"], msg["text"][:40],
                    )
                offset = update.update_id + 1
                await redis_client.set(offset_key, offset)

        except asyncio.CancelledError:
            logger.info("Polling cancelled for %s", tenant_name)
            return
        except TelegramError as e:
            logger.error("Telegram error for %s: %s", tenant_name, e)
            await asyncio.sleep(5)
        except Exception as e:
            logger.error("Poll error for %s: %s", tenant_name, e, exc_info=True)
            stats["errors"] += 1
            await asyncio.sleep(5)


# ---------------------------------------------------------------------------
# Response Listener
# ---------------------------------------------------------------------------

async def response_listener():
    """Listen for worker responses on Redis and send back via Telegram."""
    logger.info("Response listener started")
    while True:
        try:
            result = await redis_client.brpop("hermes:responses", timeout=5)
            if result is None:
                continue

            _, data = result
            resp = json.loads(data)

            tenant_id = resp["tenant_id"]
            platform = resp.get("platform", "telegram")
            chat_id = resp["chat_id"]
            response_text = resp.get("response")
            message_id = resp.get("message_id")

            if not response_text:
                logger.warning("Empty/None response for chat %s — worker error, skipping send", chat_id)
                continue

            if platform == "telegram":
                bot = tenant_bots.get(tenant_id)
                if bot:
                    # Stop typing indicator
                    typing_key = f"{tenant_id}:{chat_id}"
                    if typing_key in typing_tasks and not typing_tasks[typing_key].done():
                        typing_tasks[typing_key].cancel()

                    # Split long messages (Telegram limit: 4096 chars)
                    chunks = _split_message(response_text, 4096)
                    for i, chunk in enumerate(chunks):
                        kwargs = {"chat_id": int(chat_id), "text": chunk}
                        if i == 0 and message_id:
                            kwargs["reply_to_message_id"] = int(message_id)
                        await bot.send_message(**kwargs)
                    stats["messages_out"] += 1
                else:
                    logger.error("No bot for tenant %s", tenant_id[:8])

        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error("Response listener error: %s", e, exc_info=True)
            stats["errors"] += 1
            await asyncio.sleep(1)


def _split_message(text: str, max_len: int = 4096) -> list:
    """Split a message into chunks that fit Telegram's limit."""
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        # Try to split at newline
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


# ---------------------------------------------------------------------------
# Tenant Loading
# ---------------------------------------------------------------------------

async def load_tenants():
    """Load all active tenants from Postgres and start polling."""
    rows = await db_pool.fetch("""
        SELECT t.id, t.name, t.slug, tp.platform, tp.bot_token
        FROM tenants t
        JOIN tenant_platforms tp ON tp.tenant_id = t.id
        WHERE t.active = true AND tp.enabled = true
    """)

    loaded = 0
    for row in rows:
        tenant_id = str(row["id"])
        platform = row["platform"]
        bot_token = row["bot_token"]
        tenant_name = row["name"]

        token_to_tenant[bot_token] = tenant_id

        if platform == "telegram" and HAS_TELEGRAM:
            if tenant_id not in polling_tasks:
                bot = Bot(token=bot_token)
                tenant_bots[tenant_id] = bot
                task = asyncio.create_task(
                    poll_telegram(tenant_id, bot, tenant_name)
                )
                polling_tasks[tenant_id] = task
                loaded += 1

    logger.info("Loaded %d tenant bots (%d total active)", loaded, len(rows))
    return loaded


async def refresh_tenants():
    """Periodically check for new/updated tenants (hot reload)."""
    while True:
        try:
            await asyncio.sleep(60)  # Check every minute
            await load_tenants()
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error("Tenant refresh error: %s", e)


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown."""
    global db_pool, redis_client

    database_url = os.getenv("DATABASE_URL", "postgresql://hermes:hermes@localhost:5432/hermes")
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

    db_pool = await asyncpg.create_pool(database_url, min_size=2, max_size=10)
    redis_client = aioredis.from_url(redis_url, decode_responses=True)

    logger.info("Gateway starting — Postgres ✓  Redis ✓")
    stats["started_at"] = time.time()

    # Load tenants and start polling
    await load_tenants()

    # Background tasks
    response_task = asyncio.create_task(response_listener())
    refresh_task = asyncio.create_task(refresh_tenants())

    yield

    # Shutdown
    logger.info("Gateway shutting down...")
    response_task.cancel()
    refresh_task.cancel()
    for tid, task in polling_tasks.items():
        task.cancel()
    await db_pool.close()
    await redis_client.close()


app = FastAPI(title="Hermes Scale Gateway", lifespan=lifespan)


@app.get("/health")
async def health():
    """Health check — verify Postgres, Redis, and polling tasks."""
    checks = {}

    # Postgres
    try:
        await db_pool.fetchval("SELECT 1")
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {e}"

    # Redis
    try:
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    # Polling tasks
    active_polls = sum(1 for t in polling_tasks.values() if not t.done())
    checks["polling_tasks"] = f"{active_polls} active"

    # Queue depths
    queue_depths = {}
    for tid in tenant_bots:
        depth = await redis_client.llen(f"hermes:queue:{tid}")
        if depth > 0:
            queue_depths[tid[:8]] = depth
    checks["queues"] = queue_depths if queue_depths else "all empty"

    # Stats
    uptime = time.time() - stats["started_at"] if stats["started_at"] else 0
    checks["stats"] = {
        "messages_in": stats["messages_in"],
        "messages_out": stats["messages_out"],
        "errors": stats["errors"],
        "uptime_hours": round(uptime / 3600, 1),
    }

    healthy = checks["postgres"] == "ok" and checks["redis"] == "ok"
    return JSONResponse(
        status_code=200 if healthy else 503,
        content=checks,
    )


@app.get("/tenants")
async def list_tenants():
    """List all active tenants and their status."""
    rows = await db_pool.fetch("""
        SELECT t.id, t.name, t.slug, t.active, t.model,
               count(tp.id) as platform_count
        FROM tenants t
        LEFT JOIN tenant_platforms tp ON tp.tenant_id = t.id AND tp.enabled = true
        GROUP BY t.id
        ORDER BY t.created_at
    """)
    return [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "slug": r["slug"],
            "active": r["active"],
            "model": r["model"],
            "platforms": r["platform_count"],
            "polling": str(r["id"]) in polling_tasks and not polling_tasks[str(r["id"])].done(),
        }
        for r in rows
    ]


@app.post("/mailbox/inbound")
async def mailbox_inbound(request: Request):
    """
    Mailgun webhook for inbound emails to worker addresses.
    Routes the email into the worker's Redis queue as a regular message.
    """
    form = await request.form()
    recipient = form.get("recipient", "")  # e.g. marco-marios-pizza@hermes-worker.com
    sender = form.get("sender", "")
    subject = form.get("subject", "")
    body = form.get("body-plain", "") or form.get("body-html", "")

    if not recipient:
        return JSONResponse(status_code=400, content={"ok": False, "error": "missing recipient"})

    # Look up tenant by worker_email
    tenant = await db_pool.fetchrow(
        "SELECT id, name FROM tenants WHERE worker_email = $1 AND active = true",
        recipient,
    )
    if not tenant:
        logger.warning("Inbound email to unknown address: %s", recipient)
        return JSONResponse(status_code=200, content={"ok": False, "error": "unknown recipient"})

    tenant_id = str(tenant["id"])
    message_text = f"Email from {sender}\nSubject: {subject}\n\n{body}"

    await redis_client.lpush(f"hermes:queue:{tenant_id}", json.dumps({
        "tenant_id": tenant_id,
        "platform": "email",
        "chat_id": sender,   # reply-to address acts as the "chat"
        "user_id": sender,
        "user_name": sender.split("@")[0],
        "chat_type": "dm",
        "text": message_text,
        "message_id": None,
        "timestamp": __import__("time").time(),
    }))

    logger.info("Inbound email queued: tenant=%s from=%s subject=%s", tenant["name"], sender, subject[:50])
    return {"ok": True}


@app.get("/stats/{tenant_slug}")
async def tenant_stats(tenant_slug: str):
    """Get message stats for a specific tenant."""
    tenant = await db_pool.fetchrow("SELECT id, name FROM tenants WHERE slug = $1", tenant_slug)
    if not tenant:
        raise HTTPException(404, "Tenant not found")

    tid = tenant["id"]

    # Message counts
    counts = await db_pool.fetchrow("""
        SELECT
            count(*) as total_messages,
            sum(input_tokens) as total_input_tokens,
            sum(output_tokens) as total_output_tokens,
            sum(cost_usd) as total_cost,
            avg(duration_ms) as avg_duration_ms,
            count(*) FILTER (WHERE created_at > now() - interval '24 hours') as messages_24h
        FROM message_log WHERE tenant_id = $1
    """, tid)

    session_count = await db_pool.fetchval(
        "SELECT count(*) FROM sessions WHERE tenant_id = $1", tid
    )

    return {
        "tenant": tenant["name"],
        "sessions": session_count,
        "total_messages": counts["total_messages"],
        "messages_24h": counts["messages_24h"],
        "total_tokens": (counts["total_input_tokens"] or 0) + (counts["total_output_tokens"] or 0),
        "total_cost_usd": round(float(counts["total_cost"] or 0), 4),
        "avg_response_ms": round(float(counts["avg_duration_ms"] or 0)),
    }


# ---------------------------------------------------------------------------
# Direct run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("GATEWAY_PORT", "8443"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
