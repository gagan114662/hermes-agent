"""Tests for agent/sentry_tracing.py — must pass even without sentry-sdk installed."""
from unittest.mock import MagicMock, patch
import pytest


def test_init_sentry_no_dsn_returns_false():
    """init_sentry() without a DSN should return False gracefully."""
    from agent.sentry_tracing import init_sentry
    result = init_sentry(dsn="")
    assert result is False


def test_finish_session_no_crash_without_sentry():
    """finish_session() must not raise even when sentry-sdk is absent."""
    from agent.sentry_tracing import finish_session
    finish_session("test-session-123", token_count=100, tool_call_count=5)  # no raise


def test_capture_heal_verdict_no_crash_without_sentry():
    """capture_heal_verdict() must not raise even when sentry-sdk is absent."""
    from agent.sentry_tracing import capture_heal_verdict
    capture_heal_verdict("PASS", session_id="abc", task_summary="all good")
    capture_heal_verdict("FAIL", session_id="abc", task_summary="broken", issues_found=2)


def test_hooks_return_tool_hook_result():
    """Sentry pre/post/failure hooks must always return a ToolHookResult."""
    from agent.tool_hooks import ToolHookContext, ToolHookResult
    from agent.sentry_tracing import _sentry_pre_hook, _sentry_post_hook, _sentry_failure_hook

    agent = MagicMock()
    agent.session_id = "test-sess"
    agent.model = "claude-3"
    # Explicitly set these so the skill restriction hook doesn't trigger
    agent._active_skill_allowed_tools = []
    agent._active_skill_blocked_tools = []

    ctx = ToolHookContext(tool_name="web_search", tool_input={"query": "test"}, agent=agent)

    pre_result = _sentry_pre_hook(ctx)
    assert isinstance(pre_result, ToolHookResult)
    assert not pre_result.blocking_error

    ctx.result = '{"ok": true}'
    post_result = _sentry_post_hook(ctx)
    assert isinstance(post_result, ToolHookResult)

    ctx.error = ValueError("tool exploded")
    fail_result = _sentry_failure_hook(ctx)
    assert isinstance(fail_result, ToolHookResult)


def test_init_sentry_with_fake_dsn():
    """init_sentry() with a valid-looking DSN should attempt SDK init."""
    import agent.sentry_tracing as st
    # Reset state for test isolation
    st._initialized = False

    with patch.dict("os.environ", {}, clear=False):
        with patch("agent.sentry_tracing._sentry") as mock_sentry_fn:
            mock_sdk = MagicMock()
            mock_client = MagicMock()
            mock_sdk.get_client.return_value = mock_client
            mock_sentry_fn.return_value = mock_sdk

            result = st.init_sentry(
                dsn="https://fake@sentry.io/123",
                environment="test",
                traces_sample_rate=0.0,
            )
            assert result is True
            mock_sdk.init.assert_called_once()

    # Reset for other tests
    st._initialized = False
