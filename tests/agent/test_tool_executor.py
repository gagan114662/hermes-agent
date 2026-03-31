"""Unit tests for ToolExecutor.invoke_tool — special-cased tools."""
import json
from unittest.mock import MagicMock, patch
from agent.tool_executor import ToolExecutor


def _make_executor():
    agent = MagicMock()
    agent._todo_store = MagicMock()
    agent._session_db = MagicMock()
    agent._memory_store = MagicMock()
    agent._honcho = None
    agent._honcho_session_key = None
    agent.clarify_callback = None
    agent.valid_tool_names = []
    return ToolExecutor(agent)


def test_tool_executor_instantiates():
    executor = _make_executor()
    assert executor.agent is not None


def test_invoke_unknown_tool_delegates_to_handle_function_call():
    executor = _make_executor()
    with patch("agent.tool_executor.ToolExecutor.invoke_tool") as mock_invoke:
        mock_invoke.return_value = '{"ok": true}'
        result = executor.invoke_tool("web_search", {"query": "test"}, "task-1")
    mock_invoke.assert_called_once_with("web_search", {"query": "test"}, "task-1")
    assert result == '{"ok": true}'


def test_invoke_tool_todo():
    executor = _make_executor()
    with patch("tools.todo_tool.todo_tool") as mock_todo:
        mock_todo.return_value = '{"todos": []}'
        result = executor.invoke_tool("todo", {"todos": [], "merge": False}, "task-1")
    mock_todo.assert_called_once()
    assert result == '{"todos": []}'


def test_invoke_tool_session_search_no_db():
    executor = _make_executor()
    executor.agent._session_db = None
    result = executor.invoke_tool("session_search", {"query": "test"}, "task-1")
    parsed = json.loads(result)
    assert parsed["success"] is False
    assert "not available" in parsed["error"]


def test_invoke_tool_memory():
    executor = _make_executor()
    with patch("tools.memory_tool.memory_tool") as mock_mem:
        mock_mem.return_value = '{"ok": true}'
        result = executor.invoke_tool(
            "memory",
            {"action": "read", "target": "memory", "content": None, "old_text": None},
            "task-1",
        )
    mock_mem.assert_called_once()
    assert result == '{"ok": true}'
