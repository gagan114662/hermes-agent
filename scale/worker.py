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
        """Connect to Postgres and Redis, then run message + autonomous loops."""
        database_url = os.getenv("DATABASE_URL", "postgresql://hermes:hermes@localhost:5432/hermes")
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

        self.db = await asyncpg.create_pool(database_url, min_size=2, max_size=5)
        self.redis = aioredis.from_url(redis_url, decode_responses=True)

        logger.info("Worker %d started — Postgres ✓  Redis ✓", self.worker_id)

        # Graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._shutdown)

        logger.info("Worker %d: _message_loop started", self.worker_id)
        logger.info("Worker %d: _autonomous_loop started", self.worker_id)
        await asyncio.gather(
            self._main_loop(),
            self._autonomous_loop(),
            self._digest_loop(),
        )

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
                    """SELECT memory_type, content FROM tenant_memory
                       WHERE tenant_id = $1
                       ORDER BY updated_at DESC
                       LIMIT 20""",
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
# Autonomous loop — the worker's own decision engine
# ---------------------------------------------------------------------------

_DECISION_PROMPT = """You are {worker_name}, an AI {worker_role} working for {business_name}.

## Your Memory & Context
{memory}

## What You've Done Recently (last 24h)
{recent_actions}

## Current Time
{current_datetime}

## Standing Instructions from Manager
{standing_instructions}

---

What is the single most valuable action you should take RIGHT NOW?

Think like a high-performing employee who owns their results:
- Is there a lead or contact you haven't followed up on?
- Something you started that needs to continue or complete?
- Research that would meaningfully help you do your job better?
- A report or summary the manager would find valuable right now?
- Outreach or work that could directly generate results?

Respond in pure JSON only (no markdown, no explanation):
{{
  "reasoning": "why this is the highest-value action right now",
  "action": "do_work" or "rest",
  "confidence": 1-10,
  "task": "precise, specific description of exactly what to do — enough detail to execute without clarification",
  "expected_outcome": "what you will deliver when done"
}}

If confidence is below 7, set action to "rest" — it's better to do nothing than waste time on low-value work.
If it is very late at night (after midnight, before 5am), set action to "rest".
If you completed very similar work within the last 60 minutes, set action to "rest".
"""

_TASK_TYPE_PROMPT = """You are classifying a task.

Task: {task}

Classify into exactly one of these types (respond with just the type keyword, nothing else):
- lead_research   (finding leads, prospects, companies, contacts)
- content         (writing posts, articles, newsletters, copy, social media)
- outreach        (drafting emails, messages, pitches, follow-ups)
- research        (competitor analysis, market research, news monitoring, intel)
- ops             (scheduling, organizing, summarizing, reporting, admin)
- other           (anything that doesn't fit above)
"""

_GRADER_PROMPTS = {
    "lead_research": """You are grading an AI worker's lead research output.

Task given: {task}
Output produced: {output}

Score on these dimensions (each 0-25 points):
1. Quantity — how many leads/companies found vs what was asked
2. Relevance — how well do they match the stated criteria
3. Completeness — how much useful info per lead (name, company, signal, contact)
4. Actionability — can a human immediately act on this without more research

Respond in JSON only:
{{
  "quantity_score": 0,
  "relevance_score": 0,
  "completeness_score": 0,
  "actionability_score": 0,
  "total": 0,
  "best_thing": "one specific thing done well",
  "biggest_gap": "one specific thing missing or weak",
  "beat_this_next_time": "one concrete instruction for how to score higher next time"
}}""",

    "content": """You are grading an AI worker's content writing output.

Task given: {task}
Output produced: {output}

Score on these dimensions (each 0-25 points):
1. On-brief — does it match what was asked (format, topic, audience, tone)
2. Quality — is it well-written, clear, engaging, not generic
3. Specificity — specific details, examples, data — not vague filler
4. Completeness — is it a finished, usable draft or just an outline

Respond in JSON only:
{{
  "on_brief_score": 0,
  "quality_score": 0,
  "specificity_score": 0,
  "completeness_score": 0,
  "total": 0,
  "best_thing": "one specific thing done well",
  "biggest_gap": "one specific thing missing or weak",
  "beat_this_next_time": "one concrete instruction for how to score higher next time"
}}""",

    "outreach": """You are grading an AI worker's outreach draft.

Task given: {task}
Output produced: {output}

Score on these dimensions (each 0-25 points):
1. Personalization — specific to the recipient, not generic
2. Clarity — clear value prop, easy to understand in 10 seconds
3. Call to action — specific, low-friction ask
4. Tone — appropriate for the relationship and context

Respond in JSON only:
{{
  "personalization_score": 0,
  "clarity_score": 0,
  "cta_score": 0,
  "tone_score": 0,
  "total": 0,
  "best_thing": "one specific thing done well",
  "biggest_gap": "one specific thing missing or weak",
  "beat_this_next_time": "one concrete instruction for how to score higher next time"
}}""",

    "research": """You are grading an AI worker's research output.

Task given: {task}
Output produced: {output}

Score on these dimensions (each 0-25 points):
1. Depth — how thoroughly was the topic covered
2. Sources — were multiple sources used, are they credible
3. Synthesis — is raw info turned into useful insight, not just facts
4. Actionability — does it tell the reader what to DO with this information

Respond in JSON only:
{{
  "depth_score": 0,
  "sources_score": 0,
  "synthesis_score": 0,
  "actionability_score": 0,
  "total": 0,
  "best_thing": "one specific thing done well",
  "biggest_gap": "one specific thing missing or weak",
  "beat_this_next_time": "one concrete instruction for how to score higher next time"
}}""",

    "ops": """You are grading an AI worker's operations/admin output.

Task given: {task}
Output produced: {output}

Score on these dimensions (each 0-25 points):
1. Accuracy — is the information correct and complete
2. Clarity — easy to read and act on
3. Format — appropriate structure for the type of output (table, bullets, prose)
4. Time-saving — does this actually save the manager meaningful time

Respond in JSON only:
{{
  "accuracy_score": 0,
  "clarity_score": 0,
  "format_score": 0,
  "time_saving_score": 0,
  "total": 0,
  "best_thing": "one specific thing done well",
  "biggest_gap": "one specific thing missing or weak",
  "beat_this_next_time": "one concrete instruction for how to score higher next time"
}}""",

    "other": """You are grading an AI worker's output.

Task given: {task}
Output produced: {output}

Score holistically (0-100):
- Was the task completed as requested?
- Is the output high quality and usable?
- Is it specific rather than generic?
- Does it save the manager time?

Respond in JSON only:
{{
  "total": 0,
  "best_thing": "one specific thing done well",
  "biggest_gap": "one specific thing missing or weak",
  "beat_this_next_time": "one concrete instruction for how to score higher next time"
}}""",
}


async def _autonomous_loop(self):
    """
    The worker's own decision engine. Runs every 5 minutes.
    Asks the LLM what's most valuable to do right now — no cron, no templates.
    """
    while self.running:
        try:
            await asyncio.sleep(300)  # check every 5 minutes

            tenants = await self.db.fetch(
                "SELECT * FROM tenants WHERE active = true AND tenant_config IS NOT NULL"
            )
            for tenant in tenants:
                config = json.loads(tenant["tenant_config"] or "{}")
                if not config.get("manager_chat_id"):
                    continue  # not an autonomous worker tenant

                # Skip if there are human messages pending for this tenant
                pending = await self.redis.llen(f"hermes:queue:{tenant['id']}")
                if pending > 0:
                    continue  # let message loop handle humans first

                await self._run_autonomous_decision(tenant, config)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Autonomous loop error: %s", e, exc_info=True)
            await asyncio.sleep(5)


async def _run_autonomous_decision(self, tenant, config: dict):
    """Ask the LLM what to do right now, execute it, save the learning."""
    from run_agent import AIAgent

    tenant_id = tenant["id"]
    manager_chat_id = config["manager_chat_id"]

    # Load memory (paginated — LIMIT 40 to prevent context blowup)
    memories = await self.db.fetch(
        """SELECT memory_type, content FROM tenant_memory
           WHERE tenant_id = $1
           ORDER BY updated_at DESC
           LIMIT 40""",
        tenant_id,
    )
    recent_actions = await self.db.fetch(
        "SELECT summary, created_at FROM worker_actions WHERE tenant_id = $1 ORDER BY created_at DESC LIMIT 15",
        tenant_id,
    )

    memory_text = "\n\n".join(f"[{m['memory_type']}]\n{m['content']}" for m in memories) or "No memory yet."
    recent_text = "\n".join(f"- {r['summary']}" for r in recent_actions) or "No recent actions."

    or_key = os.getenv("OPENROUTER_API_KEY", "")
    model = tenant["model"] or "openrouter/google/gemini-2.5-flash-preview"
    or_model = model[len("openrouter/"):] if model.startswith("openrouter/") else model

    # Load recent scores per task type so the decision LLM knows what to beat
    score_rows = await self.db.fetch(
        """SELECT task_type, quality_score FROM worker_actions
           WHERE tenant_id = $1 AND quality_score IS NOT NULL
           ORDER BY created_at DESC LIMIT 10""",
        tenant_id,
    )
    scores_by_type: dict = {}
    for row in score_rows:
        if row["task_type"] not in scores_by_type:
            scores_by_type[row["task_type"]] = row["quality_score"]

    scores_text = ""
    if scores_by_type:
        scores_text = "\n\n## Your Recent Quality Scores (beat these)\n"
        for t, s in scores_by_type.items():
            scores_text += f"- {t}: {s}/100\n"

    # Step 1: Ask LLM what to do (no tools — pure reasoning)
    decision_agent = AIAgent(
        model=or_model,
        api_key=or_key,
        base_url="https://openrouter.ai/api/v1",
        provider="openrouter",
        max_iterations=2,
        quiet_mode=True,
        skip_memory=True,
        skip_context_files=True,
        enabled_toolsets=[],
    )
    decision_result = decision_agent.run_conversation(
        user_message=_DECISION_PROMPT.format(
            worker_name=config.get("worker_name", "Worker"),
            worker_role=config.get("worker_role", "AI Assistant"),
            business_name=tenant["name"],
            memory=memory_text + scores_text,
            recent_actions=recent_text,
            current_datetime=datetime.now().strftime("%A %B %d %Y, %I:%M %p"),
            standing_instructions=config.get("standing_instructions", "Do your best work."),
        )
    )

    raw = decision_result.get("final_response", "").strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        import re as _re
        raw = _re.sub(r"^```[a-z]*\n?", "", raw)
        raw = _re.sub(r"\n?```$", "", raw.rstrip())

    try:
        decision = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        logger.debug("Autonomous decision parse failed for tenant %s", str(tenant_id)[:8])
        return

    if decision.get("action") != "do_work":
        logger.debug("Worker %s chose to rest: %s", str(tenant_id)[:8], decision.get("reasoning", ""))
        return

    # Minimum confidence check (Fix 4)
    if decision.get("confidence", 10) < 7:
        logger.debug("Worker %s low confidence (%s), skipping", str(tenant_id)[:8], decision.get("confidence"))
        return

    task = decision.get("task", "").strip()
    if not task:
        return

    # Draft-first: never publish/send autonomously — always save to drafts (Fix 2)
    autonomous_task = (
        task + "\n\n"
        "IMPORTANT: You are running autonomously without manager supervision. "
        "Do NOT publish posts, send emails, or take any irreversible action. "
        "Instead: write drafts and save them to your drafts/ folder. "
        "Summarise what you drafted and what action the manager needs to take to publish/send it."
    )

    logger.info("Worker autonomous task [%s]: %s", str(tenant_id)[:8], task[:100])

    # Step 2: Build system prompt from tenant config + memory (same as message loop)
    template = tenant["system_prompt_template"] or f"You are an AI worker for {tenant['name']}."
    system_prompt = template
    if memory_text and memory_text != "No memory yet.":
        system_prompt += f"\n\n{memory_text}"

    # Step 3: Execute the task with full toolset
    work_agent = AIAgent(
        model=or_model,
        api_key=or_key,
        base_url="https://openrouter.ai/api/v1",
        provider="openrouter",
        max_iterations=30,
        quiet_mode=True,
        ephemeral_system_prompt=system_prompt,
        session_id=generate_session_id(),
        platform="autonomous",
        enabled_toolsets=list(tenant["enabled_toolsets"] or ["web", "file", "memory"]),
        skip_memory=False,
        skip_context_files=True,
    )
    work_result = work_agent.run_conversation(user_message=autonomous_task)
    output = work_result.get("final_response", "")

    # Step 4: Classify task type
    task_type = "other"
    if output and len(output) > 30:
        try:
            classify_agent = AIAgent(
                model=or_model, api_key=or_key,
                base_url="https://openrouter.ai/api/v1", provider="openrouter",
                max_iterations=1, quiet_mode=True,
                skip_memory=True, skip_context_files=True, enabled_toolsets=[],
            )
            raw_type = classify_agent.run_conversation(
                user_message=_TASK_TYPE_PROMPT.format(task=task)
            ).get("final_response", "other").strip().lower()
            if raw_type in _GRADER_PROMPTS:
                task_type = raw_type
        except Exception:
            pass

    # Step 5: Grade the output (Karpathy-style — every action gets a number)
    quality_score = None
    grader_reasoning = None
    beat_this = None
    grade: dict = {}

    if output and len(output) > 50:
        try:
            grade_agent = AIAgent(
                model=or_model, api_key=or_key,
                base_url="https://openrouter.ai/api/v1", provider="openrouter",
                max_iterations=1, quiet_mode=True,
                skip_memory=True, skip_context_files=True, enabled_toolsets=[],
            )
            rubric = _GRADER_PROMPTS.get(task_type, _GRADER_PROMPTS["other"])
            raw_grade = grade_agent.run_conversation(
                user_message=rubric.format(task=task, output=output[:1500])
            ).get("final_response", "").strip()
            if raw_grade.startswith("```"):
                import re as _re
                raw_grade = _re.sub(r"^```[a-z]*\n?", "", raw_grade)
                raw_grade = _re.sub(r"\n?```$", "", raw_grade.rstrip())
            grade = json.loads(raw_grade)
            quality_score = int(grade.get("total", 0))
            beat_this = grade.get("beat_this_next_time", "")
            grader_reasoning = json.dumps({k: v for k, v in grade.items() if k != "total"})
        except Exception as e:
            logger.debug("Grading failed for tenant %s: %s", str(tenant_id)[:8], e)

    # Step 6: Log action WITH score
    summary = f"{datetime.now().strftime('%Y-%m-%d %H:%M')} — {task[:120]}"
    if quality_score is not None:
        summary += f" [score: {quality_score}/100]"

    await self.db.execute(
        """INSERT INTO worker_actions
           (tenant_id, summary, full_output, task_type, quality_score, grader_reasoning, created_at)
           VALUES ($1, $2, $3, $4, $5, $6, NOW())""",
        tenant_id, summary, output, task_type, quality_score, grader_reasoning,
    )

    # Step 7: Hill-climb — compare to previous score for same task type
    if quality_score is not None and task_type != "other":
        prev = await self.db.fetchrow(
            """SELECT quality_score FROM worker_actions
               WHERE tenant_id = $1 AND task_type = $2 AND quality_score IS NOT NULL
               AND created_at < NOW() - INTERVAL '10 minutes'
               ORDER BY created_at DESC LIMIT 1""",
            tenant_id, task_type,
        )
        if prev and prev["quality_score"] is not None:
            prev_score = prev["quality_score"]
            delta = quality_score - prev_score
            if delta > 0:
                trend = f"IMPROVED +{delta} points ({prev_score} → {quality_score})"
                what = f"What worked: {grade.get('best_thing', '')}"
            elif delta < 0:
                trend = f"REGRESSED {delta} points ({prev_score} → {quality_score})"
                what = f"What went wrong: {grade.get('biggest_gap', '')}"
            else:
                trend = f"SAME score ({quality_score}/100)"
                what = f"What worked: {grade.get('best_thing', '')}"

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            hill_note = (
                f"{trend} on {task_type}.\n"
                f"Task: {task[:100]}\n"
                f"{what}\n"
                f"Next time: {beat_this or 'maintain approach'}"
            )
            await self.db.execute(
                """INSERT INTO tenant_memory (tenant_id, memory_type, content)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (tenant_id, memory_type)
                   DO UPDATE SET content = EXCLUDED.content, updated_at = NOW()""",
                tenant_id, f"hill_climb_{task_type}_{ts}", hill_note,
            )

    # Step 8: Save beat_this as a standing learning for next time
    if beat_this:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        await self.db.execute(
            """INSERT INTO tenant_memory (tenant_id, memory_type, content)
               VALUES ($1, $2, $3)
               ON CONFLICT (tenant_id, memory_type)
               DO UPDATE SET content = EXCLUDED.content, updated_at = NOW()""",
            tenant_id, f"learning_{ts}",
            f"[{task_type}] Score: {quality_score}/100. Next time: {beat_this}",
        )

    logger.info(
        "Autonomous task complete [%s] type=%s score=%s",
        str(tenant_id)[:8], task_type,
        f"{quality_score}/100" if quality_score is not None else "ungraded",
    )


async def _digest_loop(self):
    """Send a digest of autonomous actions to the manager every 2 hours."""
    while self.running:
        try:
            await asyncio.sleep(7200)  # every 2 hours

            tenants = await self.db.fetch(
                "SELECT * FROM tenants WHERE active = true AND tenant_config IS NOT NULL"
            )
            for tenant in tenants:
                config = json.loads(tenant["tenant_config"] or "{}")
                manager_chat_id = config.get("manager_chat_id")
                if not manager_chat_id:
                    continue

                actions = await self.db.fetch(
                    "SELECT summary, full_output FROM worker_actions WHERE tenant_id = $1 "
                    "AND created_at > NOW() - INTERVAL '2 hours' ORDER BY created_at DESC",
                    tenant["id"],
                )
                if not actions:
                    continue

                worker_name = config.get("worker_name", "Hermes")
                lines = [f"**{worker_name} update — last 2 hours:**\n"]
                for a in actions:
                    lines.append(f"• {a['summary']}")
                    if a["full_output"] and len(a["full_output"]) > 30:
                        lines.append(f"  → {a['full_output'][:200].strip()}...")
                digest = "\n".join(lines)

                await self.redis.lpush("hermes:responses", json.dumps({
                    "tenant_id": str(tenant["id"]),
                    "platform": "telegram",
                    "chat_id": manager_chat_id,
                    "response": digest,
                }))
                logger.info("Digest sent to manager for tenant %s (%d actions)", str(tenant["id"])[:8], len(actions))

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Digest loop error: %s", e, exc_info=True)
            await asyncio.sleep(10)


# Inject autonomous methods onto the actual HermesWorker class
HermesWorker._autonomous_loop = _autonomous_loop
HermesWorker._run_autonomous_decision = _run_autonomous_decision
HermesWorker._digest_loop = _digest_loop


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    worker = HermesWorker(worker_id=int(os.getenv("WORKER_ID", "0")))
    await worker.start()


if __name__ == "__main__":
    asyncio.run(main())
