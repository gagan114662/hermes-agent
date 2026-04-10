# agent/tool_hooks.py
"""
Pre/Post tool use hooks — per-call interception pipeline.

Ported from CC's src/services/tools/toolHooks.ts pattern.

Every tool call in ToolExecutor passes through:
  run_pre_hooks()  → execute tool → run_post_hooks()  (or run_failure_hooks())

Hook results can:
  - blocking_error        : cancel the tool call entirely, return error to model
  - updated_input         : rewrite the tool's args before execution
  - message               : inject a message into the next turn
  - prevent_continuation  : stop the agent loop after this tool
  - additional_context    : append text to ephemeral system prompt for next call

Usage:
    # Register a hook at import time (module level):
    from agent.tool_hooks import register_pre_hook, ToolHookContext, ToolHookResult

    def my_hook(ctx: ToolHookContext) -> ToolHookResult:
        if ctx.tool_name == "terminal" and "rm -rf /" in ctx.tool_input.get("command", ""):
            return ToolHookResult(blocking_error="Refusing to nuke the filesystem.")
        return ToolHookResult()

    register_pre_hook(my_hook)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class ToolHookResult:
    """Return value from a hook. Set only the fields you need."""

    # Block the tool call — return this string as the tool result instead of running the tool.
    blocking_error: Optional[str] = None

    # Rewrite the tool's input args before execution.
    updated_input: Optional[dict] = None

    # Inject a synthetic message into the conversation after this turn.
    message: Optional[str] = None

    # Stop the agent loop after this tool completes.
    prevent_continuation: bool = False

    # Append text to the agent's ephemeral system prompt for the next call only.
    additional_context: Optional[str] = None


@dataclass
class ToolHookContext:
    """Context passed to every hook."""

    tool_name: str
    tool_input: dict

    # Populated only for PostToolUse / FailureHooks:
    result: Optional[str] = None
    error: Optional[Exception] = None

    # Reference to the running AIAgent (may be None in tests).
    agent: Any = None


# ---------------------------------------------------------------------------
# Global hook registries
# ---------------------------------------------------------------------------

_pre_hooks:     list[Callable[[ToolHookContext], ToolHookResult]] = []
_post_hooks:    list[Callable[[ToolHookContext], ToolHookResult]] = []
_failure_hooks: list[Callable[[ToolHookContext], ToolHookResult]] = []


def register_pre_hook(fn: Callable[[ToolHookContext], ToolHookResult]) -> None:
    """Register a PreToolUse hook. Called before the tool executes."""
    _pre_hooks.append(fn)


def register_post_hook(fn: Callable[[ToolHookContext], ToolHookResult]) -> None:
    """Register a PostToolUse hook. Called after the tool succeeds."""
    _post_hooks.append(fn)


def register_failure_hook(fn: Callable[[ToolHookContext], ToolHookResult]) -> None:
    """Register a PostToolUseFailure hook. Called when the tool raises."""
    _failure_hooks.append(fn)


# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------

def run_pre_hooks(ctx: ToolHookContext) -> ToolHookResult:
    """
    Run all PreToolUse hooks in registration order.
    First blocking_error short-circuits — remaining hooks are skipped.
    updated_input is accumulated: each hook sees the latest rewritten args.
    """
    combined = ToolHookResult()
    for hook in _pre_hooks:
        try:
            result = hook(ctx)
            if result is None:
                continue
            if result.blocking_error:
                return result                   # short-circuit on first block
            if result.updated_input:
                ctx.tool_input = result.updated_input
                combined.updated_input = result.updated_input
            if result.message:
                combined.message = ((combined.message or "") + "\n" + result.message).strip()
            if result.additional_context:
                combined.additional_context = (
                    (combined.additional_context or "") + "\n" + result.additional_context
                ).strip()
        except Exception as exc:
            logger.warning("PreToolUse hook %s raised: %s", getattr(hook, "__name__", hook), exc)
    return combined


def run_post_hooks(ctx: ToolHookContext) -> ToolHookResult:
    """
    Run all PostToolUse hooks in registration order.
    Collects messages and additional_context from all hooks.
    First prevent_continuation wins.
    """
    combined = ToolHookResult()
    for hook in _post_hooks:
        try:
            result = hook(ctx)
            if result is None:
                continue
            if result.prevent_continuation:
                combined.prevent_continuation = True
            if result.message:
                combined.message = ((combined.message or "") + "\n" + result.message).strip()
            if result.additional_context:
                combined.additional_context = (
                    (combined.additional_context or "") + "\n" + result.additional_context
                ).strip()
        except Exception as exc:
            logger.warning("PostToolUse hook %s raised: %s", getattr(hook, "__name__", hook), exc)
    return combined


def run_failure_hooks(ctx: ToolHookContext) -> ToolHookResult:
    """Run all PostToolUseFailure hooks. Fire-and-forget, never raises."""
    combined = ToolHookResult()
    for hook in _failure_hooks:
        try:
            result = hook(ctx)
            if result and result.message:
                combined.message = ((combined.message or "") + "\n" + result.message).strip()
        except Exception as exc:
            logger.warning("FailureHook %s raised: %s", getattr(hook, "__name__", hook), exc)
    return combined


# ---------------------------------------------------------------------------
# Built-in hooks — registered at module load
# ---------------------------------------------------------------------------

# ── 1. Bash / terminal safety pre-hook ──────────────────────────────────────
_DANGEROUS_PATTERNS = [
    (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f\b",        "recursive force-delete (rm -rf)"),
    (r"\brm\s+-[a-zA-Z]*f[a-zA-Z]*r\b",        "recursive force-delete (rm -fr)"),
    (r":\s*\(\s*\)\s*\{[^}]*\}\s*;?\s*:\s*&",  "fork bomb"),
    (r"\bdd\b.*\bof=/dev/(s?d[a-z]|nvme)",     "disk overwrite (dd to block device)"),
    (r"\bmkfs\b",                               "filesystem format (mkfs)"),
    (r"\bshred\b.*(-[unz]|--iterations)",       "shred with wipe flags"),
    # Secret exfil patterns
    (r"\bcurl\b[^|]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)\b",
     "potential secret exfiltration via curl"),
    (r"\bwget\b[^|]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)\b",
     "potential secret exfiltration via wget"),
]

_COMPILED_DANGEROUS = [
    (re.compile(pat, re.IGNORECASE), label) for pat, label in _DANGEROUS_PATTERNS
]

_TERMINAL_TOOL_NAMES = {"terminal", "bash", "shell", "run_command", "execute"}


def _bash_safety_pre_hook(ctx: ToolHookContext) -> ToolHookResult:
    """Block obviously destructive commands before they reach the shell."""
    if ctx.tool_name not in _TERMINAL_TOOL_NAMES:
        return ToolHookResult()

    command = ctx.tool_input.get("command", "") or ctx.tool_input.get("cmd", "")
    if not command:
        return ToolHookResult()

    for pattern, label in _COMPILED_DANGEROUS:
        if pattern.search(command):
            logger.warning("bash_safety_pre_hook blocked: %s — matched: %s", command[:80], label)
            return ToolHookResult(
                blocking_error=(
                    f"Command blocked by safety policy ({label}). "
                    "If you genuinely need this, ask the user to run it manually."
                )
            )
    return ToolHookResult()


register_pre_hook(_bash_safety_pre_hook)


# ── 2. Skill tool-restriction pre-hook ──────────────────────────────────────

def _skill_tool_restriction_pre_hook(ctx: ToolHookContext) -> ToolHookResult:
    """
    Enforce per-skill tool allowlists/blocklists.

    When a skill is active (agent._active_skill_allowed_tools or
    agent._active_skill_blocked_tools is set), block tools that are
    outside the skill's declared constraints.
    """
    agent = ctx.agent
    if agent is None:
        return ToolHookResult()

    allowed = getattr(agent, "_active_skill_allowed_tools", None) or []
    blocked = getattr(agent, "_active_skill_blocked_tools", None) or []

    if blocked and ctx.tool_name in blocked:
        return ToolHookResult(
            blocking_error=(
                f"Tool '{ctx.tool_name}' is blocked by the active skill. "
                f"Blocked tools: {blocked}"
            )
        )
    if allowed and ctx.tool_name not in allowed:
        return ToolHookResult(
            blocking_error=(
                f"Tool '{ctx.tool_name}' is not in the active skill's allowedTools. "
                f"Allowed: {allowed}"
            )
        )
    return ToolHookResult()


register_pre_hook(_skill_tool_restriction_pre_hook)


# ── 3. Memory-write post-hook — incremental extraction ─────────────────────

_WRITE_TOOL_NAMES = {"write_file", "patch", "append_file", "create_file"}


def _memory_extraction_post_hook(ctx: ToolHookContext) -> ToolHookResult:
    """
    After a file write, opportunistically extract memories.
    Moves extraction from stop_hooks (end-of-conversation) to per-write
    so memory is updated incrementally during long agentic runs.
    """
    if ctx.tool_name not in _WRITE_TOOL_NAMES:
        return ToolHookResult()

    agent = ctx.agent
    if agent is None:
        return ToolHookResult()

    try:
        from agent.extract_memories import extract_memories_async
        messages = getattr(agent, "messages", None) or getattr(agent, "_messages", [])
        extract_memories_async(messages, agent)
    except Exception as exc:
        logger.debug("memory_extraction_post_hook: %s", exc)

    return ToolHookResult()


register_post_hook(_memory_extraction_post_hook)


# ── 4. Token budget injection post-hook ─────────────────────────────────────

def _token_budget_post_hook(ctx: ToolHookContext) -> ToolHookResult:
    """
    After each tool call, check remaining context and inject a warning
    into the ephemeral system prompt so the model knows to wrap up.
    Ported from CC's dynamic prompt suffix pattern.
    """
    agent = ctx.agent
    if agent is None:
        return ToolHookResult()

    try:
        remaining = getattr(agent, "_remaining_context_tokens", None)
        if remaining is None:
            return ToolHookResult()

        if remaining < 4000:
            return ToolHookResult(
                prevent_continuation=True,
                message=(
                    "[CONTEXT CRITICAL] Fewer than 4 000 tokens remaining. "
                    "Stop tool use immediately and deliver your final answer now."
                )
            )
        if remaining < 12000:
            return ToolHookResult(
                additional_context=(
                    f"⚠️ Context warning: only {remaining:,} tokens remain. "
                    "Wrap up tool calls and deliver your answer soon."
                )
            )
    except Exception as exc:
        logger.debug("token_budget_post_hook: %s", exc)

    return ToolHookResult()


register_post_hook(_token_budget_post_hook)
