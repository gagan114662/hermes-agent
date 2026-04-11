# Hermes Autonomous Worker — 4 Critical Fixes

Branch: `feature/ai-sdr-workers`
Files to touch: `scale/worker.py` only (all 4 fixes are in there)

---

## Fix 1: Digest mode — stop spamming Telegram

**Problem:** `_run_autonomous_decision()` pushes every action output directly to the manager's Telegram chat. If the worker acts every 5 minutes, the manager gets 12+ messages per hour. They will mute it within a day.

**Fix:** Accumulate actions in `worker_actions` table (already happening). Add a digest sender that fires once every 2 hours. Only report the digest — not individual actions.

Replace this block in `_run_autonomous_decision()`:
```python
# Step 6: Report meaningful output to manager
if output and len(output) > 50:
    await self.redis.lpush("hermes:responses", json.dumps({...}))
```

With: don't push to Telegram at all from `_run_autonomous_decision`. Instead, add a `_digest_loop()` that runs every 2 hours:

```python
async def _digest_loop(self):
    while self.running:
        await asyncio.sleep(7200)  # every 2 hours
        tenants = await self.db.fetch(
            "SELECT * FROM tenants WHERE active = true AND tenant_config IS NOT NULL"
        )
        for tenant in tenants:
            config = json.loads(tenant["tenant_config"] or "{}")
            manager_chat_id = config.get("manager_chat_id")
            if not manager_chat_id:
                continue
            # Get actions from last 2 hours
            actions = await self.db.fetch(
                "SELECT summary, full_output FROM worker_actions WHERE tenant_id=$1 "
                "AND created_at > NOW() - INTERVAL '2 hours' ORDER BY created_at DESC",
                tenant["id"]
            )
            if not actions:
                continue
            worker_name = config.get("worker_name", "Hermes")
            lines = [f"**{worker_name} update — last 2 hours:**\n"]
            for a in actions:
                lines.append(f"• {a['summary']}")
                if a['full_output'] and len(a['full_output']) > 30:
                    # Truncate to first 200 chars of output
                    lines.append(f"  → {a['full_output'][:200].strip()}...")
            digest = "\n".join(lines)
            await self.redis.lpush("hermes:responses", json.dumps({
                "tenant_id": str(tenant["id"]),
                "platform": "telegram",
                "chat_id": manager_chat_id,
                "response": digest,
            }))
```

Add `self._digest_loop()` to the `asyncio.gather()` in `start()`:
```python
await asyncio.gather(
    self._main_loop(),
    self._autonomous_loop(),
    self._digest_loop(),   # <-- add this
)
```

---

## Fix 2: Draft-first for risky autonomous actions

**Problem:** In autonomous mode the worker has `social_media` and `google-workspace` toolsets. It can tweet, post to LinkedIn, and send Gmail emails without the manager seeing it first. For most customers this is unacceptable.

**Fix:** In `_run_autonomous_decision()`, inject a "draft only" instruction into the task before execution:

```python
task = decision.get("task", "").strip()
if not task:
    return

# IMPORTANT: In autonomous mode, never publish or send — always draft
autonomous_task = (
    task + "\n\n"
    "IMPORTANT: You are running autonomously without manager supervision. "
    "Do NOT publish posts, send emails, or take any irreversible action. "
    "Instead: write drafts and save them to your drafts/ folder. "
    "Summarise what you drafted and what action the manager needs to take to publish/send it."
)
```

Then pass `autonomous_task` instead of `task` to `work_agent.run_conversation()`.

This way the worker researches, writes, prepares — but never fires. The digest tells the manager "I drafted 3 LinkedIn posts, ready to publish" and they approve via Telegram.

---

## Fix 3: Memory pagination — prevent context blowup

**Problem:** In both `_process_message()` and `_run_autonomous_decision()`, the memory query has no LIMIT:
```python
memories = await self.db.fetch(
    "SELECT memory_type, content FROM tenant_memory WHERE tenant_id = $1",
    tenant_id,
)
```
After a month of learnings (saved every 5 min = ~8,640 learnings/month), this will load thousands of rows into every prompt. Context limit hit, or very slow.

**Fix:** In `_run_autonomous_decision()`, change the memory query to:
```python
memories = await self.db.fetch(
    """SELECT memory_type, content FROM tenant_memory
       WHERE tenant_id = $1
       ORDER BY updated_at DESC
       LIMIT 40""",
    tenant_id,
)
```

In `_process_message()`, change the memory query (inside the `if system_prompt is None:` block) to:
```python
memories = await self.db.fetch(
    """SELECT memory_type, content FROM tenant_memory
       WHERE tenant_id = $1
       ORDER BY updated_at DESC
       LIMIT 20""",
    uuid.UUID(tenant_id),
)
```

40 rows for autonomous (more context needed), 20 for message handling (conversation history already uses tokens).

---

## Fix 4: Add minimum value threshold to autonomous decision

**Problem:** The decision prompt has no way to say "nothing worth doing right now." The LLM will always find something to fill the cycle, even if the value is low. This means the worker burns tokens on low-value tasks.

**Fix:** Add a `confidence` field and minimum threshold to the decision JSON. In `_DECISION_PROMPT`, change the JSON spec to:

```
Respond in pure JSON only (no markdown, no explanation):
{
  "reasoning": "why this is the highest-value action right now",
  "action": "do_work" or "rest",
  "confidence": 1-10 (how confident you are this is worth doing right now),
  "task": "precise, specific description of exactly what to do",
  "expected_outcome": "what you will deliver when done"
}

If confidence is below 7, set action to "rest" — it's better to do nothing than waste time on low-value work.
If it is very late at night (after midnight, before 5am), set action to "rest".
If you completed very similar work within the last 60 minutes, set action to "rest".
```

Then in `_run_autonomous_decision()`, after parsing the decision:
```python
if decision.get("action") != "do_work":
    return

# Minimum confidence check
if decision.get("confidence", 10) < 7:
    logger.debug("Worker %s low confidence (%s), skipping", str(tenant_id)[:8], decision.get("confidence"))
    return
```

---

## How to apply

All 4 changes are in `scale/worker.py`. No other files need changing. No migration needed.

After applying:
- Rebuild Docker: `docker compose -f scale/docker-compose.scale.yml up -d --build`
- Restart worker: `docker compose -f scale/docker-compose.scale.yml restart worker`

## Verification

- Manager Telegram chat: should get ONE digest message every 2 hours, not one per action
- Check `worker_actions` table: should show rows being inserted (worker is still working)
- Check `tenant_memory`: learnings table should have rows with `learning_` prefix
- Send a test message on Telegram: should get reply within 10 seconds (message loop priority still works)
- Confirm no tweets/emails sent autonomously: check social_media/gmail logs, should be empty
