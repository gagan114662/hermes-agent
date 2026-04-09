import importlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

moa = importlib.import_module("tools.mixture_of_agents_tool")


def test_moa_defaults_track_current_openrouter_frontier_models():
    assert moa.REFERENCE_MODELS == [
        "anthropic/claude-opus-4.6",
        "google/gemini-2.5-pro",
        "openai/gpt-5.4-pro",
        "deepseek/deepseek-v3.2",
    ]
    assert moa.AGGREGATOR_MODEL == "anthropic/claude-opus-4.6"


def test_reference_models_does_not_contain_deprecated_gemini_3_pro_preview():
    assert "google/gemini-3-pro-preview" not in moa.REFERENCE_MODELS


@pytest.mark.asyncio
async def test_reference_model_passes_max_tokens_to_api(monkeypatch):
    """max_tokens must be forwarded to the API call so OpenRouter budgets correctly."""
    captured = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        resp = MagicMock()
        resp.choices = [MagicMock(message=MagicMock(content="ok", reasoning_content=None))]
        return resp

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )
    monkeypatch.setattr(moa, "_get_openrouter_client", lambda: fake_client)

    await moa._run_reference_model_safe("deepseek/deepseek-v3.2", "hello", max_tokens=16000, max_retries=1)

    assert "max_tokens" in captured, "max_tokens was not forwarded to the API call"
    assert captured["max_tokens"] == 16000


@pytest.mark.asyncio
async def test_aggregator_model_passes_max_tokens_to_api_when_set(monkeypatch):
    """max_tokens must be forwarded by the aggregator when explicitly provided."""
    captured = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        resp = MagicMock()
        resp.choices = [MagicMock(message=MagicMock(content="synthesis", reasoning_content=None))]
        return resp

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )
    monkeypatch.setattr(moa, "_get_openrouter_client", lambda: fake_client)

    await moa._run_aggregator_model("sys", "user", max_tokens=8000)

    assert "max_tokens" in captured, "max_tokens was not forwarded to the aggregator API call"
    assert captured["max_tokens"] == 8000


@pytest.mark.asyncio
async def test_aggregator_model_omits_max_tokens_when_none(monkeypatch):
    """When max_tokens is None (default), it must not be sent to the API."""
    captured = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        resp = MagicMock()
        resp.choices = [MagicMock(message=MagicMock(content="synthesis", reasoning_content=None))]
        return resp

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )
    monkeypatch.setattr(moa, "_get_openrouter_client", lambda: fake_client)

    await moa._run_aggregator_model("sys", "user")  # max_tokens defaults to None

    assert "max_tokens" not in captured, "max_tokens should be omitted when None"


@pytest.mark.asyncio
async def test_reference_model_retry_warnings_avoid_exc_info_until_terminal_failure(monkeypatch):
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=AsyncMock(side_effect=RuntimeError("rate limited"))
            )
        )
    )
    warn = MagicMock()
    err = MagicMock()

    monkeypatch.setattr(moa, "_get_openrouter_client", lambda: fake_client)
    monkeypatch.setattr(moa.logger, "warning", warn)
    monkeypatch.setattr(moa.logger, "error", err)

    model, message, success = await moa._run_reference_model_safe(
        "openai/gpt-5.4-pro", "hello", max_retries=2
    )

    assert model == "openai/gpt-5.4-pro"
    assert success is False
    assert "failed after 2 attempts" in message
    assert warn.call_count == 2
    assert all(call.kwargs.get("exc_info") is None for call in warn.call_args_list)
    err.assert_called_once()
    assert err.call_args.kwargs.get("exc_info") is True


@pytest.mark.asyncio
async def test_moa_top_level_error_logs_single_traceback_on_aggregator_failure(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(
        moa,
        "_run_reference_model_safe",
        AsyncMock(return_value=("anthropic/claude-opus-4.6", "ok", True)),
    )
    monkeypatch.setattr(
        moa,
        "_run_aggregator_model",
        AsyncMock(side_effect=RuntimeError("aggregator boom")),
    )
    monkeypatch.setattr(
        moa,
        "_debug",
        SimpleNamespace(log_call=MagicMock(), save=MagicMock(), active=False),
    )

    err = MagicMock()
    monkeypatch.setattr(moa.logger, "error", err)

    result = json.loads(
        await moa.mixture_of_agents_tool(
            "solve this",
            reference_models=["anthropic/claude-opus-4.6"],
        )
    )

    assert result["success"] is False
    assert "Error in MoA processing" in result["error"]
    err.assert_called_once()
    assert err.call_args.kwargs.get("exc_info") is True
