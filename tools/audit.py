"""
Audit log for Hermes Agent tool invocations.

Every tool call is written as a JSON line to:
    $HERMES_HOME/logs/audit.jsonl   (default)

Each record contains:
    ts          ISO-8601 UTC timestamp
    tool        tool name
    user_id     user identifier (set via set_audit_context() at request ingress)
    platform    messaging platform (telegram, discord, cli, …)
    session_id  session / task_id
    args        sanitized copy of the tool arguments (secrets redacted)
    outcome     "ok" | "error" | "suppressed"
    duration_ms wall-clock milliseconds for the call

Usage (from the gateway or CLI before running the agent turn):
    from tools.audit import set_audit_context, clear_audit_context
    set_audit_context(user_id="u123", platform="telegram", session_id="s456")
    try:
        ...  # run agent turn
    finally:
        clear_audit_context()

The registry calls record_tool_call() automatically — no per-tool changes needed.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Thread-local request context ──────────────────────────────────────────────

_ctx = threading.local()


def set_audit_context(
    *,
    user_id: str = "",
    platform: str = "",
    session_id: str = "",
) -> None:
    """Set per-request audit context (call at message-ingress time)."""
    _ctx.user_id = user_id
    _ctx.platform = platform
    _ctx.session_id = session_id


def clear_audit_context() -> None:
    """Clear audit context at end of request."""
    _ctx.user_id = ""
    _ctx.platform = ""
    _ctx.session_id = ""


def get_audit_context() -> dict:
    return {
        "user_id": getattr(_ctx, "user_id", ""),
        "platform": getattr(_ctx, "platform", ""),
        "session_id": getattr(_ctx, "session_id", ""),
    }


# ── Log file setup ─────────────────────────────────────────────────────────────

def _audit_log_path() -> Path:
    hermes_home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
    log_dir = Path(hermes_home) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "audit.jsonl"


_log_lock = threading.Lock()


# ── Secret / PII scrubbing ─────────────────────────────────────────────────────

# Patterns for values that should be redacted from audit args.
# Only values assigned to these keys are scrubbed; content is not scanned.
_SENSITIVE_ARG_KEYS = re.compile(
    r"(key|token|secret|password|passwd|pwd|api_key|auth|credential|dsn|"
    r"private_key|access_key|refresh_token|bearer|authorization)",
    re.IGNORECASE,
)

_MAX_ARG_VALUE_LEN = 500   # truncate long strings to avoid log bloat


def _scrub_args(args: dict) -> dict:
    """Return a copy of args with sensitive values redacted."""
    if not isinstance(args, dict):
        return {}
    result = {}
    for k, v in args.items():
        if _SENSITIVE_ARG_KEYS.search(str(k)):
            result[k] = "<REDACTED>"
        elif isinstance(v, str) and len(v) > _MAX_ARG_VALUE_LEN:
            result[k] = v[:_MAX_ARG_VALUE_LEN] + "…"
        elif isinstance(v, dict):
            result[k] = _scrub_args(v)
        elif isinstance(v, list):
            result[k] = [
                _scrub_args(i) if isinstance(i, dict) else i
                for i in v[:50]          # cap list length
            ]
        else:
            result[k] = v
    return result


# ── Core write ─────────────────────────────────────────────────────────────────

def record_tool_call(
    *,
    tool: str,
    args: dict,
    outcome: str,
    duration_ms: float,
    error: str | None = None,
) -> None:
    """
    Append one audit record to the audit log.

    This is called automatically by tools/registry.py — you do not need to
    call it from individual tool handlers.
    """
    ctx = get_audit_context()
    record: dict[str, Any] = {
        "ts": _utc_now(),
        "tool": tool,
        "user_id": ctx["user_id"],
        "platform": ctx["platform"],
        "session_id": ctx["session_id"],
        "args": _scrub_args(args),
        "outcome": outcome,
        "duration_ms": round(duration_ms, 2),
    }
    if error:
        record["error"] = error[:500]

    line = json.dumps(record, ensure_ascii=False, default=str)
    try:
        path = _audit_log_path()
        with _log_lock:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except Exception as exc:
        # Never let audit logging crash the tool execution path.
        logger.warning("audit: failed to write record: %s", exc)


# ── Query helpers (for the health endpoint and tests) ──────────────────────────

def recent_records(n: int = 100) -> list[dict]:
    """Return the last *n* audit records (most-recent first)."""
    path = _audit_log_path()
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as fh:
            lines = fh.readlines()
        records = []
        for line in reversed(lines[-max(n * 2, 200):]):
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
                if len(records) >= n:
                    break
        return records
    except Exception:
        return []


# ── Internal helpers ───────────────────────────────────────────────────────────

def _utc_now() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")
