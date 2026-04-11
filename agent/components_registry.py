"""Components Registry — provenance tracking for installed Hermes skills.

Every skill that is created via ``/skillnew`` or installed from a
community marketplace is registered here with full provenance metadata.

Storage
-------
One JSONL file per installation event at ``~/.hermes/components.jsonl``.
Each line is a JSON record with the following fields:

  id           str   kebab-case skill name  (e.g. "proposal-writer")
  version      str   semver or "local"
  source       str   "local" | "community" | "git" | "url"
  origin       str   URL / git remote / "" for locally authored skills
  author       str   author name from SKILL.md front-matter, or ""
  description  str   short description from SKILL.md front-matter, or ""
  installed_at str   ISO-8601 UTC timestamp
  path         str   absolute path to the skill's SKILL.md
  checksum     str   SHA-256 of SKILL.md contents at install time

Public API
----------
  register_skill(skill_id, path, *, source, origin, version, author,
                 description)  → None
      Add or update a registry entry.

  get_provenance(skill_id)  → dict | None
      Return the latest registry entry for *skill_id*, or None.

  list_installed()  → List[dict]
      All registered skills, newest-first, de-duped by id.

  unregister_skill(skill_id)  → bool
      Append a tombstone record; returns True if the skill was found.
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _registry_path() -> Path:
    from hermes_constants import get_hermes_home
    return Path(get_hermes_home()) / "components.jsonl"


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _checksum(path: Path) -> str:
    """Return the SHA-256 hex digest of *path*'s contents, or '' on error."""
    try:
        data = path.read_bytes()
        return hashlib.sha256(data).hexdigest()
    except Exception:
        return ""


def _append_record(record: Dict[str, Any]) -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with _lock:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line)


def _read_all_records() -> List[Dict[str, Any]]:
    path = _registry_path()
    if not path.exists():
        return []
    records: List[Dict[str, Any]] = []
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                records.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    except Exception:
        pass
    return records


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def register_skill(
    skill_id: str,
    path: str,
    *,
    source: str = "local",
    origin: str = "",
    version: str = "local",
    author: str = "",
    description: str = "",
) -> None:
    """Register (or update) provenance for a skill.

    ``source`` should be one of: ``"local"``, ``"community"``,
    ``"git"``, ``"url"``.
    """
    skill_path = Path(path)
    record: Dict[str, Any] = {
        "id": skill_id,
        "version": version or "local",
        "source": source or "local",
        "origin": origin or "",
        "author": author or "",
        "description": description or "",
        "installed_at": _now_iso(),
        "path": str(skill_path.resolve()),
        "checksum": _checksum(skill_path),
        "_deleted": False,
    }
    _append_record(record)


def get_provenance(skill_id: str) -> Optional[Dict[str, Any]]:
    """Return the latest registry entry for *skill_id*, or ``None``."""
    records = _read_all_records()
    # Iterate in reverse to get the latest record first
    for rec in reversed(records):
        if rec.get("id") == skill_id:
            if rec.get("_deleted"):
                return None
            return dict(rec)
    return None


def list_installed() -> List[Dict[str, Any]]:
    """Return all currently installed skills, newest-first, de-duped by id."""
    records = _read_all_records()
    seen: Dict[str, Dict[str, Any]] = {}
    # Walk newest-first so the first hit per id wins
    for rec in reversed(records):
        sid = rec.get("id", "")
        if not sid or sid in seen:
            continue
        if rec.get("_deleted"):
            # Mark as deleted so earlier records are ignored
            seen[sid] = {"_deleted": True, "id": sid}
        else:
            seen[sid] = dict(rec)

    return [v for v in seen.values() if not v.get("_deleted")]


def unregister_skill(skill_id: str) -> bool:
    """Append a tombstone record for *skill_id*.  Returns True if found."""
    existing = get_provenance(skill_id)
    if existing is None:
        return False
    _append_record({
        "id": skill_id,
        "_deleted": True,
        "installed_at": _now_iso(),
    })
    return True


# ---------------------------------------------------------------------------
# Auto-register helper (called from _handle_skillnew after creation)
# ---------------------------------------------------------------------------

def try_auto_register(skill_id: str, skills_base_dir: Optional[str] = None) -> bool:
    """Try to register a freshly created skill from ``~/.hermes/skills/<id>/SKILL.md``.

    Returns True on success, False if the SKILL.md does not yet exist.
    Parses author + description from the YAML front-matter when available.
    """
    from hermes_constants import get_hermes_home
    base = Path(skills_base_dir) if skills_base_dir else Path(get_hermes_home()) / "skills"
    skill_path = base / skill_id / "SKILL.md"
    if not skill_path.exists():
        return False

    author = ""
    description = ""
    version = "local"
    try:
        content = skill_path.read_text(encoding="utf-8")
        # Simple front-matter parser — avoid heavy yaml dependency
        if content.startswith("---"):
            end = content.find("\n---", 3)
            if end != -1:
                front = content[3:end]
                for line in front.splitlines():
                    if line.startswith("author:"):
                        author = line.split(":", 1)[1].strip().strip('"\'')
                    elif line.startswith("version:"):
                        version = line.split(":", 1)[1].strip().strip('"\'')
                    elif line.startswith("description:"):
                        description = line.split(":", 1)[1].strip().strip('"\'>-').strip()
    except Exception:
        pass

    register_skill(
        skill_id,
        str(skill_path),
        source="local",
        origin="",
        version=version,
        author=author,
        description=description,
    )
    return True
