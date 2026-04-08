"""
Thread-safe task mailbox for async delegation results.

Usage:
    mailbox = Mailbox()
    handle = mailbox.reserve()          # returns task_handle_id
    mailbox.send(handle, result_dict)   # called by background thread
    result = mailbox.poll(handle)       # None if not ready
    result = mailbox.receive(handle, timeout=30)  # blocks until ready
"""
from __future__ import annotations
import threading
import time
import uuid
from typing import Any, Optional


class Mailbox:
    """A thread-safe store for async task results."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._results: dict[str, Any] = {}
        self._events: dict[str, threading.Event] = {}

    def reserve(self) -> str:
        """Reserve a slot and return a unique task_handle_id."""
        handle = str(uuid.uuid4())[:12]
        with self._lock:
            self._events[handle] = threading.Event()
        return handle

    def send(self, handle: str, result: Any) -> None:
        """Store a result and signal waiters. Called from background thread."""
        with self._lock:
            self._results[handle] = result
            event = self._events.get(handle)
        if event:
            event.set()

    def poll(self, handle: str) -> Optional[Any]:
        """Return result if ready, else None. Non-blocking."""
        with self._lock:
            return self._results.get(handle)

    def receive(self, handle: str, timeout: float = 300) -> Optional[Any]:
        """Block until result is ready or timeout. Returns result or None."""
        event = None
        with self._lock:
            event = self._events.get(handle)
        if event is None:
            return None
        event.wait(timeout=timeout)
        return self.poll(handle)

    def discard(self, handle: str) -> None:
        """Remove a completed handle to free memory."""
        with self._lock:
            self._results.pop(handle, None)
            self._events.pop(handle, None)


# Module-level singleton shared across all agent instances in the process
_global_mailbox = Mailbox()


def get_mailbox() -> Mailbox:
    return _global_mailbox
