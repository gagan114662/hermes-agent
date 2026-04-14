"""
Regression: run_conversation() delegates to pipeline modules correctly.
Uses Mock client so no real network calls are made.
"""
from unittest.mock import MagicMock
import pytest
from run_agent import AIAgent


def _make_agent():
    agent = AIAgent(
        model="anthropic/claude-haiku-4-5",
        api_key="test-key",
        quiet_mode=True,
    )
    mock_client = MagicMock()
    agent.client = mock_client
    agent._disable_streaming = True  # Use non-streaming path so MagicMock works as response
    return agent, mock_client


def _make_mock_response(content="Hello, world!"):
    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message.content = content
    choice.message.tool_calls = None
    choice.message.reasoning_content = None
    # Explicitly set reasoning fields to None so _extract_reasoning
    # doesn't pick up auto-generated MagicMock instances.
    choice.message.reasoning = None
    choice.message.reasoning_details = None

    resp = MagicMock(spec=["choices", "usage"])
    resp.choices = [choice]
    resp.usage = MagicMock(spec=["prompt_tokens", "completion_tokens", "total_tokens"])
    resp.usage.prompt_tokens = 10
    resp.usage.completion_tokens = 5
    resp.usage.total_tokens = 15
    return resp


def test_run_conversation_returns_final_response():
    agent, mock_client = _make_agent()
    mock_client.chat.completions.create.return_value = _make_mock_response("Done.")

    result = agent.run_conversation("Say hello")

    assert result["final_response"] == "Done."
    assert result["completed"] is True
    assert result["api_calls"] == 1


def test_prepare_turn_is_callable():
    """Verify _prepare_turn() method exists and is callable."""
    agent, _ = _make_agent()
    assert hasattr(agent, "_prepare_turn")
    assert callable(agent._prepare_turn)


def test_build_api_messages_is_callable():
    """Verify _build_api_messages() exists."""
    agent, _ = _make_agent()
    assert hasattr(agent, "_build_api_messages")


def test_build_result_is_callable():
    """Verify _build_result() exists."""
    agent, _ = _make_agent()
    assert hasattr(agent, "_build_result")
