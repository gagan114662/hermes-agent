"""File-write lineage tracking for Hermes.

Every time the agent writes a file, a record is appended to a JSONL log at
``~/.hermes/lineage/YYYYMMDD.jsonl``.  Each record stores:

  - ``ts``         ISO-8601 timestamp
  - ``path``       Absolute path that was written
  - ``goal``       The user goal / task description that triggered the write
  - ``session_id`` Agent session ID (optional)
  - ``model``      Model that made the write (optional)

Public API
----------
  record_write(path, goal, *, session_id="", model="")
      Append a lineage entry (non-blocking; errors are silently swallowed).

  get_lineage(path, *, days=90)
      Return a list of lineage records for *path* (most-recent first).

  get_all_lineage(*, days=1)
      Return all records from today's log (for /costmap-style views).
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_write_lock = threading.Lock()

# ---------------------------------------------------------------------------
# In-memory session task-cost register (for /costmap)
# ---------------------------------------------------------------------------

_cost_lock = threading.Lock()
_session_costs: List[Dict[str, Any]] = []


def record_task_cost(
    label: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    *,
    status: str = "completed",
    duration_seconds: float = 0.0,
    session_id: str = "",
) -> None:
    """Append a task-cost entry to the in-memory register.

    Called by delegate_tool after every child completes.
    """
    try:
        from agent.usage_pricing import CanonicalUsage, estimate_usage_cost
        usage = CanonicalUsage(input_tokens=input_tokens, output_tokens=output_tokens)
        cost_result = estimate_usage_cost(model, usage)
        cost_usd = float(cost_result.amount_usd) if cost_result.amount_usd is not None else None
    except Exception:
        cost_usd = None

    entry: Dict[str, Any] = {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "label": label,
        "model": model or "",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
        "status": status,
        "duration_seconds": duration_seconds,
        "session_id": session_id,
    }
    with _cost_lock:
        _session_costs.append(entry)


def get_session_costs() -> List[Dict[str, Any]]:
    """Return a snapshot of all task-cost entries for this session."""
    with _cost_lock:
        return list(_session_costs)


def clear_session_costs() -> None:
    """Clear the session cost register (e.g. at session start)."""
    with _cost_lock:
        _session_costs.clear()


# ---------------------------------------------------------------------------
# Per-task context registry (task_id → {goal, session_id, model})
# ---------------------------------------------------------------------------

_ctx_lock = threading.Lock()
_task_contexts: Dict[str, Dict[str, str]] = {}


def set_task_context(
    task_id: str,
    goal: str,
    *,
    session_id: str = "",
    model: str = "",
) -> None:
    """Associate a *goal* (and optional session/model) with a *task_id*.

    Called by delegate_tool before spawning each child so that
    write_file_tool can record meaningful lineage.
    """
    with _ctx_lock:
        _task_contexts[task_id] = {
            "goal": (goal or "").strip(),
            "session_id": session_id,
            "model": model,
        }


def get_task_context(task_id: str) -> Dict[str, str]:
    """Return the stored context for *task_id*, or an empty dict."""
    with _ctx_lock:
        return dict(_task_contexts.get(task_id, {}))

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _lineage_dir() -> Path:
    """Return ~/.hermes/lineage/, creating it if needed."""
    from hermes_constants import get_hermes_home
    d = Path(get_hermes_home()) / "lineage"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _log_path(date: Optional[datetime] = None) -> Path:
    d = date or datetime.now(tz=timezone.utc)
    return _lineage_dir() / f"{d.strftime('%Y%m%d')}.jsonl"


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def record_write(
    path: str,
    goal: str = "",
    *,
    task_id: str = "default",
    session_id: str = "",
    model: str = "",
) -> None:
    """Append a lineage entry for *path*.

    If *goal* is empty, falls back to the context registered for *task_id*
    via :func:`set_task_context`.  Silent no-op on any error.
    """
    try:
        ctx = get_task_context(task_id)
        effective_goal = (goal or ctx.get("goal", "")).strip()
        effective_session = session_id or ctx.get("session_id", "")
        effective_model = model or ctx.get("model", "")

        entry: Dict[str, Any] = {
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            "path": str(Path(path).resolve()),
            "goal": effective_goal,
            "session_id": effective_session,
            "model": effective_model,
        }
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        log = _log_path()
        with _write_lock:
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(line)
    except Exception as exc:  # pragma: no cover
        logger.debug("lineage.record_write failed: %s", exc)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def _iter_log_paths(days: int) -> List[Path]:
    """Return log paths for the last *days* days (newest first, existing only)."""
    today = datetime.now(tz=timezone.utc)
    paths = []
    for offset in range(days):
        from datetime import timedelta
        candidate = _log_path(today - timedelta(days=offset))
        if candidate.exists():
            paths.append(candidate)
    return paths


def get_lineage(path: str, *, days: int = 90) -> List[Dict[str, Any]]:
    """Return lineage records for *path*, most-recent first.

    Searches the last *days* daily log files.
    """
    target = str(Path(path).resolve())
    results: List[Dict[str, Any]] = []

    for log in _iter_log_paths(days):
        try:
            for raw in reversed(log.read_text(encoding="utf-8").splitlines()):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if entry.get("path") == target:
                    results.append(entry)
        except Exception as exc:
            logger.debug("lineage.get_lineage error reading %s: %s", log, exc)

    return results  # already in reverse-chronological per file; cross-day ordering maintained


def get_all_lineage(*, days: int = 1) -> List[Dict[str, Any]]:
    """Return all lineage records from the last *days* days, newest first."""
    results: List[Dict[str, Any]] = []

    for log in _iter_log_paths(days):
        try:
            lines = log.read_text(encoding="utf-8").splitlines()
            for raw in reversed(lines):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    results.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue
        except Exception as exc:
            logger.debug("lineage.get_all_lineage error: %s", exc)

    return results
