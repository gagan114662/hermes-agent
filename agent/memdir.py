# agent/memdir.py
"""
Memdir — shared session knowledge base across agents.

Ported from CC's memdir pattern, extended with Hermes-specific features.

While CC's memdir is a simple file directory, Hermes memdir is a structured
in-session knowledge store: agents WRITE discoveries during a task and all
subsequent agents (including parallel ones) can READ them — without
re-discovering what's already known.

This is what makes multi-agent Hermes faster than Claude Code:
  - Agent A explores codebase → writes "uses FastAPI, Python 3.11, pytest"
  - Agents B and C (spawned in parallel) read that immediately
  - No agent re-reads the same files or re-discovers the same facts

Persistence:
  - In-session: in-memory dict (fast, zero I/O)
  - Cross-session: optionally persisted to ~/.hermes/memdir/{session_id}.json
    so resumed sessions don't lose discoveries

Structure per entry:
  key       : str — topic identifier ("tech_stack", "api_endpoints", etc.)
  value     : str — the discovered fact or knowledge
  source    : str — which agent wrote it ("explore", "researcher", etc.)
  ts        : float — unix timestamp
  confidence: float — 0.0–1.0, default 0.8

Usage (from inside delegate_task or any agent):
    from agent.memdir import get_session_memdir
    memdir = get_session_memdir()

    # Write a discovery
    memdir.write("api_base_url", "https://api.example.com/v2", source="explore")

    # Read it later
    url = memdir.read("api_base_url")

    # Dump everything as a prompt injection
    context = memdir.format_for_prompt()
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Entry dataclass
# ---------------------------------------------------------------------------

@dataclass
class MemdirEntry:
    key: str
    value: str
    source: str = "agent"
    ts: float = field(default_factory=time.time)
    confidence: float = 0.8


# ---------------------------------------------------------------------------
# SessionMemdir — the per-session knowledge store
# ---------------------------------------------------------------------------

class SessionMemdir:
    """
    Thread-safe in-session knowledge store.

    Multiple agents (parent + parallel children) share ONE instance
    per session. Children receive the session_id and call
    get_session_memdir(session_id) to get the same instance.
    """

    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self._store: dict[str, MemdirEntry] = {}
        self._lock = threading.RLock()
        self._load_from_disk()

    # ── Write ──────────────────────────────────────────────────────────────

    def write(
        self,
        key: str,
        value: str,
        *,
        source: str = "agent",
        confidence: float = 0.8,
        overwrite: bool = True,
    ) -> bool:
        """
        Write a discovery to the memdir.

        Returns True if written, False if skipped (key exists + overwrite=False).
        """
        if not key or not value:
            return False

        with self._lock:
            if not overwrite and key in self._store:
                return False
            self._store[key] = MemdirEntry(
                key=key,
                value=str(value).strip(),
                source=source,
                ts=time.time(),
                confidence=min(1.0, max(0.0, confidence)),
            )
            logger.debug("memdir[%s]: wrote '%s' from %s", self.session_id, key, source)
            self._persist_async()
            return True

    def write_many(self, entries: dict[str, str], *, source: str = "agent") -> int:
        """Write multiple key→value discoveries at once. Returns count written."""
        count = 0
        for k, v in entries.items():
            if self.write(k, v, source=source):
                count += 1
        return count

    # ── Read ──────────────────────────────────────────────────────────────

    def read(self, key: str) -> Optional[str]:
        """Read a value by key, or None."""
        with self._lock:
            entry = self._store.get(key)
            return entry.value if entry else None

    def read_entry(self, key: str) -> Optional[MemdirEntry]:
        """Read the full entry (includes source, confidence, timestamp)."""
        with self._lock:
            return self._store.get(key)

    def all_keys(self) -> list[str]:
        with self._lock:
            return list(self._store.keys())

    def all_entries(self) -> list[MemdirEntry]:
        with self._lock:
            return list(self._store.values())

    def has(self, key: str) -> bool:
        with self._lock:
            return key in self._store

    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    # ── Prompt injection ──────────────────────────────────────────────────

    def format_for_prompt(
        self,
        *,
        max_entries: int = 30,
        min_confidence: float = 0.5,
    ) -> str:
        """
        Format memdir contents as a system prompt injection.

        Agents call this to inject session knowledge into child prompts
        so children don't re-discover what's already known.

        Example output:
            ## Session Knowledge (from previous agents)
            - tech_stack: FastAPI, Python 3.11, pytest (from: explore)
            - api_base_url: https://api.example.com/v2 (from: researcher)
        """
        with self._lock:
            entries = [
                e for e in self._store.values()
                if e.confidence >= min_confidence
            ]

        if not entries:
            return ""

        # Sort by confidence desc, then timestamp desc
        entries.sort(key=lambda e: (-e.confidence, -e.ts))
        entries = entries[:max_entries]

        lines = ["## Session Knowledge (from earlier agents — use this, don't re-discover)"]
        for e in entries:
            lines.append(f"- **{e.key}**: {e.value}  _(source: {e.source})_")

        return "\n".join(lines)

    def format_compact(self) -> str:
        """One-line summary for logging/display."""
        with self._lock:
            n = len(self._store)
            keys = list(self._store.keys())[:5]
        if not n:
            return "memdir: empty"
        more = f" +{n - 5} more" if n > 5 else ""
        return f"memdir: {n} entries — {', '.join(keys)}{more}"

    # ── Persistence ───────────────────────────────────────────────────────

    def _persist_path(self) -> Path:
        hermes_home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
        d = Path(hermes_home) / "memdir"
        d.mkdir(parents=True, exist_ok=True)
        # Sanitize session_id for use as filename
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in self.session_id)[:64]
        return d / f"{safe_id}.json"

    def _persist_async(self) -> None:
        """Fire-and-forget async persist — never blocks callers."""
        import threading
        t = threading.Thread(target=self._persist, daemon=True)
        t.start()

    def _persist(self) -> None:
        """Write current state to disk."""
        try:
            path = self._persist_path()
            with self._lock:
                data = [asdict(e) for e in self._store.values()]
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.debug("memdir persist failed: %s", exc)

    def _load_from_disk(self) -> None:
        """Load previously persisted entries on startup."""
        try:
            path = self._persist_path()
            if not path.exists():
                return
            data = json.loads(path.read_text(encoding="utf-8"))
            for item in data:
                entry = MemdirEntry(**item)
                self._store[entry.key] = entry
            logger.debug("memdir: loaded %d entries from disk", len(self._store))
        except Exception as exc:
            logger.debug("memdir load failed: %s", exc)


# ---------------------------------------------------------------------------
# Global registry — one SessionMemdir per session_id
# ---------------------------------------------------------------------------

_registry: dict[str, SessionMemdir] = {}
_registry_lock = threading.Lock()


def get_session_memdir(session_id: str = "default") -> SessionMemdir:
    """
    Get or create the SessionMemdir for this session.

    All agents in the same session share the same instance.
    Thread-safe — safe to call from parallel subagent threads.
    """
    with _registry_lock:
        if session_id not in _registry:
            _registry[session_id] = SessionMemdir(session_id)
        return _registry[session_id]


def clear_session_memdir(session_id: str) -> None:
    """Remove a session's memdir from the registry (e.g. on session end)."""
    with _registry_lock:
        _registry.pop(session_id, None)


# ---------------------------------------------------------------------------
# Convenience: inject memdir context into delegate_task calls
# ---------------------------------------------------------------------------

def inject_memdir_context(
    session_id: str,
    existing_context: Optional[str] = None,
) -> str:
    """
    Build a context string that includes current memdir knowledge.

    Used in delegate_tool.py to automatically pass session knowledge
    to all child agents without manual wiring.

    Example:
        context = inject_memdir_context(agent.session_id, user_context)
        delegate_task(goal=goal, context=context, ...)
    """
    memdir = get_session_memdir(session_id)
    memdir_text = memdir.format_for_prompt()

    if not memdir_text:
        return existing_context or ""

    parts = []
    if existing_context:
        parts.append(existing_context)
    parts.append(memdir_text)
    return "\n\n".join(parts)
