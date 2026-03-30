# tests/test_mcp_autoconfig.py
"""Tests for tools/mcp_autoconfig.py — MCP Auto-Configurator."""
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml


# ---------------------------------------------------------------------------
# MCP_TEMPLATES coverage
# ---------------------------------------------------------------------------

def test_mcp_templates_covers_required_services():
    from tools.mcp_autoconfig import MCP_TEMPLATES

    required = [
        "gmail", "shopify", "notion", "slack", "stripe",
        "github", "airtable", "hubspot", "quickbooks",
        "xero", "calendly", "square",
    ]
    for svc in required:
        assert svc in MCP_TEMPLATES, f"MCP_TEMPLATES missing service: {svc}"


def test_mcp_templates_quickbooks_is_builtin():
    from tools.mcp_autoconfig import MCP_TEMPLATES

    assert MCP_TEMPLATES["quickbooks"].get("builtin") is True


def test_mcp_templates_xero_is_builtin():
    from tools.mcp_autoconfig import MCP_TEMPLATES

    assert MCP_TEMPLATES["xero"].get("builtin") is True


# ---------------------------------------------------------------------------
# build_mcp_config
# ---------------------------------------------------------------------------

def test_build_mcp_config_substitutes_credentials():
    from tools.mcp_autoconfig import build_mcp_config

    cred = {
        "service": "gmail",
        "username": "user@example.com",
        "password": "secret-token",
    }
    result = build_mcp_config(cred)
    assert result is not None
    # Should not contain raw placeholders
    result_str = str(result)
    assert "{username}" not in result_str
    assert "{password}" not in result_str
    # Actual values substituted
    assert "user@example.com" in result_str


def test_build_mcp_config_returns_none_for_unknown_service():
    from tools.mcp_autoconfig import build_mcp_config

    cred = {
        "service": "nonexistent_service_xyz",
        "username": "user@example.com",
        "password": "secret",
    }
    result = build_mcp_config(cred)
    assert result is None


def test_build_mcp_config_returns_none_for_builtin_services():
    """Builtin services (quickbooks, xero) don't need MCP server configs."""
    from tools.mcp_autoconfig import build_mcp_config

    for svc in ("quickbooks", "xero"):
        cred = {"service": svc, "username": "u", "password": "p"}
        result = build_mcp_config(cred)
        # Builtin services return None (no external server config needed)
        assert result is None, f"build_mcp_config should return None for builtin service: {svc}"


def test_build_mcp_config_slack_substitution():
    from tools.mcp_autoconfig import build_mcp_config

    cred = {
        "service": "slack",
        "username": "slack-user",
        "password": "xoxb-slack-token",
    }
    result = build_mcp_config(cred)
    assert result is not None
    result_str = str(result)
    assert "{username}" not in result_str
    assert "{password}" not in result_str


# ---------------------------------------------------------------------------
# apply_mcp_configs
# ---------------------------------------------------------------------------

def test_apply_mcp_configs_writes_to_config_yaml(tmp_path, monkeypatch):
    """apply_mcp_configs should write mcp_servers key to config.yaml."""
    from tools.mcp_autoconfig import apply_mcp_configs

    config_path = tmp_path / "config.yaml"
    configs = {
        "gmail": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-gmail"],
            "env": {"GMAIL_USER": "user@example.com"},
        }
    }
    apply_mcp_configs(configs, config_path=config_path)

    assert config_path.exists(), "config.yaml should be created"
    with open(config_path) as f:
        data = yaml.safe_load(f)
    assert "mcp_servers" in data
    assert "gmail" in data["mcp_servers"]
    assert data["mcp_servers"]["gmail"]["command"] == "npx"


def test_apply_mcp_configs_merges_with_existing(tmp_path, monkeypatch):
    """apply_mcp_configs should merge into existing config without overwriting."""
    from tools.mcp_autoconfig import apply_mcp_configs

    config_path = tmp_path / "config.yaml"
    # Write existing config with an unrelated key
    existing = {"model": "gpt-4", "mcp_servers": {"existing_svc": {"command": "node"}}}
    with open(config_path, "w") as f:
        yaml.dump(existing, f)

    new_configs = {
        "slack": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-slack"],
            "env": {"SLACK_TOKEN": "xoxb-token"},
        }
    }
    apply_mcp_configs(new_configs, config_path=config_path)

    with open(config_path) as f:
        data = yaml.safe_load(f)
    # Existing unrelated key preserved
    assert data["model"] == "gpt-4"
    # Existing mcp server preserved
    assert "existing_svc" in data["mcp_servers"]
    # New server added
    assert "slack" in data["mcp_servers"]


def test_apply_mcp_configs_uses_hermes_home_by_default(monkeypatch, tmp_path):
    """When config_path is None, apply_mcp_configs uses HERMES_HOME/config.yaml."""
    # _isolate_hermes_home autouse fixture already sets HERMES_HOME to tmp_path/hermes_test
    # We just verify it writes to the env-var path, not the real home.
    from tools.mcp_autoconfig import apply_mcp_configs

    hermes_home = Path(os.environ["HERMES_HOME"])
    expected_config = hermes_home / "config.yaml"

    configs = {"github": {"command": "npx", "args": [], "env": {"GH_TOKEN": "tok"}}}
    apply_mcp_configs(configs)  # no config_path — should use HERMES_HOME

    assert expected_config.exists()
    with open(expected_config) as f:
        data = yaml.safe_load(f)
    assert "mcp_servers" in data
    assert "github" in data["mcp_servers"]


# ---------------------------------------------------------------------------
# detect_and_configure
# ---------------------------------------------------------------------------

def test_detect_and_configure_returns_configured_service_names(monkeypatch):
    """detect_and_configure should return list of service names that got configs."""
    from tools import mcp_autoconfig

    fake_creds = [
        {"service": "gmail", "username": "u@g.com", "password": "pass", "display_name": "Gmail", "domain": "mail.google.com", "source": "keychain"},
        {"service": "slack", "username": "u", "password": "xoxb-tok", "display_name": "Slack", "domain": "slack.com", "source": "keychain"},
        {"service": "quickbooks", "username": "u", "password": "pass", "display_name": "QuickBooks", "domain": "quickbooks.intuit.com", "source": "keychain"},
    ]

    monkeypatch.setattr(mcp_autoconfig, "_harvest", lambda: fake_creds)

    written = {}

    def fake_apply(configs, config_path=None):
        written.update(configs)

    monkeypatch.setattr(mcp_autoconfig, "apply_mcp_configs", fake_apply)

    result = mcp_autoconfig.detect_and_configure()

    # gmail and slack should be configured (quickbooks is builtin, build_mcp_config returns None)
    assert "gmail" in result
    assert "slack" in result
    # quickbooks is builtin — no external MCP server written
    assert "quickbooks" not in result


def test_detect_and_configure_returns_empty_when_no_creds(monkeypatch):
    """detect_and_configure returns [] when harvest finds nothing."""
    from tools import mcp_autoconfig

    monkeypatch.setattr(mcp_autoconfig, "_harvest", lambda: [])
    monkeypatch.setattr(mcp_autoconfig, "apply_mcp_configs", lambda configs, config_path=None: None)

    result = mcp_autoconfig.detect_and_configure()
    assert result == []
