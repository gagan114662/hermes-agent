"""
MCP Auto-Configurator — detects services from macOS Keychain credentials and
writes MCP server configs to ~/.hermes/config.yaml.

Pipeline:
    harvest_credentials() → build_mcp_config() per cred → apply_mcp_configs()

Builtin services (quickbooks, xero) are already supported natively by Hermes
and do not require external MCP servers.
"""
import copy
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

import yaml

from tools.registry import registry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MCP server templates
# Placeholders: {username}, {password}
# ---------------------------------------------------------------------------

MCP_TEMPLATES: dict = {
    "gmail": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-gmail"],
        "env": {"GMAIL_USER": "{username}"},
    },
    "shopify": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-shopify"],
        "env": {
            "SHOPIFY_ACCESS_TOKEN": "{password}",
            "SHOPIFY_SHOP_DOMAIN": "{username}",
        },
    },
    "notion": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-notion"],
        "env": {"NOTION_API_KEY": "{password}"},
    },
    "slack": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-slack"],
        "env": {"SLACK_BOT_TOKEN": "{password}"},
    },
    "stripe": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-stripe"],
        "env": {"STRIPE_SECRET_KEY": "{password}"},
    },
    "github": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "{password}"},
    },
    "airtable": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-airtable"],
        "env": {"AIRTABLE_API_KEY": "{password}"},
    },
    "hubspot": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-hubspot"],
        "env": {"HUBSPOT_ACCESS_TOKEN": "{password}"},
    },
    "calendly": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-calendly"],
        "env": {"CALENDLY_API_KEY": "{password}"},
    },
    "square": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-square"],
        "env": {"SQUARE_ACCESS_TOKEN": "{password}"},
    },
    # Built-in: Hermes already has native tools for these
    "quickbooks": {
        "builtin": True,
        "note": "Use existing quickbooks tools",
    },
    "xero": {
        "builtin": True,
        "note": "Use existing xero tools",
    },
}


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def build_mcp_config(cred: dict) -> Optional[dict]:
    """Build a resolved MCP server config dict for a single credential.

    Substitutes ``{username}`` and ``{password}`` placeholders in the template.

    Returns:
        Resolved config dict, or None if:
        - The service has no template.
        - The service is marked ``builtin`` (no external server needed).
    """
    service = cred.get("service", "")
    template = MCP_TEMPLATES.get(service)
    if template is None:
        return None
    if template.get("builtin"):
        return None

    username = cred.get("username", "")
    password = cred.get("password", "")

    # Deep-copy to avoid mutating the template
    resolved = copy.deepcopy(template)

    def _sub(value):
        if isinstance(value, str):
            return value.replace("{username}", username).replace("{password}", password)
        if isinstance(value, list):
            return [_sub(v) for v in value]
        if isinstance(value, dict):
            return {k: _sub(v) for k, v in value.items()}
        return value

    return _sub(resolved)


def _hermes_config_path() -> Path:
    """Return the path to ~/.hermes/config.yaml (respects HERMES_HOME env var)."""
    hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    return hermes_home / "config.yaml"


def apply_mcp_configs(configs: dict, config_path: Path = None) -> None:
    """Write MCP server configs into config.yaml under the ``mcp_servers`` key.

    Merges with existing config — does not overwrite unrelated keys.

    Args:
        configs: ``{service_name: config_dict}`` mapping.
        config_path: Path to config.yaml. Defaults to ``~/.hermes/config.yaml``.
    """
    if config_path is None:
        config_path = _hermes_config_path()

    config_path = Path(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing config (if any)
    if config_path.exists():
        try:
            with open(config_path) as f:
                existing = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning("Could not parse existing config.yaml: %s — starting fresh", e)
            existing = {}
    else:
        existing = {}

    # Merge under mcp_servers key
    mcp_servers = existing.setdefault("mcp_servers", {})
    mcp_servers.update(configs)

    # Atomic write: write to temp file in the same directory then rename
    tmp_fd, tmp_path = tempfile.mkstemp(dir=config_path.parent, suffix=".yaml.tmp")
    try:
        with os.fdopen(tmp_fd, "w") as f:
            yaml.dump(existing, f, default_flow_style=False, allow_unicode=True)
        os.replace(tmp_path, config_path)
    except Exception:
        os.unlink(tmp_path)
        raise

    logger.info("Wrote %d MCP server config(s) to %s", len(configs), config_path)


def _harvest() -> list:
    """Thin wrapper around credential_harvester.harvest_credentials().

    Isolated as a module-level name so tests can monkeypatch it easily.
    """
    from tools.credential_harvester import harvest_credentials
    return harvest_credentials()


def detect_and_configure() -> list:
    """Full pipeline: harvest credentials → build configs → write → return names.

    Returns:
        List of service names for which MCP server configs were written.
    """
    credentials = _harvest()
    if not credentials:
        logger.info("mcp_autoconfig: no credentials found in Keychain")
        return []

    configs = {}
    for cred in credentials:
        cfg = build_mcp_config(cred)
        if cfg is not None:
            configs[cred["service"]] = cfg
            logger.info("mcp_autoconfig: built config for %s", cred["service"])

    if configs:
        apply_mcp_configs(configs)

    return list(configs.keys())


# ---------------------------------------------------------------------------
# Tool wrapper (registered with Hermes)
# ---------------------------------------------------------------------------

def mcp_autoconfig_tool(args: dict) -> str:
    """Detect services from credentials and spin up MCP servers automatically."""
    configured = detect_and_configure()
    if not configured:
        return "No new services detected to configure."
    return f"Configured MCP servers for: {', '.join(configured)}"


registry.register(
    name="mcp_autoconfig",
    toolset="mcp_autoconfig",
    schema={
        "name": "mcp_autoconfig",
        "description": (
            "Detect services from macOS Keychain credentials and automatically "
            "configure MCP servers for them in ~/.hermes/config.yaml."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    handler=mcp_autoconfig_tool,
    description="Detect services from credentials and spin up MCP servers automatically.",
    emoji="🔌",
)
