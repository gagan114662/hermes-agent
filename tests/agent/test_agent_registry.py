"""Tests for named persistent specialist registry."""
from unittest.mock import MagicMock
from agent.agent_registry import AgentRegistry


def test_register_and_get():
    r = AgentRegistry()
    agent = MagicMock()
    r.register("researcher", agent)
    assert r.get("researcher") is agent


def test_get_nonexistent_returns_none():
    r = AgentRegistry()
    assert r.get("nonexistent") is None


def test_get_or_create_creates_once():
    r = AgentRegistry()
    factory_calls = []

    def factory():
        agent = MagicMock()
        factory_calls.append(agent)
        return agent

    a1 = r.get_or_create("writer", factory)
    a2 = r.get_or_create("writer", factory)
    assert a1 is a2
    assert len(factory_calls) == 1


def test_history_accumulates():
    r = AgentRegistry()
    agent = MagicMock()
    r.register("coder", agent)
    r.append_history("coder", [{"role": "user", "content": "hello"}])
    r.append_history("coder", [{"role": "assistant", "content": "hi"}])
    assert len(r.get_history("coder")) == 2


def test_history_returns_copy():
    """get_history should return a copy, not the internal list."""
    r = AgentRegistry()
    r.register("x", MagicMock())
    r.append_history("x", [{"role": "user", "content": "a"}])
    h = r.get_history("x")
    h.append({"role": "user", "content": "mutated"})
    assert len(r.get_history("x")) == 1


def test_history_for_unregistered_name():
    r = AgentRegistry()
    assert r.get_history("nobody") == []


def test_list_names():
    r = AgentRegistry()
    r.register("a", MagicMock())
    r.register("b", MagicMock())
    assert set(r.list_names()) == {"a", "b"}


def test_clear():
    r = AgentRegistry()
    r.register("x", MagicMock())
    r.clear()
    assert r.list_names() == []
    assert r.get("x") is None


def test_singleton_accessible():
    """Module-level singleton is importable and is an AgentRegistry."""
    from agent.agent_registry import get_registry
    reg = get_registry()
    assert isinstance(reg, AgentRegistry)


def test_register_twice_overwrites():
    """Re-registering a name replaces the agent but preserves history."""
    r = AgentRegistry()
    a1 = MagicMock()
    a2 = MagicMock()
    r.register("writer", a1)
    r.append_history("writer", [{"role": "user", "content": "hi"}])
    r.register("writer", a2)
    assert r.get("writer") is a2
    # History preserved (register doesn't reset it)
    assert len(r.get_history("writer")) == 1
