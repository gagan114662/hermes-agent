"""Tests for multi-provider API routing."""
import os
import pytest
from unittest.mock import patch
from agent.provider_router import resolve_provider_config, list_providers, PROVIDER_CONFIGS


def test_default_provider_is_openrouter():
    with patch.dict(os.environ, {}, clear=False):
        config = resolve_provider_config()
    assert config["provider"] == "openrouter"


def test_explicit_provider_overrides_default():
    config = resolve_provider_config(provider="anthropic")
    assert config["provider"] == "anthropic"
    assert "anthropic.com" in config["base_url"]


def test_hermes_provider_env_var():
    with patch.dict(os.environ, {"HERMES_PROVIDER": "azure"}):
        config = resolve_provider_config()
    assert config["provider"] == "azure"


def test_infer_bedrock_from_model():
    config = resolve_provider_config(model="bedrock/claude-3-haiku")
    assert config["provider"] == "bedrock"


def test_list_providers_returns_all():
    providers = list_providers()
    provider_names = {p["provider"] for p in providers}
    assert {"anthropic", "openrouter", "bedrock", "azure", "vertex"}.issubset(provider_names)


def test_all_providers_have_description():
    for p in list_providers():
        assert "description" in p
        assert len(p["description"]) > 0
