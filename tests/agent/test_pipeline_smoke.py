"""Smoke test: pipeline module can be imported and TurnState works."""
from agent.pipeline import TurnState, TurnPipeline
from unittest.mock import MagicMock


def test_turn_state_defaults():
    state = TurnState()
    assert state.messages == []
    assert state.api_call_count == 0
    assert state.completed is False
    assert state.interrupted is False


def test_turn_pipeline_instantiates():
    mock_agent = MagicMock()
    pipeline = TurnPipeline(mock_agent)
    assert pipeline.agent is mock_agent
