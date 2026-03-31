"""Tests for conversation stop hooks."""
from unittest.mock import MagicMock, patch
from agent.stop_hooks import run_stop_hooks, _maybe_detect_deal_transition


def test_stop_hooks_skips_on_interrupt():
    agent = MagicMock()
    # Should not raise even with minimal mocking
    run_stop_hooks(agent=agent, messages=[], final_response="", completed=False, interrupted=True)


def test_stop_hooks_skips_no_response():
    agent = MagicMock()
    run_stop_hooks(agent=agent, messages=[], final_response=None, completed=True, interrupted=False)


def test_stop_hooks_fires_on_completion():
    agent = MagicMock()
    with patch("hermes_cli.plugins.emit_hook") as mock_emit:
        run_stop_hooks(
            agent=agent,
            messages=[{"role": "user", "content": "hi"}],
            final_response="Done!",
            completed=True,
            interrupted=False,
        )
        mock_emit.assert_called()


def test_deal_transition_detected():
    agent = MagicMock()
    with patch("hermes_cli.plugins.emit_hook") as mock_emit:
        _maybe_detect_deal_transition(
            messages=[],
            final_response="The deal has moved to Proposal Sent stage.",
            agent=agent,
        )
        mock_emit.assert_called_with("on_deal_stage_transition", response_preview=mock_emit.call_args[1]["response_preview"])


def test_no_deal_transition_no_emit():
    agent = MagicMock()
    with patch("hermes_cli.plugins.emit_hook") as mock_emit:
        _maybe_detect_deal_transition(
            messages=[],
            final_response="The weather is nice today.",
            agent=agent,
        )
        mock_emit.assert_not_called()
