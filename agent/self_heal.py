# agent/self_heal.py
"""
Self-heal loop — automatic verify + retry.

After a complex task (many tool calls), Hermes spawns a Verify agent.
If it returns VERDICT: FAIL or VERDICT: PARTIAL, Hermes spawns a Repair
agent with full failure context and retries — up to MAX_HEAL_ATTEMPTS.

Claude Code has no equivalent. Hermes checks its own work and fixes mistakes
without being asked.

Architecture:
    run_agent.py calls maybe_self_heal() after _build_result() when
    the task was "complex" (>= HEAL_MIN_TOOL_CALLS tool calls in the turn).

Flow:
    1. Spawn verify agent (read-only, adversarial)
    2. Parse VERDICT from response
    3. If PASS → done
    4. If FAIL/PARTIAL → spawn repair agent with failure context
    5. Repair runs, then verify again
    6. Repeat up to MAX_HEAL_ATTEMPTS

Usage:
    from agent.self_heal import maybe_self_heal
    # In run_agent._build_result():
    heal_result = maybe_self_heal(agent, messages, task_description, tool_call_count)
"""
from __future__ import annotations

import logging
import re
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Minimum tool calls in a turn to trigger self-heal
HEAL_MIN_TOOL_CALLS = 5

# Maximum verify+repair cycles
MAX_HEAL_ATTEMPTS = 2

# Regex to extract VERDICT from verify agent response
_VERDICT_RE = re.compile(
    r"VERDICT\s*:\s*(PASS|FAIL|PARTIAL)",
    re.IGNORECASE,
)


def _extract_verdict(text: str) -> Optional[str]:
    """Parse VERDICT: PASS/FAIL/PARTIAL from verify agent output."""
    match = _VERDICT_RE.search(text or "")
    return match.group(1).upper() if match else None


def _count_tool_calls_in_messages(messages: list) -> int:
    """Count tool result messages in the conversation."""
    return sum(1 for m in messages if isinstance(m, dict) and m.get("role") == "tool")


def _build_verify_goal(task_description: str, messages: list) -> str:
    """Build the goal string for the verify agent."""
    # Extract the last few assistant messages as task summary
    assistant_texts = []
    for m in reversed(messages[-20:]):
        if isinstance(m, dict) and m.get("role") == "assistant":
            content = m.get("content", "")
            if isinstance(content, str) and content.strip():
                assistant_texts.append(content.strip()[:300])
            if len(assistant_texts) >= 2:
                break

    summary = "\n\n".join(reversed(assistant_texts)) if assistant_texts else "(no summary)"

    return (
        f"Adversarially verify this completed task:\n\n"
        f"**Task:** {task_description}\n\n"
        f"**What the agent reported:**\n{summary}\n\n"
        f"Read every file mentioned above and check: correctness, edge cases, "
        f"error handling, security, completeness.\n\n"
        f"End your response with exactly one of:\n"
        f"VERDICT: PASS\n"
        f"VERDICT: FAIL\n"
        f"VERDICT: PARTIAL"
    )


def _build_repair_goal(
    task_description: str,
    verify_response: str,
    attempt: int,
) -> str:
    """Build the goal string for the repair agent."""
    return (
        f"A verify agent found problems with this task. Fix them.\n\n"
        f"**Original task:** {task_description}\n\n"
        f"**Verify agent findings (attempt {attempt}):**\n{verify_response}\n\n"
        f"Fix every issue listed. Be specific: read the actual files, "
        f"make the actual changes. Do not re-describe the problems — fix them.\n\n"
        f"When done, report: what you fixed, what files you changed, "
        f"what you could not fix and why."
    )


def maybe_self_heal(
    agent,
    messages: list,
    task_description: str,
    tool_call_count: int,
    *,
    min_tool_calls: int = HEAL_MIN_TOOL_CALLS,
    max_attempts: int = MAX_HEAL_ATTEMPTS,
) -> Optional[dict]:
    """
    Run self-heal loop if the task was complex enough to warrant it.

    Returns a dict with heal results, or None if heal was skipped.

    Called from run_agent._build_result() after task completion.
    """
    # Only heal complex tasks
    if tool_call_count < min_tool_calls:
        return None

    # Don't heal if already in a heal cycle (child agents)
    if getattr(agent, "_in_self_heal", False):
        return None

    # Don't heal if self-heal is disabled
    if not getattr(agent, "self_heal_enabled", True):
        return None

    # Don't heal subagents (depth > 0)
    if getattr(agent, "_delegate_depth", 0) > 0:
        return None

    logger.info("self_heal: starting verify+repair cycle for task: %s", task_description[:80])

    heal_log = []
    final_verdict = None

    for attempt in range(1, max_attempts + 1):
        # ── Step 1: Spawn verify agent ───────────────────────────────────────
        verify_goal = _build_verify_goal(task_description, messages)

        try:
            from tools.delegate_tool import delegate_task
            import json as _json

            verify_result_json = delegate_task(
                goal=verify_goal,
                agent_type="verify",
                max_iterations=20,
                parent_agent=agent,
            )
            verify_data = _json.loads(verify_result_json)
            verify_response = ""
            if verify_data.get("results"):
                verify_response = verify_data["results"][0].get("summary", "")
        except Exception as exc:
            logger.warning("self_heal: verify agent failed: %s", exc)
            break

        verdict = _extract_verdict(verify_response)
        heal_log.append({
            "attempt": attempt,
            "verdict": verdict,
            "verify_summary": verify_response[:500],
        })

        logger.info("self_heal: attempt %d verdict: %s", attempt, verdict)

        if verdict == "PASS":
            final_verdict = "PASS"
            break

        if verdict is None:
            # Verify agent didn't produce a verdict — don't retry
            logger.warning("self_heal: no VERDICT found in verify response")
            break

        final_verdict = verdict  # FAIL or PARTIAL

        if attempt >= max_attempts:
            break

        # ── Step 2: Spawn repair agent ───────────────────────────────────────
        repair_goal = _build_repair_goal(task_description, verify_response, attempt)

        try:
            agent._in_self_heal = True
            repair_result_json = delegate_task(
                goal=repair_goal,
                agent_type="general",
                max_iterations=40,
                parent_agent=agent,
            )
            repair_data = _json.loads(repair_result_json)
            repair_summary = ""
            if repair_data.get("results"):
                repair_summary = repair_data["results"][0].get("summary", "")
            heal_log[-1]["repair_summary"] = repair_summary[:500]
            logger.info("self_heal: repair complete, re-verifying...")
        except Exception as exc:
            logger.warning("self_heal: repair agent failed: %s", exc)
            break
        finally:
            agent._in_self_heal = False

    return {
        "triggered": True,
        "attempts": len(heal_log),
        "final_verdict": final_verdict,
        "log": heal_log,
    }


def format_heal_summary(heal_result: Optional[dict]) -> str:
    """Format self-heal result for display to user."""
    if not heal_result or not heal_result.get("triggered"):
        return ""

    verdict = heal_result.get("final_verdict", "UNKNOWN")
    attempts = heal_result.get("attempts", 0)

    icons = {"PASS": "✅", "FAIL": "❌", "PARTIAL": "⚠️", "UNKNOWN": "❓"}
    icon = icons.get(verdict, "❓")

    if verdict == "PASS":
        return f"\n{icon} Self-verified: PASS (checked in {attempts} round{'s' if attempts > 1 else ''})"
    elif verdict == "PARTIAL":
        return f"\n{icon} Self-verified: PARTIAL — some issues remain after {attempts} repair attempt{'s' if attempts > 1 else ''}"
    elif verdict == "FAIL":
        return f"\n{icon} Self-verified: FAIL — could not fully repair after {attempts} attempt{'s' if attempts > 1 else ''}"
    return ""
