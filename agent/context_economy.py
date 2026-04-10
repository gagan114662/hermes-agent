# agent/context_economy.py
"""
Context economy — selective tool result clearing + agent memory snapshots.

Ported from CC's context economy pattern (function result clearing,
summarize tool results, agent memory snapshots).

## Why this exists
In long agentic runs, tool results from 30+ turns ago waste context window.
context_compressor.py handles whole-conversation summarization, but that's
too coarse — it throws away everything. This module surgically clears
individual old tool results while keeping model reasoning intact.

## Functions
  apply_selective_result_clearing()  — replace old large results with placeholder
  save_agent_snapshot()              — save compact summary for named agents
  get_agent_snapshot()               — retrieve snapshot for agent reuse
  clear_agent_snapshot()             — remove snapshot when agent is done
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Selective tool result clearing
# ---------------------------------------------------------------------------

RESULT_CLEARED_PLACEHOLDER = "[Tool result cleared — context efficiency]"

# Clear results older than this many turns (counting from current turn).
CLEAR_AFTER_TURNS = 15

# Only clear results longer than this (short results are cheap to keep).
MIN_RESULT_LENGTH_TO_CLEAR = 400

# Tool names whose results should NEVER be cleared (their content matters long-term).
NEVER_CLEAR_TOOLS = frozenset({
    "memory",
    "read_file",       # referenced later in the conversation
    "session_search",  # cross-session context the model may refer back to
    "skill_manage",    # skill loading — model may need to re-read
})


def apply_selective_result_clearing(
    messages: list,
    current_turn: int,
    *,
    clear_after_turns: int = CLEAR_AFTER_TURNS,
    min_length: int = MIN_RESULT_LENGTH_TO_CLEAR,
    never_clear: frozenset = NEVER_CLEAR_TOOLS,
) -> list:
    """
    Return a new messages list with old, large tool results replaced by a placeholder.

    Clears tool results that are:
    - older than clear_after_turns
    - longer than min_length characters
    - not in the never_clear set

    This is non-destructive: the original messages list is not modified.
    The agent loop should call this every N turns and replace self._messages.

    Example:
        self._messages = apply_selective_result_clearing(
            self._messages, self._turn_count
        )
    """
    cleared_count = 0
    new_messages = []

    for i, msg in enumerate(messages):
        turn_age = current_turn - i

        # Only process tool result messages
        is_tool_result = (
            isinstance(msg, dict)
            and msg.get("role") == "tool"
        )

        if (
            is_tool_result
            and turn_age > clear_after_turns
            and msg.get("tool_name") not in never_clear
        ):
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > min_length:
                # Replace with placeholder — preserve tool_call_id so API accepts it
                msg = {**msg, "content": RESULT_CLEARED_PLACEHOLDER}
                cleared_count += 1
            elif isinstance(content, list):
                # Multi-part content (e.g. vision tool results)
                total_text = "".join(
                    c.get("text", "") for c in content if isinstance(c, dict)
                )
                if len(total_text) > min_length:
                    msg = {**msg, "content": RESULT_CLEARED_PLACEHOLDER}
                    cleared_count += 1

        new_messages.append(msg)

    if cleared_count:
        logger.debug(
            "context_economy: cleared %d tool results older than %d turns",
            cleared_count, clear_after_turns
        )

    return new_messages


def should_apply_clearing(turn_count: int, interval: int = 10) -> bool:
    """Return True if it's time to run a clearing pass. Call every N turns."""
    return turn_count > 0 and turn_count % interval == 0


# ---------------------------------------------------------------------------
# Agent memory snapshots — shared read-only knowledge between named agents
# ---------------------------------------------------------------------------

# In-process snapshot store: agent_name → compact summary string.
# Cleared between sessions automatically (in-memory only).
_agent_snapshots: dict[str, str] = {}

# Max characters to keep per snapshot (prevents runaway growth).
_MAX_SNAPSHOT_CHARS = 4000


def save_agent_snapshot(agent_name: str, summary: str) -> None:
    """
    Save a compact summary for a named agent so it can be resumed without
    re-reading everything.

    Called at the end of delegate_task() for named agents:
        save_agent_snapshot("researcher", child.get_compact_summary())
    """
    if not agent_name or not summary:
        return
    truncated = summary[:_MAX_SNAPSHOT_CHARS]
    if len(summary) > _MAX_SNAPSHOT_CHARS:
        truncated += "\n[snapshot truncated for context efficiency]"
    _agent_snapshots[agent_name] = truncated
    logger.debug("context_economy: saved snapshot for agent '%s' (%d chars)", agent_name, len(truncated))


def get_agent_snapshot(agent_name: str) -> Optional[str]:
    """
    Retrieve a saved snapshot for a named agent.

    Called at the start of delegate_task() when agent_name is set:
        snapshot = get_agent_snapshot("researcher")
        if snapshot:
            context = f"Previous session memory:\\n{snapshot}\\n\\n{context}"
    """
    return _agent_snapshots.get(agent_name)


def clear_agent_snapshot(agent_name: str) -> None:
    """Remove a snapshot (e.g. when the agent's task is fully done)."""
    _agent_snapshots.pop(agent_name, None)


def list_agent_snapshots() -> dict[str, int]:
    """Return {agent_name: snapshot_length} for debugging."""
    return {name: len(snap) for name, snap in _agent_snapshots.items()}
