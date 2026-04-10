"""
Hermes Dream Cycle — nightly memory consolidation

Runs at 3am UTC for each tenant:
  1. Collect last 24h of worker actions
  2. Find stale brain pages (not updated in 3+ days)
  3. Re-synthesize compiled_truth for each stale page
  4. Extract daily patterns and upsert as brain page

Returns {"pages_updated": N, "patterns_found": N, "actions_processed": N}
"""

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger("hermes.dream")


async def run_dream_cycle(tenant_id, db, brain, llm_agent_factory) -> dict:
    """
    Nightly consolidation for a single tenant.

    Args:
        tenant_id: UUID of the tenant
        db: asyncpg pool
        brain: BrainMemory instance
        llm_agent_factory: callable() -> AIAgent for LLM calls

    Returns dict with pages_updated, patterns_found, actions_processed.
    """
    pages_updated = 0
    patterns_found = 0
    actions_processed = 0

    try:
        # Step 1: Collect last 24h of worker actions
        actions = await db.fetch(
            """SELECT summary, full_output, task_type, quality_score
               FROM worker_actions
               WHERE tenant_id = $1
                 AND created_at > NOW() - INTERVAL '24 hours'
               ORDER BY created_at DESC""",
            tenant_id,
        )
        actions_processed = len(actions)

        # Step 2: Find stale brain pages (not updated in 3+ days)
        stale_pages = await db.fetch(
            """SELECT slug, compiled_truth, timeline
               FROM brain_pages
               WHERE tenant_id = $1
                 AND page_type = 'memory'
                 AND (last_dream_at IS NULL OR last_dream_at < NOW() - INTERVAL '3 days')
               ORDER BY updated_at ASC
               LIMIT 20""",
            tenant_id,
        )

        # Step 3: Re-synthesize compiled_truth for each stale page
        for page in stale_pages:
            try:
                slug = page["slug"]
                timeline = page["timeline"] or ""
                old_truth = page["compiled_truth"] or ""

                if not timeline.strip():
                    continue

                agent = llm_agent_factory()
                if agent is None:
                    break

                synth_prompt = (
                    f"You are consolidating memory for an AI worker.\n"
                    f"Topic: {slug}\n\n"
                    f"Evidence timeline:\n{timeline[-2000:]}\n\n"
                    f"Previous summary: {old_truth[:400] if old_truth else 'None'}\n\n"
                    f"Write a concise, factual summary (max 150 words) of the current best "
                    f"understanding about this topic. Focus on what is still true and actionable. "
                    f"No preamble — just the summary."
                )
                result = agent.run_conversation(user_message=synth_prompt)
                new_truth = result.get("final_response", "").strip()

                if new_truth:
                    await db.execute(
                        """UPDATE brain_pages
                           SET compiled_truth = $1, last_dream_at = NOW(), updated_at = NOW()
                           WHERE tenant_id = $2 AND slug = $3""",
                        new_truth, tenant_id, slug,
                    )
                    pages_updated += 1
                    logger.debug("Dream: resynthesized page '%s' for tenant %s", slug, str(tenant_id)[:8])

            except Exception as e:
                logger.debug("Dream: page resynthesis failed for '%s': %s", page["slug"], e)

        # Step 4: Synthesize daily patterns from today's actions and upsert
        if actions_processed > 0:
            try:
                agent = llm_agent_factory()
                if agent is not None:
                    action_summaries = "\n".join(
                        f"- [{a['task_type'] or 'other'}] score={a['quality_score'] or 'N/A'}: {a['summary']}"
                        for a in actions[:20]
                    )
                    pattern_prompt = (
                        f"An AI worker completed these tasks in the last 24 hours:\n\n"
                        f"{action_summaries}\n\n"
                        f"Identify 2-3 patterns or insights about the worker's performance today. "
                        f"Be specific — what areas are strong, what areas need improvement, "
                        f"what types of tasks are being done most? "
                        f"Keep it under 100 words. No preamble."
                    )
                    result = agent.run_conversation(user_message=pattern_prompt)
                    patterns_text = result.get("final_response", "").strip()

                    if patterns_text:
                        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                        await brain.upsert(
                            tenant_id,
                            f"patterns/daily-{today}",
                            patterns_text,
                            page_type="memory",
                        )
                        patterns_found = 1
                        logger.info(
                            "Dream: daily patterns stored for tenant %s (%d actions)",
                            str(tenant_id)[:8], actions_processed,
                        )

            except Exception as e:
                logger.debug("Dream: pattern synthesis failed: %s", e)

    except Exception as e:
        logger.warning("Dream cycle failed for tenant %s: %s", str(tenant_id)[:8], e)

    return {
        "pages_updated": pages_updated,
        "patterns_found": patterns_found,
        "actions_processed": actions_processed,
    }


def _seconds_until_3am() -> float:
    """Return seconds until next 3:00 UTC."""
    now = datetime.now(timezone.utc)
    next_3am = now.replace(hour=3, minute=0, second=0, microsecond=0)
    if now.hour >= 3:
        from datetime import timedelta
        next_3am += timedelta(days=1)
    return (next_3am - now).total_seconds()
