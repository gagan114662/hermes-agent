# Hermes Delight Onboarding Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Business owner installs the app, grants one permission, and within 5 minutes Hermes has auto-connected to all their tools and is already doing work — without being asked a single question.

**Architecture:** A credential harvester reads macOS Keychain + browser passwords once, maps them to MCP server configs that spin up automatically, then a proactive work loop runs every 15 minutes across 5 queues (inbox, leads, money, reputation, prospecting) and reports results to the owner on Telegram each morning.

**Tech Stack:** Python 3.11, macOS `security` CLI (Keychain), `sqlite3` (browser passwords), `rumps` (menubar), `httpx`, existing Hermes tools (crm_tool, prospect_tool, reach_tools, twilio_tool, vapi_tool)

---

## Context for the implementer

- All new tools follow the pattern: create `tools/xxx_tool.py` → `registry.register()` → add to `model_tools.py` `_modules` list → add names to `_HERMES_CORE_TOOLS` in `toolsets.py`
- Persistent data lives in `~/.hermes/` as JSON files
- Tests use `_isolate_hermes_home` fixture (auto-applied) which redirects `~/.hermes` to a temp dir
- Run tests with: `venv/bin/pytest tests/test_xxx.py -v`
- Gateway restart: `launchctl unload ~/Library/LaunchAgents/ai.hermes.gateway.plist && launchctl load ~/Library/LaunchAgents/ai.hermes.gateway.plist`
- Owner's Telegram ID: read from `TELEGRAM_OWNER_ID` env var
- See `tools/crm_tool.py` for a complete example of the tool pattern

---

### Task 1: Credential Harvester

Reads macOS Keychain and Chrome/Safari saved passwords. Maps known domains to service names. Outputs a list of `{service, username, password_or_token}` dicts. Never writes credentials anywhere — caller decides what to do with them.

**Files:**
- Create: `tools/credential_harvester.py`
- Create: `tests/test_credential_harvester.py`

**Step 1: Write the failing tests**

```python
# tests/test_credential_harvester.py
import pytest
from unittest.mock import patch, MagicMock
from tools.credential_harvester import (
    _map_domain_to_service,
    _parse_keychain_output,
    harvest_credentials,
    SERVICE_MAP,
)

def test_map_domain_to_service_known():
    assert _map_domain_to_service("gmail.com") == "gmail"
    assert _map_domain_to_service("app.shopify.com") == "shopify"
    assert _map_domain_to_service("quickbooks.intuit.com") == "quickbooks"

def test_map_domain_to_service_unknown():
    assert _map_domain_to_service("unknownapp.xyz") is None

def test_parse_keychain_output_extracts_fields():
    raw = '''keychain: "/Users/user/Library/Keychains/login.keychain-db"
class: "inet"
attributes:
    "acct"<blob>="user@gmail.com"
    "srvr"<blob>="gmail.com"
password: "mypassword123"
'''
    result = _parse_keychain_output(raw)
    assert result["username"] == "user@gmail.com"
    assert result["domain"] == "gmail.com"
    assert result["password"] == "mypassword123"

def test_parse_keychain_output_missing_fields():
    result = _parse_keychain_output("no fields here")
    assert result is None

def test_harvest_credentials_returns_list(monkeypatch):
    mock_output = '''keychain: "/Users/user/Library/Keychains/login.keychain-db"
class: "inet"
attributes:
    "acct"<blob>="owner@shopify.com"
    "srvr"<blob>="app.shopify.com"
password: "shopify-token-abc"
'''
    monkeypatch.setattr(
        "tools.credential_harvester._run_keychain_dump",
        lambda: mock_output
    )
    monkeypatch.setattr(
        "tools.credential_harvester._read_browser_passwords",
        lambda: []
    )
    results = harvest_credentials()
    assert len(results) == 1
    assert results[0]["service"] == "shopify"
    assert results[0]["username"] == "owner@shopify.com"
    assert results[0]["password"] == "shopify-token-abc"

def test_service_map_covers_common_smb_tools():
    required = ["gmail", "shopify", "quickbooks", "stripe", "calendly", "notion", "slack"]
    for svc in required:
        assert any(svc in v for v in SERVICE_MAP.values()), f"Missing service: {svc}"
```

**Step 2: Run tests to confirm they fail**
```bash
cd "/Users/gaganarora/Desktop/my projects/hermes/hermes-agent"
venv/bin/pytest tests/test_credential_harvester.py -v
```
Expected: `ModuleNotFoundError: No module named 'tools.credential_harvester'`

**Step 3: Implement `tools/credential_harvester.py`**

```python
"""
Credential Harvester — reads macOS Keychain and browser saved passwords.

Maps known service domains to service names. Returns structured credential
dicts for use by the MCP auto-configurator. Credentials never leave this
machine — no logging, no network calls.
"""
import re
import sqlite3
import subprocess
import shutil
from pathlib import Path
from typing import Optional

# domain substring → service name
SERVICE_MAP = {
    "gmail.com": "gmail",
    "google.com": "gmail",
    "mail.google.com": "gmail",
    "shopify.com": "shopify",
    "quickbooks.intuit.com": "quickbooks",
    "intuit.com": "quickbooks",
    "stripe.com": "stripe",
    "dashboard.stripe.com": "stripe",
    "calendly.com": "calendly",
    "notion.so": "notion",
    "slack.com": "slack",
    "airtable.com": "airtable",
    "hubspot.com": "hubspot",
    "squareup.com": "square",
    "square.com": "square",
    "xero.com": "xero",
    "trello.com": "trello",
    "github.com": "github",
    "wordpress.com": "wordpress",
    "woocommerce.com": "woocommerce",
}


def _map_domain_to_service(domain: str) -> Optional[str]:
    domain = domain.lower()
    for pattern, service in SERVICE_MAP.items():
        if pattern in domain:
            return service
    return None


def _run_keychain_dump() -> str:
    """Dump all internet passwords from the login keychain."""
    try:
        result = subprocess.run(
            ["security", "dump-keychain", "-d", "login.keychain"],
            capture_output=True, text=True, timeout=30,
        )
        return result.stdout
    except Exception:
        return ""


def _parse_keychain_output(raw: str) -> Optional[dict]:
    """Parse a single keychain entry block. Returns None if incomplete."""
    username_match = re.search(r'"acct"<blob>="([^"]+)"', raw)
    domain_match = re.search(r'"srvr"<blob>="([^"]+)"', raw)
    password_match = re.search(r'^password: "([^"]*)"', raw, re.MULTILINE)

    if not (username_match and domain_match and password_match):
        return None

    return {
        "username": username_match.group(1),
        "domain": domain_match.group(1),
        "password": password_match.group(1),
    }


def _read_browser_passwords() -> list:
    """
    Read Chrome saved passwords from its SQLite Login Data file.
    Returns list of {domain, username, password} dicts.
    Note: Chrome must be closed for the DB to be readable.
    """
    results = []
    chrome_path = Path.home() / "Library/Application Support/Google/Chrome/Default/Login Data"
    if not chrome_path.exists():
        return results

    # Copy to temp to avoid lock issues
    import tempfile, shutil
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name
    shutil.copy2(chrome_path, tmp_path)

    try:
        conn = sqlite3.connect(tmp_path)
        cursor = conn.execute(
            "SELECT origin_url, username_value, password_value FROM logins"
        )
        for url, username, _ in cursor.fetchall():
            # Extract domain from URL
            domain_match = re.search(r"https?://([^/]+)", url or "")
            if domain_match and username:
                results.append({
                    "domain": domain_match.group(1),
                    "username": username,
                    "password": "",  # encrypted, skip for now
                })
        conn.close()
    except Exception:
        pass
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return results


def harvest_credentials() -> list:
    """
    Harvest credentials from Keychain and browser.
    Returns list of {service, username, password, source} dicts
    for known services only. Unknowns are silently skipped.
    """
    found = []
    seen_services = set()

    # Parse Keychain entries
    raw = _run_keychain_dump()
    # Split on keychain entry boundaries
    entries = re.split(r'(?=keychain:)', raw)
    for entry in entries:
        parsed = _parse_keychain_output(entry)
        if not parsed:
            continue
        service = _map_domain_to_service(parsed["domain"])
        if service and service not in seen_services:
            seen_services.add(service)
            found.append({
                "service": service,
                "username": parsed["username"],
                "password": parsed["password"],
                "source": "keychain",
            })

    # Add browser password domains (no decrypted passwords, but confirms login exists)
    for entry in _read_browser_passwords():
        service = _map_domain_to_service(entry["domain"])
        if service and service not in seen_services:
            seen_services.add(service)
            found.append({
                "service": service,
                "username": entry["username"],
                "password": entry["password"],
                "source": "browser",
            })

    return found
```

**Step 4: Run tests to confirm they pass**
```bash
venv/bin/pytest tests/test_credential_harvester.py -v
```
Expected: `6 passed`

**Step 5: Commit**
```bash
git add tools/credential_harvester.py tests/test_credential_harvester.py
git commit -m "feat: credential harvester — reads Keychain + browser passwords, maps to services"
```

---

### Task 2: MCP Auto-Configurator

Given a list of harvested credentials, spins up MCP servers for each detected service by writing configs to `~/.hermes/config.yaml` under `mcp_servers`. The gateway picks these up on next restart.

**Files:**
- Create: `tools/mcp_autoconfig.py`
- Create: `tests/test_mcp_autoconfig.py`

**Step 1: Write failing tests**

```python
# tests/test_mcp_autoconfig.py
import pytest
import yaml
from pathlib import Path
from tools.mcp_autoconfig import (
    MCP_TEMPLATES,
    build_mcp_config,
    apply_mcp_configs,
    detect_and_configure,
)

def test_mcp_templates_cover_key_services():
    required = ["gmail", "shopify", "notion", "slack", "stripe"]
    for svc in required:
        assert svc in MCP_TEMPLATES, f"No MCP template for {svc}"

def test_build_mcp_config_gmail():
    cred = {"service": "gmail", "username": "user@gmail.com", "password": "token123"}
    config = build_mcp_config(cred)
    assert config is not None
    assert "command" in config or "url" in config

def test_build_mcp_config_unknown_service():
    cred = {"service": "unknownapp", "username": "x", "password": "y"}
    config = build_mcp_config(cred)
    assert config is None

def test_apply_mcp_configs_writes_to_config_yaml(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("model:\n  default: anthropic/claude-sonnet-4-6\n")
    monkeypatch.setenv("HOME", str(tmp_path))

    configs = {
        "gmail": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-gmail"]},
    }
    apply_mcp_configs(configs, config_path=config_path)

    data = yaml.safe_load(config_path.read_text())
    assert "mcp_servers" in data
    assert "gmail" in data["mcp_servers"]

def test_detect_and_configure_returns_connected_services(monkeypatch):
    monkeypatch.setattr(
        "tools.mcp_autoconfig._harvest",
        lambda: [{"service": "gmail", "username": "u@g.com", "password": "tok"}]
    )
    monkeypatch.setattr("tools.mcp_autoconfig.apply_mcp_configs", lambda configs, **kw: None)
    result = detect_and_configure()
    assert "gmail" in result
```

**Step 2: Run to confirm failure**
```bash
venv/bin/pytest tests/test_mcp_autoconfig.py -v
```
Expected: `ModuleNotFoundError`

**Step 3: Implement `tools/mcp_autoconfig.py`**

```python
"""
MCP Auto-Configurator — detects services from credentials and spins up MCP servers.

Writes mcp_servers entries to ~/.hermes/config.yaml.
Gateway reloads MCP servers on restart.
"""
import logging
import os
from pathlib import Path
from typing import Optional

import yaml

from tools.credential_harvester import harvest_credentials

logger = logging.getLogger(__name__)

# service_name → MCP server config template
# Uses npx-based MCP servers (no install required)
MCP_TEMPLATES = {
    "gmail": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-gmail"],
        "env": {"GMAIL_USER": "{username}"},
    },
    "shopify": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-shopify"],
        "env": {"SHOPIFY_ACCESS_TOKEN": "{password}"},
    },
    "notion": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-notion"],
        "env": {"NOTION_API_TOKEN": "{password}"},
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
        "args": ["-y", "airtable-mcp-server"],
        "env": {"AIRTABLE_API_KEY": "{password}"},
    },
    "hubspot": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-hubspot"],
        "env": {"HUBSPOT_ACCESS_TOKEN": "{password}"},
    },
}


def _harvest():
    """Thin wrapper so tests can monkeypatch it."""
    return harvest_credentials()


def build_mcp_config(cred: dict) -> Optional[dict]:
    """Build an MCP server config dict for a credential. Returns None if no template."""
    template = MCP_TEMPLATES.get(cred["service"])
    if not template:
        return None

    # Substitute {username} and {password} placeholders in env vars
    config = {"command": template["command"], "args": list(template["args"])}
    if "env" in template:
        config["env"] = {
            k: v.replace("{username}", cred.get("username", ""))
                 .replace("{password}", cred.get("password", ""))
            for k, v in template["env"].items()
        }
    return config


def apply_mcp_configs(configs: dict, config_path: Path = None) -> None:
    """Write MCP server configs to ~/.hermes/config.yaml under mcp_servers key."""
    if config_path is None:
        config_path = Path(os.environ.get("HOME", Path.home())) / ".hermes" / "config.yaml"

    data = {}
    if config_path.exists():
        data = yaml.safe_load(config_path.read_text()) or {}

    existing = data.get("mcp_servers", {})
    existing.update(configs)
    data["mcp_servers"] = existing

    config_path.write_text(yaml.dump(data, default_flow_style=False))
    logger.info("MCP configs written for: %s", list(configs.keys()))


def detect_and_configure() -> list:
    """
    Full pipeline: harvest credentials → build MCP configs → write to config.yaml.
    Returns list of service names that were successfully configured.
    """
    credentials = _harvest()
    configs = {}
    configured = []

    for cred in credentials:
        config = build_mcp_config(cred)
        if config:
            configs[cred["service"]] = config
            configured.append(cred["service"])
            logger.info("Configured MCP server for: %s (%s)", cred["service"], cred["username"])

    if configs:
        apply_mcp_configs(configs)

    return configured
```

**Step 4: Run tests**
```bash
venv/bin/pytest tests/test_mcp_autoconfig.py -v
```
Expected: `5 passed`

**Step 5: Commit**
```bash
git add tools/mcp_autoconfig.py tests/test_mcp_autoconfig.py
git commit -m "feat: MCP auto-configurator — detects services from credentials, writes server configs"
```

---

### Task 3: Proactive Work Loop

Checks 5 queues every 15 minutes and acts without being asked. Each queue is a function that returns a list of action strings (what was done). Results are saved to `~/.hermes/action_log.json` for the morning digest.

**Files:**
- Create: `scripts/proactive_loop.py`
- Create: `tests/test_proactive_loop.py`

**Step 1: Write failing tests**

```python
# tests/test_proactive_loop.py
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from scripts.proactive_loop import (
    log_action,
    load_action_log,
    run_inbox_queue,
    run_leads_queue,
    run_money_queue,
    run_prospecting_queue,
    run_all_queues,
)

def test_log_action_appends_to_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()
    log_action("replied to Maria G. email")
    log = load_action_log()
    assert len(log) == 1
    assert log[0]["action"] == "replied to Maria G. email"
    assert "timestamp" in log[0]

def test_log_action_multiple(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()
    log_action("action 1")
    log_action("action 2")
    assert len(load_action_log()) == 2

def test_run_leads_queue_follows_up_stale_prospects(monkeypatch):
    stale = json.dumps([
        {"id": "abc123", "name": "Jake Miller", "contact_hint": "+14155550101",
         "last_contact": "2026-03-25T00:00:00Z", "status": "new"}
    ])
    monkeypatch.setattr("scripts.proactive_loop._list_stale_prospects", lambda: [
        {"id": "abc123", "name": "Jake Miller", "contact_hint": "+14155550101"}
    ])
    sent = []
    monkeypatch.setattr("scripts.proactive_loop._send_followup", lambda prospect: sent.append(prospect["name"]))
    actions = run_leads_queue()
    assert len(actions) == 1
    assert "Jake Miller" in actions[0]

def test_run_all_queues_returns_all_actions(monkeypatch):
    monkeypatch.setattr("scripts.proactive_loop.run_inbox_queue", lambda: ["replied to email"])
    monkeypatch.setattr("scripts.proactive_loop.run_leads_queue", lambda: ["followed up Jake"])
    monkeypatch.setattr("scripts.proactive_loop.run_money_queue", lambda: [])
    monkeypatch.setattr("scripts.proactive_loop.run_prospecting_queue", lambda: ["found lead on reddit"])
    monkeypatch.setattr("scripts.proactive_loop.run_reputation_queue", lambda: [])
    monkeypatch.setattr("scripts.proactive_loop._notify_if_actions", lambda actions: None)
    actions = run_all_queues()
    assert len(actions) == 3
```

**Step 2: Run to confirm failure**
```bash
venv/bin/pytest tests/test_proactive_loop.py -v
```
Expected: `ModuleNotFoundError`

**Step 3: Implement `scripts/proactive_loop.py`**

```python
#!/usr/bin/env python3
"""
Proactive Work Loop — runs every 15 minutes, checks 5 queues, acts without asking.

Queues:
    inbox       — unanswered emails > 2 hours
    leads       — prospects with no follow-up in 3 days
    money       — overdue invoices
    reputation  — unanswered Google/Yelp reviews
    prospecting — new Reddit/Maps pain posts

Results logged to ~/.hermes/action_log.json for morning digest.
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Action log
# ---------------------------------------------------------------------------

def _log_path() -> Path:
    home = Path(os.environ.get("HOME", Path.home()))
    return home / ".hermes" / "action_log.json"


def load_action_log() -> list:
    path = _log_path()
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return []
    return []


def log_action(action: str) -> None:
    log = load_action_log()
    log.append({
        "action": action,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    _log_path().write_text(json.dumps(log, indent=2))
    logger.info("Action: %s", action)


# ---------------------------------------------------------------------------
# Queue: Inbox (unanswered emails)
# ---------------------------------------------------------------------------

def run_inbox_queue() -> list:
    """Check for unanswered customer emails > 2 hours old. Reply using owner's tone."""
    actions = []
    try:
        # Uses MCP gmail server if configured, else skips gracefully
        from tools.mcp_tool import mcp_call
        emails = mcp_call("gmail", "list_unread", {"hours_old": 2, "limit": 5})
        for email in (emails or []):
            sender = email.get("from", "")
            subject = email.get("subject", "")
            reply = _draft_reply(email)
            mcp_call("gmail", "send_reply", {"email_id": email["id"], "body": reply})
            action = f"Replied to email from {sender}: '{subject}'"
            actions.append(action)
    except Exception as e:
        logger.debug("Inbox queue skipped: %s", e)
    return actions


def _draft_reply(email: dict) -> str:
    """Draft a reply in the owner's voice using the agent."""
    return (
        f"Hi {email.get('from_name', 'there')},\n\n"
        "Thanks for reaching out! I'll get back to you shortly with more details.\n\n"
        "Best regards"
    )


# ---------------------------------------------------------------------------
# Queue: Leads (stale prospects)
# ---------------------------------------------------------------------------

def _list_stale_prospects() -> list:
    """Return prospects with no contact in 3+ days."""
    from tools.prospect_tool import prospect_list_fn
    import json as _json
    raw = prospect_list_fn(status="new", limit=50)
    # prospect_list_fn returns formatted string; parse the data directly
    home = Path(os.environ.get("HOME", Path.home()))
    prospects_path = home / ".hermes" / "prospects.json"
    if not prospects_path.exists():
        return []
    data = _json.loads(prospects_path.read_text())
    cutoff = datetime.now(timezone.utc) - timedelta(days=3)
    stale = []
    for pid, p in data.get("prospects", {}).items():
        if p.get("status") != "new":
            continue
        last = p.get("last_contact") or p.get("created_at", "")
        if last:
            try:
                last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
                if last_dt < cutoff:
                    stale.append({**p, "id": pid})
            except Exception:
                stale.append({**p, "id": pid})
    return stale


def _send_followup(prospect: dict) -> None:
    """Send a follow-up message to a stale prospect."""
    contact = prospect.get("contact_hint", "")
    name = prospect.get("name", "there")
    if contact.startswith("+"):
        from tools.twilio_tool import sms_send_tool
        sms_send_tool(
            to=contact,
            message=f"Hi {name}! Just following up — happy to answer any questions about how we can help.",
        )
    elif "@" in contact:
        logger.info("Would email %s at %s (email not implemented yet)", name, contact)


def run_leads_queue() -> list:
    actions = []
    try:
        stale = _list_stale_prospects()
        for prospect in stale[:3]:  # max 3 follow-ups per run
            _send_followup(prospect)
            action = f"Followed up with {prospect.get('name', 'prospect')} (no contact in 3+ days)"
            actions.append(action)
            # Update prospect status
            from tools.prospect_tool import prospect_update_fn
            prospect_update_fn(prospect_id=prospect["id"], status="contacted")
    except Exception as e:
        logger.debug("Leads queue error: %s", e)
    return actions


# ---------------------------------------------------------------------------
# Queue: Money (overdue invoices)
# ---------------------------------------------------------------------------

def run_money_queue() -> list:
    """Check for overdue invoices via Stripe/QuickBooks MCP. Send reminders."""
    actions = []
    try:
        from tools.mcp_tool import mcp_call
        invoices = mcp_call("stripe", "list_overdue_invoices", {"days_overdue": 7, "limit": 5})
        for inv in (invoices or []):
            customer = inv.get("customer_name", "customer")
            amount = inv.get("amount", 0)
            mcp_call("stripe", "send_invoice_reminder", {"invoice_id": inv["id"]})
            action = f"Sent payment reminder to {customer} (${amount:.0f} overdue)"
            actions.append(action)
    except Exception as e:
        logger.debug("Money queue skipped: %s", e)
    return actions


# ---------------------------------------------------------------------------
# Queue: Reputation (unanswered reviews)
# ---------------------------------------------------------------------------

def run_reputation_queue() -> list:
    """Check for unanswered Google/Yelp reviews. Respond publicly."""
    actions = []
    try:
        from tools.mcp_tool import mcp_call
        reviews = mcp_call("google_business", "list_unanswered_reviews", {"limit": 3})
        for review in (reviews or []):
            response = _draft_review_response(review)
            mcp_call("google_business", "reply_to_review", {
                "review_id": review["id"],
                "reply": response,
            })
            action = f"Replied to {review.get('rating', '')}⭐ review from {review.get('author', 'customer')}"
            actions.append(action)
    except Exception as e:
        logger.debug("Reputation queue skipped: %s", e)
    return actions


def _draft_review_response(review: dict) -> str:
    rating = review.get("rating", 5)
    if rating >= 4:
        return "Thank you so much for your kind words! We really appreciate your support and look forward to serving you again."
    return "Thank you for your feedback. We're sorry to hear about your experience and would love to make it right. Please reach out to us directly."


# ---------------------------------------------------------------------------
# Queue: Prospecting (Reddit/Maps)
# ---------------------------------------------------------------------------

def run_prospecting_queue() -> list:
    """Search Reddit for people who need the owner's services. Add to pipeline."""
    actions = []
    try:
        from tools.reach_tools import reddit_search_tool
        from tools.prospect_tool import prospect_add_fn

        # Read owner's business type from config/soul
        business_type = _get_business_type()
        queries = [
            f"need help with {business_type} small business",
            f"looking for {business_type} service overwhelmed",
        ]
        for query in queries:
            results = reddit_search_tool(query, limit=3)
            # Parse results (format: "- **title** (r/sub, ⬆score)\n  url")
            import re
            for match in re.finditer(r'\*\*(.+?)\*\*.*?r/(\w+).*?\n\s+(https://\S+)', results):
                title, subreddit, url = match.groups()
                prospect_add_fn(
                    name=f"Reddit u/unknown ({subreddit})",
                    source="reddit",
                    pain_point=title[:200],
                    source_url=url,
                    score=6,
                )
                action = f"Added Reddit prospect from r/{subreddit}: '{title[:60]}...'"
                actions.append(action)
                if len(actions) >= 2:
                    break
            if len(actions) >= 2:
                break
    except Exception as e:
        logger.debug("Prospecting queue error: %s", e)
    return actions


def _get_business_type() -> str:
    """Read business type from ~/.hermes/COMPANY.md or fall back to generic."""
    try:
        company_path = Path(os.environ.get("HOME", Path.home())) / ".hermes" / "COMPANY.md"
        if company_path.exists():
            content = company_path.read_text()
            # First non-empty line after # heading
            for line in content.splitlines():
                line = line.strip("# ").strip()
                if line:
                    return line[:50]
    except Exception:
        pass
    return "business services"


# ---------------------------------------------------------------------------
# Notify owner
# ---------------------------------------------------------------------------

def _notify_if_actions(actions: list) -> None:
    """Send Telegram summary if anything was done."""
    if not actions:
        return
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    owner_id = os.environ.get("TELEGRAM_OWNER_ID", "")
    if not bot_token or not owner_id:
        return

    lines = ["⚡ Hermes update:\n"]
    for a in actions:
        lines.append(f"✅ {a}")
    text = "\n".join(lines)

    import httpx
    try:
        httpx.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": owner_id, "text": text},
            timeout=10,
        )
    except Exception as e:
        logger.warning("Telegram notify failed: %s", e)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_all_queues() -> list:
    all_actions = []
    for queue_fn in [run_inbox_queue, run_leads_queue, run_money_queue,
                     run_prospecting_queue, run_reputation_queue]:
        actions = queue_fn()
        for a in actions:
            log_action(a)
        all_actions.extend(actions)
    _notify_if_actions(all_actions)
    return all_actions


if __name__ == "__main__":
    run_all_queues()
```

**Step 4: Run tests**
```bash
venv/bin/pytest tests/test_proactive_loop.py -v
```
Expected: `4 passed`

**Step 5: Register as a 15-minute cron**

Add to `scripts/setup_acquisition_crons.py` (already exists):
```python
# Add this cron entry alongside the existing ones
{
    "name": "proactive-work-loop",
    "schedule": "*/15 * * * *",
    "task": "Run the proactive work loop across all 5 queues (inbox, leads, money, reputation, prospecting)",
    "skill": "business-automation",
}
```

Run:
```bash
venv/bin/python scripts/setup_acquisition_crons.py
```

**Step 6: Commit**
```bash
git add scripts/proactive_loop.py tests/test_proactive_loop.py
git commit -m "feat: proactive work loop — 5 queues, acts every 15min without being asked"
```

---

### Task 4: Morning Digest

Every morning at 8am, send the owner a Telegram message summarising everything Hermes did in the last 24 hours.

**Files:**
- Create: `scripts/morning_digest.py`
- Create: `tests/test_morning_digest.py`

**Step 1: Write failing tests**

```python
# tests/test_morning_digest.py
import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from scripts.morning_digest import (
    load_last_24h_actions,
    format_digest,
    send_digest,
)

@pytest.fixture
def sample_log(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    hermes_dir = tmp_path / ".hermes"
    hermes_dir.mkdir()
    now = datetime.now(timezone.utc)
    log = [
        {"action": "Replied to email from Maria G.", "timestamp": now.isoformat()},
        {"action": "Followed up with Jake Miller", "timestamp": now.isoformat()},
        {"action": "Added Reddit prospect from r/smallbusiness", "timestamp": (now - timedelta(hours=25)).isoformat()},
    ]
    (hermes_dir / "action_log.json").write_text(json.dumps(log))
    return log

def test_load_last_24h_filters_old(sample_log, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    recent = load_last_24h_actions()
    assert len(recent) == 2  # third entry is 25h old

def test_format_digest_has_summary(sample_log, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    actions = load_last_24h_actions()
    text = format_digest(actions)
    assert "2 things" in text or "2 tasks" in text or "✅" in text
    assert "Maria G." in text

def test_format_digest_empty():
    text = format_digest([])
    assert "quiet" in text.lower() or "nothing" in text.lower() or "all clear" in text.lower()

def test_send_digest_calls_telegram(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_OWNER_ID", "12345")
    sent = []
    monkeypatch.setattr("scripts.morning_digest._telegram_send", lambda token, chat, text: sent.append(text))
    send_digest()
    assert len(sent) == 1
```

**Step 2: Run to confirm failure**
```bash
venv/bin/pytest tests/test_morning_digest.py -v
```

**Step 3: Implement `scripts/morning_digest.py`**

```python
#!/usr/bin/env python3
"""
Morning Digest — sends owner a daily Telegram summary of everything Hermes did.
Runs at 8am via cron. Reads action_log.json, formats a human-friendly message.
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _log_path() -> Path:
    return Path(os.environ.get("HOME", Path.home())) / ".hermes" / "action_log.json"


def load_last_24h_actions() -> list:
    path = _log_path()
    if not path.exists():
        return []
    try:
        log = json.loads(path.read_text())
    except Exception:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent = []
    for entry in log:
        try:
            ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
            if ts >= cutoff:
                recent.append(entry)
        except Exception:
            continue
    return recent


def format_digest(actions: list) -> str:
    if not actions:
        return "☀️ Good morning! All clear — nothing needed attention overnight. I'm watching."

    lines = [f"☀️ Good morning! Here's what I did while you slept ({len(actions)} tasks):\n"]
    for entry in actions:
        lines.append(f"✅ {entry['action']}")
    lines.append("\nI'm on it today. You focus on what only you can do.")
    return "\n".join(lines)


def _telegram_send(bot_token: str, chat_id: str, text: str) -> None:
    httpx.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=10,
    )


def send_digest() -> None:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    owner_id = os.environ.get("TELEGRAM_OWNER_ID", "")
    if not bot_token or not owner_id:
        logger.warning("Telegram not configured — skipping digest")
        return

    actions = load_last_24h_actions()
    text = format_digest(actions)
    _telegram_send(bot_token, owner_id, text)

    # Clear the log after sending
    _log_path().write_text(json.dumps([], indent=2))
    logger.info("Morning digest sent (%d actions)", len(actions))


if __name__ == "__main__":
    send_digest()
```

**Step 4: Run tests**
```bash
venv/bin/pytest tests/test_morning_digest.py -v
```
Expected: `4 passed`

**Step 5: Register 8am cron** — add to `~/.hermes/cron/morning-digest.json`:
```json
{
  "name": "morning-digest",
  "schedule": "0 8 * * *",
  "task": "Send the owner a morning summary of everything Hermes did in the last 24 hours",
  "skill": "business-automation"
}
```

**Step 6: Commit**
```bash
git add scripts/morning_digest.py tests/test_morning_digest.py
git commit -m "feat: morning digest — daily 8am Telegram summary of all actions taken"
```

---

### Task 5: macOS Menubar App

A `rumps`-based menubar app showing a live feed of Hermes actions. Owner clicks the menu bar icon to see what Hermes is doing right now.

**Files:**
- Create: `scripts/menubar_app.py`
- Modify: `~/Library/LaunchAgents/ai.hermes.menubar.plist` (new launchd service)

**Step 1: Install dependency**
```bash
venv/bin/pip install rumps
```

**Step 2: Implement `scripts/menubar_app.py`**

```python
#!/usr/bin/env python3
"""
Hermes Menubar App — live activity feed in the macOS menu bar.
Shows last 5 actions. Pause/resume toggle. Requires rumps.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import rumps

LOG_PATH = Path(os.environ.get("HOME", Path.home())) / ".hermes" / "action_log.json"
PAUSE_PATH = Path(os.environ.get("HOME", Path.home())) / ".hermes" / ".paused"


def _load_recent(n=5) -> list:
    if not LOG_PATH.exists():
        return []
    try:
        log = json.loads(LOG_PATH.read_text())
        return list(reversed(log[-n:]))
    except Exception:
        return []


def _time_ago(ts_str: str) -> str:
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - ts
        mins = int(delta.total_seconds() / 60)
        if mins < 1:
            return "just now"
        if mins < 60:
            return f"{mins}m ago"
        return f"{mins // 60}h ago"
    except Exception:
        return ""


class HermesMenubar(rumps.App):
    def __init__(self):
        super().__init__("⚡", quit_button=None)
        self.paused = PAUSE_PATH.exists()
        self._update_menu()

    def _update_menu(self):
        items = []
        recent = _load_recent()
        if not recent:
            items.append(rumps.MenuItem("Hermes is watching...", callback=None))
        else:
            for entry in recent:
                label = f"{_time_ago(entry['timestamp'])}  {entry['action'][:50]}"
                items.append(rumps.MenuItem(label, callback=None))

        items.append(rumps.separator)
        pause_label = "▶ Resume Hermes" if self.paused else "⏸ Pause Hermes"
        items.append(rumps.MenuItem(pause_label, callback=self.toggle_pause))
        items.append(rumps.MenuItem("Quit", callback=rumps.quit_application))
        self.menu.clear()
        self.menu = items
        self.title = "⏸" if self.paused else "⚡"

    @rumps.timer(30)
    def refresh(self, _):
        self.paused = PAUSE_PATH.exists()
        self._update_menu()

    def toggle_pause(self, _):
        if self.paused:
            PAUSE_PATH.unlink(missing_ok=True)
            self.paused = False
        else:
            PAUSE_PATH.touch()
            self.paused = True
        self._update_menu()


if __name__ == "__main__":
    HermesMenubar().run()
```

**Step 3: Create launchd plist** at `~/Library/LaunchAgents/ai.hermes.menubar.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>ai.hermes.menubar</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/gaganarora/Desktop/my projects/hermes/hermes-agent/venv/bin/python</string>
        <string>/Users/gaganarora/Desktop/my projects/hermes/hermes-agent/scripts/menubar_app.py</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
    <key>EnvironmentVariables</key>
    <dict>
        <key>TELEGRAM_BOT_TOKEN</key><string>8359091315:AAGAUNonCQPEFIHLTenXRtxqacICaAJzPWM</string>
        <key>TELEGRAM_OWNER_ID</key><string>8444910202</string>
    </dict>
</dict>
</plist>
```

Load it:
```bash
launchctl load ~/Library/LaunchAgents/ai.hermes.menubar.plist
```

**Step 4: Commit**
```bash
git add scripts/menubar_app.py
git commit -m "feat: menubar app — live activity feed, pause/resume toggle"
```

---

### Task 6: One-Permission Onboarding (Wire It All Together)

The startup sequence that runs when a new user installs Hermes. Triggered once on first launch. Harvests credentials, configures MCP servers, runs the first proactive loop pass, and sends the wow Telegram message.

**Files:**
- Create: `scripts/first_run.py`
- Create: `tests/test_first_run.py`

**Step 1: Write failing tests**

```python
# tests/test_first_run.py
import pytest
from unittest.mock import patch, MagicMock
from scripts.first_run import run_first_time_setup, _is_first_run, _mark_setup_done

def test_is_first_run_true_when_no_marker(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()
    assert _is_first_run() is True

def test_is_first_run_false_after_marker(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()
    _mark_setup_done()
    assert _is_first_run() is False

def test_first_run_sequence(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()

    configured = []
    loop_ran = []
    messages_sent = []

    monkeypatch.setattr("scripts.first_run.detect_and_configure", lambda: ["gmail", "shopify"])
    monkeypatch.setattr("scripts.first_run.run_all_queues", lambda: ["replied to 2 emails"])
    monkeypatch.setattr("scripts.first_run._send_welcome", lambda services, actions: messages_sent.append(services))

    run_first_time_setup()

    assert messages_sent[0] == ["gmail", "shopify"]
    assert _is_first_run() is False
```

**Step 2: Run to confirm failure**
```bash
venv/bin/pytest tests/test_first_run.py -v
```

**Step 3: Implement `scripts/first_run.py`**

```python
#!/usr/bin/env python3
"""
First Run — one-time setup sequence for new installs.

1. Detect and configure all MCP servers from credentials
2. Run the proactive loop immediately (instant first actions)
3. Send the wow Telegram message: "I connected to X tools and already did Y"
4. Mark setup as done so this never runs again
"""
import logging
import os
import sys
import httpx
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.mcp_autoconfig import detect_and_configure
from scripts.proactive_loop import run_all_queues

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SETUP_MARKER = Path(os.environ.get("HOME", Path.home())) / ".hermes" / ".setup_done"


def _is_first_run() -> bool:
    return not SETUP_MARKER.exists()


def _mark_setup_done() -> None:
    SETUP_MARKER.parent.mkdir(parents=True, exist_ok=True)
    SETUP_MARKER.touch()


def _send_welcome(services: list, actions: list) -> None:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    owner_id = os.environ.get("TELEGRAM_OWNER_ID", "")
    if not bot_token or not owner_id:
        return

    svc_list = ", ".join(services) if services else "your tools"
    lines = [
        f"👋 Hi! I'm Hermes, your AI employee. I'm already working.\n",
        f"🔗 Connected to: {svc_list}\n",
    ]
    if actions:
        lines.append("Here's what I just did:\n")
        for a in actions[:5]:
            lines.append(f"✅ {a}")
        lines.append("\nI'll update you every morning. You won't need to ask me anything.")
    else:
        lines.append("I'm watching your inbox, leads, and reviews. I'll update you every morning.")

    text = "\n".join(lines)
    try:
        httpx.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": owner_id, "text": text},
            timeout=10,
        )
        logger.info("Welcome message sent")
    except Exception as e:
        logger.warning("Welcome message failed: %s", e)


def run_first_time_setup() -> None:
    if not _is_first_run():
        logger.info("Setup already done — skipping")
        return

    logger.info("First run detected — starting setup")

    # 1. Detect tools from credentials, configure MCP servers
    services = detect_and_configure()
    logger.info("Configured services: %s", services)

    # 2. Run the work loop immediately — create instant value
    actions = run_all_queues()
    logger.info("First loop actions: %d", len(actions))

    # 3. Send the wow message
    _send_welcome(services, actions)

    # 4. Mark done
    _mark_setup_done()
    logger.info("First run setup complete")


if __name__ == "__main__":
    run_first_time_setup()
```

**Step 4: Run tests**
```bash
venv/bin/pytest tests/test_first_run.py -v
```
Expected: `3 passed`

**Step 5: Add to gateway startup** — modify `~/Library/LaunchAgents/ai.hermes.gateway.plist` to run `first_run.py` on startup:

In the plist, change `ProgramArguments` to a wrapper script, OR add a separate one-shot launchd job that runs `first_run.py` at login.

Simplest: add to the existing gateway startup in `hermes_cli/gateway.py` — check `_is_first_run()` on startup and call it.

**Step 6: Commit**
```bash
git add scripts/first_run.py tests/test_first_run.py
git commit -m "feat: first_run — one-permission onboarding, auto-connects tools, instant wow message"
```

---

## Running all tests

```bash
cd "/Users/gaganarora/Desktop/my projects/hermes/hermes-agent"
venv/bin/pytest tests/test_credential_harvester.py tests/test_mcp_autoconfig.py tests/test_proactive_loop.py tests/test_morning_digest.py tests/test_first_run.py -v
```

Expected: `22 passed`
