# agent/sentry_tracing.py
"""
Sentry tracing for Hermes agent trajectories.

What this gives you in Sentry:
  - Every tool call → breadcrumb (full trajectory visible on any error)
  - Tool failures   → captured exceptions with the complete call trail
  - Each session    → a Sentry transaction (when traces enabled)
  - Each tool call  → a span inside that transaction (latency per tool)
  - Self-heal runs  → Sentry events with VERDICT tag + repair details
  - Token budget    → custom Sentry measurement on session finish

Setup (no code changes needed):
    export SENTRY_DSN="https://abc@sentry.io/123"
    export SENTRY_TRACES_SAMPLE_RATE="1.0"   # 0-1, enables performance tracing
    export SENTRY_ENVIRONMENT="production"   # optional, defaults to "development"
    export SENTRY_RELEASE="hermes@1.0.0"     # optional

Importing this module auto-initializes Sentry if SENTRY_DSN is set.
You can also call init_sentry() explicitly with a DSN.

Hook registration is automatic on import — no changes to core agent code needed.
The hooks plug into the tool_hooks pipeline already wired into ToolExecutor.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy Sentry SDK access — never hard-crashes if sentry-sdk is not installed
# ---------------------------------------------------------------------------

def _sentry():
    """Return the sentry_sdk module or None if not installed."""
    try:
        import sentry_sdk
        return sentry_sdk
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Session-level transaction tracking
# ---------------------------------------------------------------------------

# session_id → sentry Transaction (only when traces_sample_rate > 0)
_session_transactions: dict[str, Any] = {}
_sessions_lock = threading.Lock()

# Thread-local storage for the current span (pre→post/failure handoff)
_tls = threading.local()


def _get_or_create_transaction(session_id: str, model: str = "unknown") -> Optional[Any]:
    """
    Get or lazily create a Sentry transaction for a session.
    Returns None if Sentry isn't configured or traces are disabled.
    """
    sdk = _sentry()
    if not sdk:
        return None

    with _sessions_lock:
        if session_id in _session_transactions:
            return _session_transactions[session_id]

        # Only create a transaction if traces_sample_rate is configured
        try:
            client = sdk.get_client()
            if not client or not getattr(client.options, "traces_sample_rate", 0):
                return None
        except Exception:
            return None

        txn = sdk.start_transaction(
            op="agent.session",
            name=f"hermes/{model}",
            sampled=True,
        )
        txn.set_tag("session_id", session_id)
        txn.set_tag("model", model)
        _session_transactions[session_id] = txn
        return txn


def finish_session(session_id: str, *, token_count: int = 0, tool_call_count: int = 0) -> None:
    """
    Finish the Sentry transaction for a session.
    Call this at session end (e.g. from stop_hooks).
    """
    sdk = _sentry()
    if not sdk:
        return

    with _sessions_lock:
        txn = _session_transactions.pop(session_id, None)

    if txn is not None:
        if token_count:
            txn.set_measurement("token_count", token_count, unit="none")
        if tool_call_count:
            txn.set_measurement("tool_call_count", tool_call_count, unit="none")
        try:
            txn.finish()
        except Exception as exc:
            logger.debug("sentry_tracing: finish_session error: %s", exc)


# ---------------------------------------------------------------------------
# Sentry init
# ---------------------------------------------------------------------------

_initialized = False


def init_sentry(
    dsn: Optional[str] = None,
    *,
    environment: Optional[str] = None,
    release: Optional[str] = None,
    traces_sample_rate: Optional[float] = None,
) -> bool:
    """
    Initialize Sentry SDK.  Safe to call multiple times.

    All params fall back to environment variables:
      SENTRY_DSN, SENTRY_ENVIRONMENT, SENTRY_RELEASE, SENTRY_TRACES_SAMPLE_RATE

    Returns True if Sentry was initialized successfully.
    """
    global _initialized
    sdk = _sentry()
    if not sdk:
        logger.debug("sentry_tracing: sentry-sdk not installed, skipping init")
        return False

    dsn = dsn or os.environ.get("SENTRY_DSN", "")
    if not dsn:
        return False

    if _initialized:
        return True

    environment = environment or os.environ.get("SENTRY_ENVIRONMENT", "development")
    release = release or os.environ.get("SENTRY_RELEASE")
    try:
        rate_str = os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0")
        traces_sample_rate = traces_sample_rate if traces_sample_rate is not None else float(rate_str)
    except (ValueError, TypeError):
        traces_sample_rate = 0.0

    try:
        sdk.init(
            dsn=dsn,
            environment=environment,
            release=release,
            traces_sample_rate=traces_sample_rate,
            # Don't let Sentry slow down the agent loop
            max_breadcrumbs=200,
            attach_stacktrace=True,
            # Integrations: no web framework noise
            default_integrations=False,
            integrations=[],
        )
        _initialized = True
        logger.info("sentry_tracing: initialized (env=%s, traces=%.2f)", environment, traces_sample_rate)
        return True
    except Exception as exc:
        logger.warning("sentry_tracing: init failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Tool-level hooks — wired into tool_hooks pipeline
# ---------------------------------------------------------------------------

def _extract_session_context(agent: Any) -> tuple[str, str]:
    """Extract (session_id, model) from an agent instance."""
    session_id = getattr(agent, "session_id", None) or "unknown"
    model = getattr(agent, "model", None) or "unknown"
    return str(session_id), str(model)


def _sentry_pre_hook(ctx: "ToolHookContext") -> "ToolHookResult":  # type: ignore[name-defined]
    """
    PreToolUse: add breadcrumb + start a span for this tool call.
    Stores the span in thread-local so the post/failure hook can finish it.
    """
    from agent.tool_hooks import ToolHookResult

    sdk = _sentry()
    if not sdk:
        return ToolHookResult()

    session_id, model = _extract_session_context(ctx.agent)

    # ── Breadcrumb (always, even without traces) ──────────────────────────
    # Truncate args to avoid huge payloads
    try:
        args_preview = {
            k: (str(v)[:120] + "…" if len(str(v)) > 120 else v)
            for k, v in (ctx.tool_input or {}).items()
        }
    except Exception:
        args_preview = {}

    try:
        sdk.add_breadcrumb(
            category="tool.call",
            message=f"→ {ctx.tool_name}",
            data={
                "tool": ctx.tool_name,
                "session_id": session_id[:16],
                **args_preview,
            },
            level="info",
        )
    except Exception:
        pass

    # ── Span (only when transaction exists) ──────────────────────────────
    _tls.span_start = time.monotonic()
    _tls.span = None

    try:
        txn = _get_or_create_transaction(session_id, model)
        if txn is not None:
            span = txn.start_child(
                op=f"tool.{ctx.tool_name}",
                description=ctx.tool_name,
            )
            span.set_tag("tool", ctx.tool_name)
            span.set_tag("session_id", session_id[:16])
            _tls.span = span
    except Exception as exc:
        logger.debug("sentry_tracing pre-hook span error: %s", exc)

    return ToolHookResult()


def _sentry_post_hook(ctx: "ToolHookContext") -> "ToolHookResult":  # type: ignore[name-defined]
    """
    PostToolUse: finish the span with success status + result size.
    """
    from agent.tool_hooks import ToolHookResult

    sdk = _sentry()
    if not sdk:
        return ToolHookResult()

    duration_ms = (time.monotonic() - getattr(_tls, "span_start", time.monotonic())) * 1000

    # ── Finish span ───────────────────────────────────────────────────────
    span = getattr(_tls, "span", None)
    if span is not None:
        try:
            result_len = len(str(ctx.result or ""))
            span.set_data("result_bytes", result_len)
            span.set_data("duration_ms", round(duration_ms, 1))
            span.set_status("ok")
            span.finish()
        except Exception as exc:
            logger.debug("sentry_tracing post-hook span error: %s", exc)
        finally:
            _tls.span = None

    # ── Success breadcrumb ────────────────────────────────────────────────
    try:
        sdk.add_breadcrumb(
            category="tool.result",
            message=f"← {ctx.tool_name} ({round(duration_ms)}ms)",
            data={"tool": ctx.tool_name, "duration_ms": round(duration_ms, 1)},
            level="info",
        )
    except Exception:
        pass

    return ToolHookResult()


def _sentry_failure_hook(ctx: "ToolHookContext") -> "ToolHookResult":  # type: ignore[name-defined]
    """
    PostToolUseFailure: capture the exception in Sentry with full trajectory.
    """
    from agent.tool_hooks import ToolHookResult

    sdk = _sentry()
    if not sdk:
        return ToolHookResult()

    session_id, model = _extract_session_context(ctx.agent)
    duration_ms = (time.monotonic() - getattr(_tls, "span_start", time.monotonic())) * 1000

    # ── Finish span as failed ─────────────────────────────────────────────
    span = getattr(_tls, "span", None)
    if span is not None:
        try:
            span.set_status("internal_error")
            span.set_data("duration_ms", round(duration_ms, 1))
            span.finish()
        except Exception:
            pass
        finally:
            _tls.span = None

    # ── Capture exception ─────────────────────────────────────────────────
    exc = ctx.error
    if exc is not None:
        try:
            with sdk.push_scope() as scope:
                scope.set_tag("tool", ctx.tool_name)
                scope.set_tag("session_id", session_id[:16])
                scope.set_tag("model", model)
                scope.set_context("tool_call", {
                    "tool_name": ctx.tool_name,
                    "args": {k: str(v)[:200] for k, v in (ctx.tool_input or {}).items()},
                    "duration_ms": round(duration_ms, 1),
                    "session_id": session_id,
                })
                sdk.capture_exception(exc)
        except Exception as capture_err:
            logger.debug("sentry_tracing failure-hook capture error: %s", capture_err)

    return ToolHookResult()


# ---------------------------------------------------------------------------
# Self-heal verdict reporting
# ---------------------------------------------------------------------------

def capture_heal_verdict(
    verdict: str,
    *,
    session_id: str = "unknown",
    task_summary: str = "",
    issues_found: int = 0,
    repairs_made: int = 0,
) -> None:
    """
    Send a self-heal verdict event to Sentry.

    verdict: "PASS" | "FAIL" | "PARTIAL"
    """
    sdk = _sentry()
    if not sdk:
        return

    try:
        level = "info" if verdict == "PASS" else ("warning" if verdict == "PARTIAL" else "error")
        with sdk.push_scope() as scope:
            scope.set_tag("verdict", verdict)
            scope.set_tag("session_id", session_id[:16])
            scope.set_level(level)
            scope.set_context("self_heal", {
                "verdict": verdict,
                "task_summary": task_summary[:300],
                "issues_found": issues_found,
                "repairs_made": repairs_made,
            })
            sdk.capture_message(
                f"[self-heal] {verdict} — {task_summary[:80] or 'no summary'}",
                level=level,
            )
    except Exception as exc:
        logger.debug("sentry_tracing capture_heal_verdict error: %s", exc)


# ---------------------------------------------------------------------------
# Auto-registration on import
# ---------------------------------------------------------------------------

def _register_hooks() -> None:
    """Register Sentry hooks into the tool_hooks pipeline."""
    try:
        from agent.tool_hooks import register_pre_hook, register_post_hook, register_failure_hook
        register_pre_hook(_sentry_pre_hook)
        register_post_hook(_sentry_post_hook)
        register_failure_hook(_sentry_failure_hook)
        logger.debug("sentry_tracing: hooks registered")
    except Exception as exc:
        logger.debug("sentry_tracing: hook registration failed: %s", exc)


# Auto-init from environment on import
try:
    if os.environ.get("SENTRY_DSN"):
        init_sentry()
        _register_hooks()
    else:
        # Register hooks anyway so they're ready if init_sentry() is called later
        _register_hooks()
except Exception as _auto_init_err:
    logger.debug("sentry_tracing: auto-init error: %s", _auto_init_err)
