from gateway import run as gateway_run


def test_resolve_runtime_agent_kwargs_prefers_config_over_stale_env(monkeypatch):
    captured = {}

    def fake_resolve_runtime_provider(requested=None, **kwargs):
        captured["requested"] = requested
        captured["kwargs"] = kwargs
        return {
            "api_key": "codex-token",
            "base_url": "https://chatgpt.com/backend-api/codex",
            "provider": "openai-codex",
            "api_mode": "codex_responses",
            "command": None,
            "args": [],
            "credential_pool": None,
        }

    monkeypatch.setenv("HERMES_INFERENCE_PROVIDER", "openrouter")
    monkeypatch.setattr(
        "hermes_cli.runtime_provider.resolve_runtime_provider",
        fake_resolve_runtime_provider,
    )

    result = gateway_run._resolve_runtime_agent_kwargs()

    assert captured["requested"] is None
    assert result["provider"] == "openai-codex"
    assert result["base_url"] == "https://chatgpt.com/backend-api/codex"
