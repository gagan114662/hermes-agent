# agent/learning_loop.py
"""
Learning loop — session → skill improvement.

After each completed session, Hermes reviews what happened and:
  1. Identifies reusable patterns worth saving as skills
  2. Updates existing skills that were wrong or incomplete
  3. Records failure patterns to avoid repeating mistakes

Claude Code doesn't learn. Hermes gets smarter every session.

Architecture:
    - run_stop_hooks() calls trigger_learning_loop() after session end
    - A background agent reviews the session transcript
    - Extracts learnable patterns using structured prompts
    - Saves new skills or patches existing ones via skill_manage
    - Journals everything in learning_journal.py for rollback

Quality gates (from learning_validator.py):
    - Min confidence score before saving
    - Max skill count per profile
    - Duplicate detection (don't save what's already known)

Usage:
    from agent.learning_loop import trigger_learning_loop

    # Called automatically from stop_hooks after complex sessions:
    trigger_learning_loop(agent, messages, final_response)

    # Or manually:
    from agent.learning_loop import run_learning_loop_sync
    result = run_learning_loop_sync(agent, messages)
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Minimum tool calls in a session to bother learning from it
LEARN_MIN_TOOL_CALLS = 4

# Minimum session duration (seconds) to bother
LEARN_MIN_DURATION = 30

# Max skills to create per session (prevent runaway skill creation)
MAX_SKILLS_PER_SESSION = 3

_EXTRACT_PROMPT = """You are reviewing a completed agent session to extract reusable knowledge.

Session summary (last assistant response):
{final_response}

Number of tool calls made: {tool_call_count}

Your job: identify up to {max_skills} patterns from this session that are worth saving as reusable skills.

A pattern is worth saving if:
- It's a multi-step workflow the agent had to figure out (not trivial)
- It would save time if the agent faced the same type of task again
- It's general enough to apply to similar future tasks
- It's NOT already obvious (don't save "use web_search to search the web")

For each pattern, output:
{{
  "learnings": [
    {{
      "name": "short-kebab-case-skill-name",
      "title": "Human readable title",
      "description": "One sentence: what this skill does and when to use it",
      "content": "The actual skill instructions in markdown. Be specific and actionable.",
      "confidence": 0.0-1.0,
      "type": "new" | "update",
      "existing_skill_name": "only if type=update"
    }}
  ],
  "failure_patterns": [
    "Brief description of a mistake made and how to avoid it next time"
  ]
}}

Output ONLY valid JSON. If nothing is worth saving, output {{"learnings": [], "failure_patterns": []}}"""


def trigger_learning_loop(
    agent,
    messages: list,
    final_response: str,
    *,
    async_mode: bool = True,
) -> None:
    """
    Trigger the learning loop after a session completes.

    Called from stop_hooks. Runs async by default so it doesn't
    block the user getting their response.

    Gates:
    - Only runs if session was complex enough (tool calls, duration)
    - Only runs if agent.learning_enabled is True (default True)
    - Only runs for top-level agents (not subagents)
    """
    # Gate 1: Only for top-level agents
    if getattr(agent, "_delegate_depth", 0) > 0:
        return

    # Gate 2: Enabled check
    if not getattr(agent, "learning_enabled", True):
        return

    # Gate 3: Complexity gates
    tool_call_count = sum(1 for m in messages if isinstance(m, dict) and m.get("role") == "tool")
    if tool_call_count < LEARN_MIN_TOOL_CALLS:
        return

    if async_mode:
        t = threading.Thread(
            target=_run_learning_loop_safe,
            args=(agent, messages, final_response, tool_call_count),
            daemon=True,
        )
        t.start()
    else:
        _run_learning_loop_safe(agent, messages, final_response, tool_call_count)


def run_learning_loop_sync(agent, messages: list) -> dict:
    """Run learning loop synchronously. Returns result dict."""
    tool_call_count = sum(1 for m in messages if isinstance(m, dict) and m.get("role") == "tool")
    final_response = ""
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "assistant":
            content = m.get("content", "")
            if isinstance(content, str) and content.strip():
                final_response = content.strip()
                break
    return _run_learning_loop(agent, messages, final_response, tool_call_count)


def _run_learning_loop_safe(agent, messages, final_response, tool_call_count) -> None:
    """Wrapper that never raises — fire-and-forget safety."""
    try:
        result = _run_learning_loop(agent, messages, final_response, tool_call_count)
        if result.get("skills_created") or result.get("skills_updated"):
            logger.info(
                "learning_loop: created %d skills, updated %d skills in session",
                result.get("skills_created", 0),
                result.get("skills_updated", 0),
            )
    except Exception as exc:
        logger.debug("learning_loop: safe wrapper caught: %s", exc)


def _run_learning_loop(
    agent,
    messages: list,
    final_response: str,
    tool_call_count: int,
) -> dict:
    """
    Core learning loop. Extracts learnings and saves skills.
    Returns stats dict.
    """
    start = time.monotonic()
    result = {
        "skills_created": 0,
        "skills_updated": 0,
        "failure_patterns": 0,
        "skipped": False,
        "error": None,
    }

    # ── Step 1: Ask model to extract learnings ───────────────────────────────
    try:
        extract_prompt = _EXTRACT_PROMPT.format(
            final_response=(final_response or "")[:1500],
            tool_call_count=tool_call_count,
            max_skills=MAX_SKILLS_PER_SESSION,
        )

        from tools.delegate_tool import delegate_task
        extract_json = delegate_task(
            goal=extract_prompt,
            agent_type="general",
            max_iterations=8,
            parent_agent=agent,
        )
        extract_data = json.loads(extract_json)
        raw_summary = extract_data.get("results", [{}])[0].get("summary", "")

        # Extract JSON from response
        import re
        json_match = re.search(r'\{.*\}', raw_summary, re.DOTALL)
        if not json_match:
            result["skipped"] = True
            return result

        learnings_data = json.loads(json_match.group())

    except Exception as exc:
        logger.debug("learning_loop: extraction failed: %s", exc)
        result["error"] = str(exc)
        return result

    # ── Step 2: Validate and save each learning ──────────────────────────────
    learnings = learnings_data.get("learnings", [])
    failure_patterns = learnings_data.get("failure_patterns", [])

    for learning in learnings[:MAX_SKILLS_PER_SESSION]:
        try:
            _save_learning(learning, agent, result)
        except Exception as exc:
            logger.debug("learning_loop: save failed for %s: %s", learning.get("name"), exc)

    # ── Step 3: Save failure patterns to memory ──────────────────────────────
    if failure_patterns:
        try:
            _save_failure_patterns(failure_patterns, agent)
            result["failure_patterns"] = len(failure_patterns)
        except Exception as exc:
            logger.debug("learning_loop: failure pattern save failed: %s", exc)

    result["duration_seconds"] = round(time.monotonic() - start, 2)
    return result


def _save_learning(learning: dict, agent, result: dict) -> None:
    """Validate and save one learning as a skill."""
    name = learning.get("name", "").strip()
    title = learning.get("title", "").strip()
    content = learning.get("content", "").strip()
    confidence = float(learning.get("confidence", 0.5))
    learning_type = learning.get("type", "new")

    # Quality gate
    if not name or not content:
        return
    if confidence < 0.5:
        logger.debug("learning_loop: skipping %s (confidence %.2f < 0.5)", name, confidence)
        return
    if len(content) < 50:
        logger.debug("learning_loop: skipping %s (content too short)", name)
        return

    # Build skill markdown with frontmatter
    skill_md = f"""---
title: {title or name}
description: {learning.get('description', '')}
auto_generated: true
confidence: {confidence}
---

{content}
"""

    # Save via skill_manage tool
    try:
        from tools.registry import dispatch
        if learning_type == "update" and learning.get("existing_skill_name"):
            dispatch("skill_manage", {
                "action": "patch",
                "name": learning["existing_skill_name"],
                "patch_content": content,
            })
            result["skills_updated"] = result.get("skills_updated", 0) + 1
            logger.info("learning_loop: updated skill '%s'", learning["existing_skill_name"])
        else:
            dispatch("skill_manage", {
                "action": "create",
                "name": name,
                "content": skill_md,
            })
            result["skills_created"] = result.get("skills_created", 0) + 1
            logger.info("learning_loop: created skill '%s'", name)
    except Exception as exc:
        # Fallback: write directly to skills directory
        try:
            _write_skill_direct(name, skill_md, agent)
            result["skills_created"] = result.get("skills_created", 0) + 1
        except Exception as exc2:
            logger.debug("learning_loop: skill write fallback failed: %s", exc2)


def _write_skill_direct(name: str, content: str, agent) -> None:
    """Direct file write fallback when skill_manage isn't available."""
    import os
    from pathlib import Path

    hermes_home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
    skills_dir = Path(hermes_home) / "skills" / "auto-learned" / name
    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "SKILL.md").write_text(content, encoding="utf-8")


def _save_failure_patterns(patterns: list[str], agent) -> None:
    """Save failure patterns to agent memory so it avoids them next time."""
    if not patterns:
        return

    summary = "Learned failure patterns from recent session:\n" + "\n".join(
        f"- {p}" for p in patterns[:5]
    )

    try:
        from tools.memory_tool import memory_tool
        store = getattr(agent, "_memory_store", None)
        if store:
            memory_tool(action="add", target="memory", content=summary, store=store)
    except Exception as exc:
        logger.debug("learning_loop: failure pattern memory write failed: %s", exc)
