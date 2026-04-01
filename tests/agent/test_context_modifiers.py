"""Tests for ContextModifier data structure."""
from tools.registry import ContextModifier


def test_context_modifier_default_empty():
    cm = ContextModifier()
    assert cm.is_empty()


def test_context_modifier_with_memory_write():
    cm = ContextModifier(memory_writes=[{"target": "user", "content": "test fact"}])
    assert not cm.is_empty()
    assert len(cm.memory_writes) == 1


def test_context_modifier_with_ephemeral():
    cm = ContextModifier(ephemeral_context="Remember to be concise")
    assert not cm.is_empty()
    assert "concise" in cm.ephemeral_context


def test_apply_context_modifiers_ephemeral(tmp_path):
    """apply_context_modifiers appends ephemeral context to agent."""
    from unittest.mock import MagicMock
    from agent.tool_executor import ToolExecutor

    agent = MagicMock()
    agent.ephemeral_system_prompt = "existing"
    agent._memory_store = None

    executor = ToolExecutor(agent)
    cm = ContextModifier(ephemeral_context="new context")
    executor.apply_context_modifiers([cm])

    assert "existing" in agent.ephemeral_system_prompt
    assert "new context" in agent.ephemeral_system_prompt
