"""
Learning journal for Hermes Agent — rollback and event log.

Every write to memory or skills is journalled before and after persistence.
A journal entry captures enough state to restore the previous version if the
learning turns out to be wrong or harmful.

Journal file (one JSON line per event):
    $HERMES_HOME/logs/learning_journal.jsonl

Each entry:
    id          UUID for the operation (used for rollback)
    ts          ISO-8601 UTC timestamp
    type        "memory" | "skill"
    action      "add" | "replace" | "remove" | "create" | "edit" | "patch" | "delete"
    target      memory target ("memory" | "user" | "team") or skill name
    quality     quality score at write time (float)
    previous    previous state (full entry list for memory; SKILL.md text for skills)
    current     new state after write
    outcome     "accepted" | "rejected" | "pending"
    error       rejection reason (if outcome == "rejected")

Rollback:
    journal.rollback(entry_id) restores the previous state.
    For memory: rewrites the entries list.
    For skills: restores SKILL.md content (or deletes the skill if it was a create).

Configuration:
    HERMES_JOURNAL_MAX_ENTRIES   max journal lines to keep (default: 500)
                                 Older lines are trimmed on each append.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_MAX_ENTRIES_DEFAULT = 500

_lock = threading.Lock()


# ── Path helpers ──────────────────────────────────────────────────────────────

def _journal_path() -> Path:
    hermes_home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
    log_dir = Path(hermes_home) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "learning_journal.jsonl"


def _max_entries() -> int:
    try:
        return int(os.environ.get("HERMES_JOURNAL_MAX_ENTRIES", _MAX_ENTRIES_DEFAULT))
    except (TypeError, ValueError):
        return _MAX_ENTRIES_DEFAULT


# ── Write helpers ─────────────────────────────────────────────────────────────

def _utc_now() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")


def _append(record: dict) -> None:
    """Append one record; trim file to max_entries."""
    path = _journal_path()
    line = json.dumps(record, ensure_ascii=False, default=str)
    try:
        with _lock:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            _trim(path)
    except Exception as exc:
        logger.warning("learning_journal: write failed: %s", exc)


def _trim(path: Path) -> None:
    """Keep only the last max_entries lines (called under _lock)."""
    max_e = _max_entries()
    try:
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        if len(lines) > max_e:
            path.write_text("".join(lines[-max_e:]), encoding="utf-8")
    except Exception:
        pass


# ── Public API ────────────────────────────────────────────────────────────────

def record_memory_event(
    *,
    action: str,
    target: str,
    previous_entries: list[str],
    current_entries: list[str],
    quality: float,
    outcome: str,
    error: Optional[str] = None,
) -> str:
    """
    Record a memory write event.  Returns the entry ID.

    Args:
        action:           "add" | "replace" | "remove"
        target:           "memory" | "user" | "team"
        previous_entries: entry list BEFORE the write
        current_entries:  entry list AFTER the write (same as previous if rejected)
        quality:          quality score (0.0–1.0)
        outcome:          "accepted" | "rejected"
        error:            rejection reason (if outcome == "rejected")
    """
    entry_id = str(uuid.uuid4())
    record: dict[str, Any] = {
        "id": entry_id,
        "ts": _utc_now(),
        "type": "memory",
        "action": action,
        "target": target,
        "quality": round(quality, 3),
        "previous": previous_entries,
        "current": current_entries,
        "outcome": outcome,
    }
    if error:
        record["error"] = error[:1000]
    _append(record)
    return entry_id


def record_skill_event(
    *,
    action: str,
    name: str,
    previous_content: Optional[str],
    current_content: Optional[str],
    quality: float,
    outcome: str,
    error: Optional[str] = None,
) -> str:
    """
    Record a skill write event.  Returns the entry ID.

    Args:
        action:           "create" | "edit" | "patch" | "delete"
        name:             skill name
        previous_content: SKILL.md text before (None for creates)
        current_content:  SKILL.md text after (None for deletes)
        quality:          quality score
        outcome:          "accepted" | "rejected"
        error:            rejection reason
    """
    entry_id = str(uuid.uuid4())
    record: dict[str, Any] = {
        "id": entry_id,
        "ts": _utc_now(),
        "type": "skill",
        "action": action,
        "target": name,
        "quality": round(quality, 3),
        "previous": previous_content,
        "current": current_content,
        "outcome": outcome,
    }
    if error:
        record["error"] = error[:1000]
    _append(record)
    return entry_id


# ── Rollback ──────────────────────────────────────────────────────────────────

def rollback(entry_id: str) -> dict[str, Any]:
    """
    Restore the state captured before the given journal entry was written.

    For memory: restores the exact entry list to disk.
    For skills: restores SKILL.md content (or removes the skill if it was a create).

    Returns a dict with ``success`` bool and ``message`` or ``error``.
    """
    entry = _find_entry(entry_id)
    if entry is None:
        return {"success": False, "error": f"Journal entry '{entry_id}' not found."}

    if entry.get("outcome") == "rejected":
        return {"success": False, "error": "Entry was already rejected — nothing to roll back."}

    try:
        if entry["type"] == "memory":
            return _rollback_memory(entry)
        elif entry["type"] == "skill":
            return _rollback_skill(entry)
        else:
            return {"success": False, "error": f"Unknown entry type: {entry['type']}"}
    except Exception as exc:
        return {"success": False, "error": f"Rollback failed: {exc}"}


def _rollback_memory(entry: dict) -> dict[str, Any]:
    from tools.memory_tool import MemoryStore, ENTRY_DELIMITER  # noqa: PLC0415
    target = entry["target"]
    previous = entry.get("previous", [])

    store = MemoryStore()
    store.load_from_disk()

    # Write previous state directly (bypass validation — rollback must always work)
    store._set_entries(target, previous)
    store.save_to_disk(target)

    # Record the rollback itself
    record_memory_event(
        action="rollback",
        target=target,
        previous_entries=entry.get("current", []),
        current_entries=previous,
        quality=0.0,
        outcome="accepted",
    )

    return {
        "success": True,
        "message": f"Memory '{target}' rolled back to state before entry {entry['id'][:8]}.",
        "restored_entries": len(previous),
    }


def _rollback_skill(entry: dict) -> dict[str, Any]:
    import shutil  # noqa: PLC0415
    from tools.skill_manager_tool import _find_skill, _atomic_write_text, SKILLS_DIR  # noqa: PLC0415

    name = entry["target"]
    action = entry["action"]
    previous_content = entry.get("previous")
    current_path_entry = _find_skill(name)

    if action == "create":
        # Undo a create → delete the skill directory
        if current_path_entry:
            shutil.rmtree(current_path_entry["path"], ignore_errors=True)
        record_skill_event(
            action="rollback",
            name=name,
            previous_content=None,
            current_content=None,
            quality=0.0,
            outcome="accepted",
        )
        return {"success": True, "message": f"Skill '{name}' removed (create rolled back)."}

    elif action in ("edit", "patch"):
        if previous_content is None:
            return {"success": False, "error": "No previous content captured for this entry."}
        if current_path_entry is None:
            return {"success": False, "error": f"Skill '{name}' no longer exists."}
        skill_md = current_path_entry["path"] / "SKILL.md"
        _atomic_write_text(skill_md, previous_content)
        record_skill_event(
            action="rollback",
            name=name,
            previous_content=entry.get("current"),
            current_content=previous_content,
            quality=0.0,
            outcome="accepted",
        )
        return {"success": True, "message": f"Skill '{name}' rolled back to previous version."}

    elif action == "delete":
        # Undo a delete → restore SKILL.md
        if previous_content is None:
            return {"success": False, "error": "No previous content to restore."}
        skill_dir = SKILLS_DIR / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_md = skill_dir / "SKILL.md"
        _atomic_write_text(skill_md, previous_content)
        record_skill_event(
            action="rollback",
            name=name,
            previous_content=None,
            current_content=previous_content,
            quality=0.0,
            outcome="accepted",
        )
        return {"success": True, "message": f"Skill '{name}' restored (delete rolled back)."}

    return {"success": False, "error": f"Rollback not supported for action '{action}'."}


# ── Query helpers ─────────────────────────────────────────────────────────────

def recent_events(n: int = 50) -> list[dict]:
    """Return the last *n* journal events (most-recent first)."""
    path = _journal_path()
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as fh:
            lines = fh.readlines()
        records: list[dict] = []
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


def _find_entry(entry_id: str) -> Optional[dict]:
    """Scan the journal file for an entry with the given ID."""
    path = _journal_path()
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if record.get("id") == entry_id:
                        return record
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass
    return None
