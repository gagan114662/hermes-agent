# agent/agent_registry.py
"""
Named agent registry — session-scoped specialist pool.

Allows naming agents (e.g., "researcher", "writer") and reusing them
across multiple delegation calls. Named agents retain their conversation
history, making them true persistent specialists.

Usage:
    registry = get_registry()
    agent = registry.get_or_create("researcher", factory_fn)
    registry.message("researcher", "Now look at the competitor pricing too")
"""
from __future__ import annotations
import threading
import logging
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from run_agent import AIAgent

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Session-scoped pool of named specialist agents."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._agents: dict[str, "AIAgent"] = {}
        self._histories: dict[str, list] = {}  # name → message history

    def get(self, name: str) -> Optional["AIAgent"]:
        with self._lock:
            return self._agents.get(name)

    def register(self, name: str, agent: "AIAgent") -> None:
        with self._lock:
            self._agents[name] = agent
            if name not in self._histories:
                self._histories[name] = []

    def get_or_create(self, name: str, factory: Callable[[], "AIAgent"]) -> "AIAgent":
        with self._lock:
            if name not in self._agents:
                self._agents[name] = factory()
                self._histories[name] = []
                logger.debug("agent_registry: created specialist %r", name)
            return self._agents[name]

    def get_history(self, name: str) -> list:
        with self._lock:
            return list(self._histories.get(name, []))

    def append_history(self, name: str, messages: list) -> None:
        with self._lock:
            if name not in self._histories:
                self._histories[name] = []
            self._histories[name].extend(messages)

    def list_names(self) -> list[str]:
        with self._lock:
            return list(self._agents.keys())

    def clear(self) -> None:
        with self._lock:
            self._agents.clear()
            self._histories.clear()


# Process-level singleton
_global_registry = AgentRegistry()


def get_registry() -> AgentRegistry:
    return _global_registry
