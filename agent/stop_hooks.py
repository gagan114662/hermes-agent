# agent/stop_hooks.py
"""
Stop hooks: actions fired when a conversation reaches its final response.

Called from _build_result() after the agent produces a final response
with no pending tool calls. All hooks are fire-and-forget.

Ported from CC's query/stopHooks.ts pattern.
"""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from run_agent import AIAgent

logger = logging.getLogger(__name__)


def run_stop_hooks(
    agent: "AIAgent",
    messages: list,
    final_response: str,
    completed: bool,
    interrupted: bool,
) -> None:
    """Fire all stop hooks. Never raises. Called after final response."""
    if not final_response or interrupted:
        return

    # Hook 1: Emit on_conversation_end plugin hook
    try:
        from hermes_cli.plugins import emit_hook
        emit_hook(
            "on_conversation_end",
            final_response=final_response,
            message_count=len(messages),
            completed=completed,
        )
    except Exception:
        pass

    # Hook 2: Memory extraction (already wired separately via extract_memories)
    # Hook 3: Deal stage transition detection
    _maybe_detect_deal_transition(messages, final_response, agent)

    # Hook 4: Contact update detection
    _maybe_detect_contact_update(messages, final_response, agent)

    # Hook 5: Magic docs update
    try:
        from agent.magic_docs import update_magic_docs_async
        update_magic_docs_async(messages, agent)
    except Exception:
        pass

    # Hook 6: Learning loop — extract reusable skills from this session
    # Runs async in background so user gets their response immediately.
    # Only fires for complex sessions (>= 4 tool calls).
    try:
        from agent.learning_loop import trigger_learning_loop
        trigger_learning_loop(agent, messages, final_response, async_mode=True)
    except Exception:
        pass

    # Hook 7: Finish Sentry session transaction (no-op if Sentry not configured)
    try:
        from agent.sentry_tracing import finish_session
        session_id = getattr(agent, "session_id", "unknown") or "unknown"
        tool_call_count = getattr(agent, "_tool_call_count", 0) or 0
        # Approximate token count from messages
        token_count = sum(
            len(str(m.get("content", ""))) // 4
            for m in (messages or [])
            if isinstance(m, dict)
        )
        finish_session(session_id, token_count=token_count, tool_call_count=tool_call_count)
    except Exception:
        pass


def _maybe_detect_deal_transition(messages: list, final_response: str, agent: "AIAgent") -> None:
    """Detect if a deal stage changed and emit hook."""
    try:
        transition_keywords = [
            "moved to", "progressed to", "advanced to", "stage:",
            "closed won", "closed lost", "proposal sent", "demo scheduled",
        ]
        text = (final_response or "").lower()
        if any(kw in text for kw in transition_keywords):
            from hermes_cli.plugins import emit_hook
            emit_hook("on_deal_stage_transition", response_preview=final_response[:200])
    except Exception:
        pass


def _maybe_detect_contact_update(messages: list, final_response: str, agent: "AIAgent") -> None:
    """Detect if contact information was updated and emit hook."""
    try:
        update_keywords = ["updated", "saved to memory", "noted", "added contact", "new contact"]
        text = (final_response or "").lower()
        if any(kw in text for kw in update_keywords):
            from hermes_cli.plugins import emit_hook
            emit_hook("on_contact_update", response_preview=final_response[:200])
    except Exception:
        pass
