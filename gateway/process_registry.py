# gateway/process_registry.py
"""
ProcessRegistry — maps session IDs to live agent subprocess handles.

Each active session gets one long-running `hermes agent serve --transport stdio`
subprocess. The registry keeps them alive between messages so session memory
is preserved, and reaps them on expiry or explicit removal.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ProcessEntry:
    process: asyncio.subprocess.Process
    created_at: float = field(default_factory=time.monotonic)
    last_used: float = field(default_factory=time.monotonic)


class ProcessRegistry:
    """Thread-safe (asyncio) registry of session_id → subprocess."""

    def __init__(self, ttl_seconds: int = 3600):
        self._entries: Dict[str, ProcessEntry] = {}
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()

    def register(self, session_id: str, process) -> None:
        self._entries[session_id] = ProcessEntry(process=process)

    def get(self, session_id: str) -> Optional[asyncio.subprocess.Process]:
        entry = self._entries.get(session_id)
        if entry is None:
            return None
        entry.last_used = time.monotonic()
        return entry.process

    def remove(self, session_id: str) -> None:
        self._entries.pop(session_id, None)

    async def spawn(self, session_id: str, hermes_bin: str = "hermes") -> asyncio.subprocess.Process:
        """Spawn a new agent serve process for this session."""
        async with self._lock:
            existing = self.get(session_id)
            if existing and existing.returncode is None:
                return existing

            proc = await asyncio.create_subprocess_exec(
                hermes_bin, "agent", "serve", "--transport", "stdio",
                "--session-id", session_id,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self.register(session_id, proc)
            logger.info("Spawned agent process pid=%d for session=%s", proc.pid, session_id)
            return proc

    async def sweep_expired(self) -> int:
        """Reap processes idle longer than TTL. Returns count reaped."""
        now = time.monotonic()
        expired = [
            sid for sid, entry in self._entries.items()
            if now - entry.last_used > self._ttl
        ]
        for sid in expired:
            proc = self._entries[sid].process
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    proc.kill()
            self.remove(sid)
            logger.info("Reaped expired agent process for session=%s", sid)
        return len(expired)
