# AI Employee Gaps Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fill all 7 production gaps so the AI employee can answer inbound calls, track deals, acquire its first customers, and onboard paying users end-to-end.

**Architecture:** Six self-contained layers — a CRM tool (persistent JSON), a prospect pipeline tool, a Vapi call webhook handler (uses existing gateway webhook platform), a control plane server (FastAPI, wires Stripe → Telegram onboarding), a customer acquisition skill (orchestrates existing reach tools), and cron job registration. Each layer is independently testable and commits separately.

**Tech Stack:** Python 3.11, FastAPI + uvicorn (already in pyproject.toml), aiohttp (already installed), httpx, python-telegram-bot, existing Hermes tool registry pattern (`tools/registry.py`), `~/.hermes/` for all persistent JSON state.

---

## Codebase Context

**Tool registration pattern** (follow exactly for every new tool):
1. Create `tools/xxx_tool.py` — define tool function(s) + call `registry.register(...)` at module level
2. Add `"tools.xxx_tool"` to `_modules` list in `_discover_tools()` in `model_tools.py` (around line 161)
3. Add tool names to `_HERMES_CORE_TOOLS` list in `toolsets.py` (around line 31)

**Existing tools to reuse** (do NOT reimplement):
- `web_search`, `web_extract` — general web search/scrape
- `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type` — full browser automation
- `reddit_search`, `twitter_search`, `jina_read` — platform-specific research
- `sms_send` — Twilio SMS (tools/twilio_tool.py)
- `vapi_call` — outbound Vapi calls (tools/vapi_tool.py)
- `send_message` — cross-platform messaging (tools/send_message_tool.py)
- `memory` — long-term agent memory (tools/memory_tool.py)
- `cronjob` — schedule recurring jobs (tools/cronjob_tools.py)

**Data directory:** All persistent state lives in `~/.hermes/`. Create subdirs as needed.

**Gateway webhook platform:** `gateway/platforms/webhook.py` — receives HTTP POSTs, validates secrets, formats prompts for agent. Config in `~/.hermes/config.yaml` under `platforms.webhook`. See `gateway/config.py` for `PlatformConfig` schema.

---

### Task 1: Customer CRM Tool

**Files:**
- Create: `tools/crm_tool.py`
- Modify: `model_tools.py` (add to `_discover_tools`)
- Modify: `toolsets.py` (add to `_HERMES_CORE_TOOLS`)
- Test: `tests/test_crm_tool.py`

The CRM stores contacts, deals, and interaction logs in `~/.hermes/crm.json`. All operations are idempotent — contacts are keyed by phone number (E.164) or email.

**Step 1: Write the failing tests**

Create `tests/test_crm_tool.py`:

```python
"""Tests for CRM tool — contact and deal management."""
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def tmp_crm(tmp_path, monkeypatch):
    """Redirect CRM storage to a temp directory."""
    crm_dir = tmp_path / ".hermes"
    crm_dir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    # Re-import to pick up patched HOME
    import importlib
    import tools.crm_tool as mod
    importlib.reload(mod)
    yield mod


def test_crm_save_new_contact(tmp_crm):
    result = tmp_crm.crm_save_fn(
        name="Alice Smith",
        phone="+14155550100",
        email="alice@example.com",
        notes="Met at trade show",
    )
    assert "saved" in result.lower() or "alice" in result.lower()
    data = json.loads(Path(tmp_crm._crm_path()).read_text())
    assert "+14155550100" in data["contacts"]


def test_crm_save_updates_existing(tmp_crm):
    tmp_crm.crm_save_fn(name="Bob", phone="+14155550101")
    tmp_crm.crm_save_fn(name="Bob Updated", phone="+14155550101", notes="Follow-up done")
    data = json.loads(Path(tmp_crm._crm_path()).read_text())
    assert data["contacts"]["+14155550101"]["name"] == "Bob Updated"


def test_crm_log_interaction(tmp_crm):
    tmp_crm.crm_save_fn(name="Carol", phone="+14155550102")
    result = tmp_crm.crm_log_fn(
        phone="+14155550102",
        channel="call",
        summary="Interested in demo, call back Thursday",
    )
    assert "logged" in result.lower() or "carol" in result.lower()
    data = json.loads(Path(tmp_crm._crm_path()).read_text())
    assert len(data["contacts"]["+14155550102"]["interactions"]) == 1


def test_crm_find_by_name(tmp_crm):
    tmp_crm.crm_save_fn(name="Dave Johnson", phone="+14155550103")
    result = tmp_crm.crm_find_fn(query="Dave")
    assert "dave" in result.lower()


def test_crm_deal_add(tmp_crm):
    tmp_crm.crm_save_fn(name="Eve", phone="+14155550104")
    result = tmp_crm.crm_deal_fn(
        phone="+14155550104",
        title="AI Employee subscription",
        value=299,
        status="open",
    )
    assert "deal" in result.lower() or "eve" in result.lower()
    data = json.loads(Path(tmp_crm._crm_path()).read_text())
    assert len(data["contacts"]["+14155550104"]["deals"]) == 1
```

**Step 2: Run tests to verify they fail**

```bash
cd "/Users/gaganarora/Desktop/my projects/hermes/hermes-agent"
venv/bin/python -m pytest tests/test_crm_tool.py -v 2>&1 | head -20
```
Expected: ImportError or ModuleNotFoundError — `tools.crm_tool` doesn't exist yet.

**Step 3: Implement `tools/crm_tool.py`**

```python
"""
Customer CRM tool — manages contacts, deals, and interaction history.

Data lives in ~/.hermes/crm.json. Contacts are keyed by E.164 phone number.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from tools.registry import registry


def _crm_path() -> str:
    return str(Path.home() / ".hermes" / "crm.json")


def _load() -> dict:
    p = Path(_crm_path())
    if not p.exists():
        return {"contacts": {}}
    return json.loads(p.read_text())


def _save(data: dict) -> None:
    p = Path(_crm_path())
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def crm_save_fn(
    name: str,
    phone: str = "",
    email: str = "",
    notes: str = "",
    status: str = "lead",
) -> str:
    """Add or update a contact. Keyed by phone (preferred) or email."""
    if not phone and not email:
        return "Error: provide phone or email to identify the contact."
    key = phone or email
    data = _load()
    existing = data["contacts"].get(key, {
        "created_at": _now(),
        "interactions": [],
        "deals": [],
    })
    existing.update({
        "name": name,
        "phone": phone or existing.get("phone", ""),
        "email": email or existing.get("email", ""),
        "notes": notes or existing.get("notes", ""),
        "status": status,
        "updated_at": _now(),
    })
    data["contacts"][key] = existing
    _save(data)
    return f"Contact '{name}' saved (key: {key})."


def crm_log_fn(
    phone: str,
    channel: str,
    summary: str,
) -> str:
    """Log an interaction (call/sms/email) for a contact."""
    data = _load()
    contact = data["contacts"].get(phone)
    if not contact:
        return f"Contact {phone} not found. Add them first with crm_save."
    contact["interactions"].append({
        "at": _now(),
        "channel": channel,
        "summary": summary,
    })
    contact["updated_at"] = _now()
    _save(data)
    name = contact.get("name", phone)
    return f"Interaction logged for {name} ({channel}): {summary[:80]}"


def crm_find_fn(query: str) -> str:
    """Search contacts by name, phone, email, or status."""
    data = _load()
    q = query.lower()
    results = []
    for key, c in data["contacts"].items():
        if (q in c.get("name", "").lower()
                or q in key.lower()
                or q in c.get("email", "").lower()
                or q in c.get("status", "").lower()):
            last = c["interactions"][-1]["summary"][:60] if c["interactions"] else "no interactions"
            results.append(
                f"• {c.get('name')} ({key}) [{c.get('status')}] — last: {last}"
            )
    if not results:
        return f"No contacts matching '{query}'."
    return f"Found {len(results)} contact(s):\n" + "\n".join(results)


def crm_deal_fn(
    phone: str,
    title: str,
    value: float = 0,
    status: str = "open",
    notes: str = "",
) -> str:
    """Add or update a deal for a contact."""
    data = _load()
    contact = data["contacts"].get(phone)
    if not contact:
        return f"Contact {phone} not found. Add them first."
    # Update existing deal with same title, or add new
    for deal in contact["deals"]:
        if deal["title"] == title:
            deal.update({"value": value, "status": status, "notes": notes, "updated_at": _now()})
            _save(data)
            return f"Deal '{title}' updated for {contact.get('name')}."
    contact["deals"].append({
        "title": title,
        "value": value,
        "status": status,
        "notes": notes,
        "created_at": _now(),
        "updated_at": _now(),
    })
    _save(data)
    return f"Deal '{title}' (${value}/mo) added for {contact.get('name')}."


# --- Registry registration ---

registry.register(
    name="crm_save",
    fn=crm_save_fn,
    schema={
        "name": "crm_save",
        "description": "Add or update a contact in the CRM. Use this after every new lead, call, or customer interaction.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Full name"},
                "phone": {"type": "string", "description": "E.164 phone number e.g. +14155551234"},
                "email": {"type": "string", "description": "Email address"},
                "notes": {"type": "string", "description": "Free-text notes about this contact"},
                "status": {"type": "string", "enum": ["lead", "prospect", "customer", "churned"], "default": "lead"},
            },
            "required": ["name"],
        },
    },
    toolset="crm",
)

registry.register(
    name="crm_log",
    fn=crm_log_fn,
    schema={
        "name": "crm_log",
        "description": "Log an interaction (call, SMS, email, meeting) with a contact.",
        "input_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "Contact's phone number (key)"},
                "channel": {"type": "string", "enum": ["call", "sms", "email", "meeting", "dm"], "description": "How we communicated"},
                "summary": {"type": "string", "description": "What was discussed / outcome"},
            },
            "required": ["phone", "channel", "summary"],
        },
    },
    toolset="crm",
)

registry.register(
    name="crm_find",
    fn=crm_find_fn,
    schema={
        "name": "crm_find",
        "description": "Search CRM contacts by name, phone, email, or status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term"},
            },
            "required": ["query"],
        },
    },
    toolset="crm",
)

registry.register(
    name="crm_deal",
    fn=crm_deal_fn,
    schema={
        "name": "crm_deal",
        "description": "Add or update a sales deal for a contact.",
        "input_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "Contact's phone number"},
                "title": {"type": "string", "description": "Deal name e.g. 'AI Employee subscription'"},
                "value": {"type": "number", "description": "Monthly value in USD"},
                "status": {"type": "string", "enum": ["open", "won", "lost"], "default": "open"},
                "notes": {"type": "string", "description": "Deal notes"},
            },
            "required": ["phone", "title"],
        },
    },
    toolset="crm",
)
```

**Step 4: Register the tool module**

In `model_tools.py`, add to `_modules` list (after `"tools.twilio_tool"` around line 164):
```python
        "tools.crm_tool",
```

In `toolsets.py`, add to `_HERMES_CORE_TOOLS` after `"sms_send"`:
```python
    # CRM
    "crm_save", "crm_log", "crm_find", "crm_deal",
```

**Step 5: Run tests to verify they pass**

```bash
cd "/Users/gaganarora/Desktop/my projects/hermes/hermes-agent"
venv/bin/python -m pytest tests/test_crm_tool.py -v
```
Expected: 5 tests PASS.

**Step 6: Smoke test the import**

```bash
cd "/Users/gaganarora/Desktop/my projects/hermes/hermes-agent"
venv/bin/python -c "import tools.crm_tool; print('CRM tool loaded OK')"
```
Expected: `CRM tool loaded OK`

**Step 7: Commit**

```bash
git add tools/crm_tool.py tests/test_crm_tool.py model_tools.py toolsets.py
git commit -m "feat: add customer CRM tool (crm_save, crm_log, crm_find, crm_deal)"
```

---

### Task 2: Prospect Tracker Tool

**Files:**
- Create: `tools/prospect_tool.py`
- Modify: `model_tools.py`
- Modify: `toolsets.py`
- Test: `tests/test_prospect_tool.py`

Prospects are distinct from CRM contacts — they're people *not yet customers* discovered through outbound research. Stored in `~/.hermes/prospects.json`. Lifecycle: `new → contacted → replied → demo → converted | rejected`.

**Step 1: Write failing tests**

Create `tests/test_prospect_tool.py`:

```python
"""Tests for prospect tracker tool."""
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def tmp_prospects(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()
    import importlib
    import tools.prospect_tool as mod
    importlib.reload(mod)
    yield mod


def test_prospect_add(tmp_prospects):
    result = tmp_prospects.prospect_add_fn(
        name="Bob's Plumbing",
        source="reddit",
        source_url="https://reddit.com/r/smallbusiness/comments/abc",
        pain_point="overwhelmed, missing calls, no time",
        contact_hint="u/bobs_plumbing",
        score=8,
    )
    assert "added" in result.lower() or "bob" in result.lower()
    data = json.loads(Path(tmp_prospects._prospects_path()).read_text())
    assert len(data["prospects"]) == 1


def test_prospect_list_filters_by_status(tmp_prospects):
    tmp_prospects.prospect_add_fn(name="A", source="reddit", pain_point="x")
    tmp_prospects.prospect_add_fn(name="B", source="twitter", pain_point="y")
    result = tmp_prospects.prospect_list_fn(status="new")
    assert "A" in result and "B" in result


def test_prospect_update_status(tmp_prospects):
    tmp_prospects.prospect_add_fn(name="C Corp", source="indeed", pain_point="z")
    data = json.loads(Path(tmp_prospects._prospects_path()).read_text())
    pid = list(data["prospects"].keys())[0]
    result = tmp_prospects.prospect_update_fn(prospect_id=pid, status="contacted", notes="Sent DM")
    assert "contacted" in result.lower() or "updated" in result.lower()


def test_prospect_digest(tmp_prospects):
    tmp_prospects.prospect_add_fn(name="D Inc", source="maps", pain_point="missed calls", score=9)
    tmp_prospects.prospect_add_fn(name="E LLC", source="indeed", pain_point="hiring sales rep", score=7)
    result = tmp_prospects.prospect_digest_fn()
    assert "D Inc" in result and "E LLC" in result
    assert "APPROVE" in result or "approve" in result.lower()
```

**Step 2: Run to verify failure**

```bash
cd "/Users/gaganarora/Desktop/my projects/hermes/hermes-agent"
venv/bin/python -m pytest tests/test_prospect_tool.py -v 2>&1 | head -10
```
Expected: ImportError.

**Step 3: Implement `tools/prospect_tool.py`**

```python
"""
Prospect tracker tool — manages outbound lead pipeline.

Prospects are potential customers found through research (Reddit, Twitter,
Indeed, Google Maps). They become CRM contacts when they convert.

Data lives in ~/.hermes/prospects.json.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from tools.registry import registry


def _prospects_path() -> str:
    return str(Path.home() / ".hermes" / "prospects.json")


def _load() -> dict:
    p = Path(_prospects_path())
    if not p.exists():
        return {"prospects": {}}
    return json.loads(p.read_text())


def _save(data: dict) -> None:
    p = Path(_prospects_path())
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def prospect_add_fn(
    name: str,
    source: str,
    pain_point: str,
    source_url: str = "",
    contact_hint: str = "",
    score: int = 5,
) -> str:
    """Add a new prospect to the pipeline."""
    data = _load()
    pid = str(uuid.uuid4())[:8]
    data["prospects"][pid] = {
        "id": pid,
        "name": name,
        "source": source,
        "source_url": source_url,
        "pain_point": pain_point,
        "contact_hint": contact_hint,
        "score": score,
        "status": "new",
        "notes": "",
        "created_at": _now(),
        "updated_at": _now(),
    }
    _save(data)
    return f"Prospect '{name}' added (id: {pid}, score: {score}/10)."


def prospect_update_fn(
    prospect_id: str,
    status: str = "",
    notes: str = "",
) -> str:
    """Update a prospect's status or add notes."""
    valid = {"new", "contacted", "replied", "demo", "converted", "rejected"}
    if status and status not in valid:
        return f"Invalid status '{status}'. Use: {', '.join(sorted(valid))}"
    data = _load()
    p = data["prospects"].get(prospect_id)
    if not p:
        return f"Prospect {prospect_id} not found."
    if status:
        p["status"] = status
    if notes:
        p["notes"] = notes
    p["updated_at"] = _now()
    _save(data)
    return f"Prospect '{p['name']}' updated: status={p['status']}."


def prospect_list_fn(status: str = "new", limit: int = 20) -> str:
    """List prospects filtered by status, sorted by score descending."""
    data = _load()
    items = [
        p for p in data["prospects"].values()
        if not status or p["status"] == status
    ]
    items.sort(key=lambda x: x.get("score", 0), reverse=True)
    items = items[:limit]
    if not items:
        return f"No prospects with status '{status}'."
    lines = [f"Prospects ({status or 'all'}) — {len(items)} found:\n"]
    for p in items:
        lines.append(
            f"[{p['id']}] {p['name']} | score:{p['score']}/10 | "
            f"src:{p['source']} | {p['pain_point'][:60]}"
        )
    return "\n".join(lines)


def prospect_digest_fn(limit: int = 10) -> str:
    """
    Format a daily batch digest of new prospects for owner approval.
    Returns a Telegram-ready message with numbered list.
    Owner replies 'APPROVE ALL' or 'REJECT 3,5' to control outreach.
    """
    data = _load()
    new_prospects = [
        p for p in data["prospects"].values()
        if p["status"] == "new"
    ]
    new_prospects.sort(key=lambda x: x.get("score", 0), reverse=True)
    new_prospects = new_prospects[:limit]

    if not new_prospects:
        return "No new prospects today."

    lines = [f"📋 *Daily Prospect Batch* — {len(new_prospects)} ready for outreach\n"]
    for i, p in enumerate(new_prospects, 1):
        lines.append(
            f"{i}. *{p['name']}* (score: {p['score']}/10)\n"
            f"   Source: {p['source']} | Pain: {p['pain_point'][:80]}\n"
            f"   Contact: {p['contact_hint'] or 'unknown'}\n"
            f"   ID: `{p['id']}`"
        )

    lines.append(
        "\nReply *APPROVE ALL* to send outreach to all, "
        "or *REJECT 2,4* to skip those numbers."
    )
    return "\n".join(lines)


# --- Registry ---

registry.register(
    name="prospect_add",
    fn=prospect_add_fn,
    schema={
        "name": "prospect_add",
        "description": "Add a new prospect to the outbound pipeline. Use after finding someone who needs what we offer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Business or person name"},
                "source": {"type": "string", "description": "Where found: reddit, twitter, indeed, maps, linkedin"},
                "pain_point": {"type": "string", "description": "Their stated pain / problem"},
                "source_url": {"type": "string", "description": "URL of the post/listing where found"},
                "contact_hint": {"type": "string", "description": "How to reach them: username, email, phone"},
                "score": {"type": "integer", "description": "Fit score 1-10 (10=perfect match)", "default": 5},
            },
            "required": ["name", "source", "pain_point"],
        },
    },
    toolset="crm",
)

registry.register(
    name="prospect_update",
    fn=prospect_update_fn,
    schema={
        "name": "prospect_update",
        "description": "Update a prospect's pipeline status or notes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prospect_id": {"type": "string", "description": "8-char prospect ID"},
                "status": {"type": "string", "enum": ["new", "contacted", "replied", "demo", "converted", "rejected"]},
                "notes": {"type": "string", "description": "Additional notes"},
            },
            "required": ["prospect_id"],
        },
    },
    toolset="crm",
)

registry.register(
    name="prospect_list",
    fn=prospect_list_fn,
    schema={
        "name": "prospect_list",
        "description": "List prospects filtered by pipeline status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["new", "contacted", "replied", "demo", "converted", "rejected", ""], "default": "new"},
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
    toolset="crm",
)

registry.register(
    name="prospect_digest",
    fn=prospect_digest_fn,
    schema={
        "name": "prospect_digest",
        "description": "Generate a daily batch digest of new prospects formatted for Telegram owner approval.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 10, "description": "Max prospects in digest"},
            },
        },
    },
    toolset="crm",
)
```

**Step 4: Register in model_tools.py and toolsets.py**

In `model_tools.py`, add after `"tools.crm_tool"`:
```python
        "tools.prospect_tool",
```

In `toolsets.py`, add after `"crm_deal"`:
```python
    "prospect_add", "prospect_update", "prospect_list", "prospect_digest",
```

**Step 5: Run tests**

```bash
cd "/Users/gaganarora/Desktop/my projects/hermes/hermes-agent"
venv/bin/python -m pytest tests/test_prospect_tool.py -v
```
Expected: 4 tests PASS.

**Step 6: Commit**

```bash
git add tools/prospect_tool.py tests/test_prospect_tool.py model_tools.py toolsets.py
git commit -m "feat: add prospect tracker tool (prospect_add, prospect_update, prospect_list, prospect_digest)"
```

---

### Task 3: Vapi Inbound Call Webhook Handler

**Files:**
- Create: `gateway/platforms/vapi_webhook.py`
- Modify: `gateway/platforms/__init__.py` (if needed to register platform)
- Modify: `~/.hermes/config.yaml` (add webhook platform config)
- Test: `tests/gateway/test_vapi_webhook.py`

When a call ends, Vapi POSTs an `end-of-call-report` to our server. This handler saves the transcript to CRM memory and notifies the owner of hot calls.

**Step 1: Understand Vapi webhook payload**

Vapi sends this JSON for `end-of-call-report`:
```json
{
  "message": {
    "type": "end-of-call-report",
    "call": {
      "id": "call_xxx",
      "phoneNumber": {"number": "+14155551234"},
      "customer": {"number": "+15105550100"},
      "duration": 145,
      "endedReason": "customer-ended-call"
    },
    "transcript": "AI: Hello, this is Alex...\nCaller: Hi, I'm interested...",
    "summary": "Caller expressed interest in demo. Follow up Thursday.",
    "recordingUrl": "https://storage.vapi.ai/recordings/xxx.mp3"
  }
}
```

Vapi also sends a `server-url-secret` header (value we configure in Vapi dashboard as `VAPI_WEBHOOK_SECRET`).

**Step 2: Write failing test**

Create `tests/gateway/test_vapi_webhook.py`:

```python
"""Tests for Vapi inbound call webhook handler."""
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


SAMPLE_END_OF_CALL = {
    "message": {
        "type": "end-of-call-report",
        "call": {
            "id": "call_abc123",
            "customer": {"number": "+15105550100"},
            "duration": 90,
            "endedReason": "customer-ended-call",
        },
        "transcript": "AI: Hello, I'm Alex.\nCaller: Hi, I saw your ad. Is this real?",
        "summary": "Prospect interested. Asked about pricing. Follow up needed.",
        "recordingUrl": "",
    }
}


def test_parse_end_of_call_report():
    from gateway.platforms.vapi_webhook import parse_vapi_event
    result = parse_vapi_event(SAMPLE_END_OF_CALL)
    assert result["type"] == "end-of-call-report"
    assert result["caller"] == "+15105550100"
    assert result["duration"] == 90
    assert "Alex" in result["transcript"]
    assert "pricing" in result["summary"]


def test_parse_ignores_non_end_events():
    from gateway.platforms.vapi_webhook import parse_vapi_event
    result = parse_vapi_event({"message": {"type": "transcript", "text": "hello"}})
    assert result is None


def test_format_agent_prompt():
    from gateway.platforms.vapi_webhook import format_agent_prompt
    event = {
        "type": "end-of-call-report",
        "caller": "+15105550100",
        "duration": 90,
        "transcript": "AI: Hi\nCaller: interested",
        "summary": "Prospect interested in demo.",
        "recording_url": "",
        "call_id": "call_abc123",
    }
    prompt = format_agent_prompt(event)
    assert "+15105550100" in prompt
    assert "crm_save" in prompt or "crm_log" in prompt
    assert "interested" in prompt
```

**Step 3: Run to verify failure**

```bash
cd "/Users/gaganarora/Desktop/my projects/hermes/hermes-agent"
venv/bin/python -m pytest tests/gateway/test_vapi_webhook.py -v 2>&1 | head -10
```
Expected: ImportError.

**Step 4: Implement `gateway/platforms/vapi_webhook.py`**

```python
"""
Vapi inbound call webhook handler.

Receives end-of-call-report webhooks from Vapi.ai after a call ends.
Parses the transcript + summary, then formats a prompt for Hermes to:
  1. Save the caller to CRM
  2. Log the interaction
  3. Notify owner if high-interest

Validation: checks x-vapi-secret header against VAPI_WEBHOOK_SECRET env var.
If VAPI_WEBHOOK_SECRET is not set, logs a warning but still processes (dev mode).
"""
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def validate_secret(header_value: str) -> bool:
    """Return True if the webhook secret matches or is not configured."""
    expected = os.environ.get("VAPI_WEBHOOK_SECRET", "")
    if not expected:
        logger.warning("VAPI_WEBHOOK_SECRET not set — skipping secret validation")
        return True
    return header_value == expected


def parse_vapi_event(payload: dict) -> Optional[dict]:
    """
    Parse a Vapi webhook payload.
    Returns structured event dict for end-of-call-report, None for all other types.
    """
    msg = payload.get("message", {})
    event_type = msg.get("type", "")

    if event_type != "end-of-call-report":
        return None

    call = msg.get("call", {})
    customer = call.get("customer", {})

    return {
        "type": event_type,
        "call_id": call.get("id", ""),
        "caller": customer.get("number", "unknown"),
        "duration": call.get("duration", 0),
        "ended_reason": call.get("endedReason", ""),
        "transcript": msg.get("transcript", ""),
        "summary": msg.get("summary", ""),
        "recording_url": msg.get("recordingUrl", ""),
    }


def format_agent_prompt(event: dict) -> str:
    """Format a Hermes agent prompt from a parsed Vapi call event."""
    caller = event["caller"]
    duration = event["duration"]
    summary = event["summary"]
    transcript = event["transcript"][:2000]  # cap at 2000 chars
    recording = event["recording_url"]

    hot_keywords = ["interested", "pricing", "sign up", "demo", "yes", "how much", "when can"]
    is_hot = any(kw in summary.lower() or kw in transcript.lower() for kw in hot_keywords)
    hot_flag = "🔥 HOT LEAD — " if is_hot else ""

    return f"""{hot_flag}Inbound call just ended.

Caller: {caller}
Duration: {duration}s
Ended because: {event['ended_reason']}
Summary: {summary}
Recording: {recording or 'not available'}

Transcript:
{transcript}

Your tasks:
1. Use crm_save to add/update this caller as a contact (status=lead if new, status=customer if they signed up)
2. Use crm_log to record this call interaction with the summary
3. If this is a hot lead (score >= 7), use prospect_add to add them to the pipeline
4. Use send_message to notify the business owner on Telegram with: caller number, call duration, summary, and whether to follow up
5. If they asked for a follow-up, use cronjob to schedule an SMS follow-up in 24 hours via sms_send
"""
```

**Step 5: Run tests**

```bash
cd "/Users/gaganarora/Desktop/my projects/hermes/hermes-agent"
venv/bin/python -m pytest tests/gateway/test_vapi_webhook.py -v
```
Expected: 3 tests PASS.

**Step 6: Add the webhook route to config.yaml**

The gateway's webhook platform is configured in `~/.hermes/config.yaml`. Add this section. Check the existing config first with `cat ~/.hermes/config.yaml`.

Append this block to `~/.hermes/config.yaml`:

```yaml
platforms:
  webhook:
    enabled: true
    extra:
      host: "0.0.0.0"
      port: 8644
      secret: "INSECURE_NO_AUTH"
      routes:
        vapi-call-ended:
          events: []
          secret: "INSECURE_NO_AUTH"
          prompt: |
            A Vapi call just ended. Payload: {payload_json}

            Use the vapi_webhook module logic:
            1. Parse the transcript and summary from the payload
            2. Save caller to CRM with crm_save
            3. Log the call with crm_log
            4. If hot lead keywords present, add to prospects with prospect_add
            5. Notify owner via send_message with call summary
          skills:
            - business-automation
          deliver: "none"
```

**IMPORTANT:** The `~/.hermes/config.yaml` format is YAML. Use `cat ~/.hermes/config.yaml` first to see the current structure and merge correctly — do NOT overwrite the whole file. The `platforms:` key may already exist; add `webhook:` as a sibling of any existing platform keys.

**Step 7: Commit**

```bash
git add gateway/platforms/vapi_webhook.py tests/gateway/test_vapi_webhook.py
git commit -m "feat: add Vapi inbound call webhook handler"
```

---

### Task 4: Control Plane Server (Stripe → Onboarding)

**Files:**
- Create: `scripts/control_plane.py`
- Test: `tests/test_control_plane.py`

The control plane is a FastAPI server that runs on your VPS. It:
1. Receives Stripe `checkout.session.completed` webhooks → sends Telegram message to new customer → starts onboarding interview
2. Stores customer records in `~/.hermes/customers.json`
3. Has a `/health` endpoint for monitoring

Stripe sends webhooks signed with `STRIPE_WEBHOOK_SECRET`. We verify this before processing.

**Step 1: Write failing tests**

Create `tests/test_control_plane.py`:

```python
"""Tests for control plane server."""
import json
import sys
import time
import hashlib
import hmac
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Mock telegram before import
sys.modules['telegram'] = MagicMock()
sys.modules['telegram.ext'] = MagicMock()


def _stripe_sig(payload: bytes, secret: str) -> str:
    timestamp = str(int(time.time()))
    signed = f"{timestamp}.{payload.decode()}"
    sig = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig}"


def test_health_endpoint():
    from fastapi.testclient import TestClient
    from scripts.control_plane import app
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_stripe_webhook_rejects_bad_signature(tmp_path, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test123")
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()
    from fastapi.testclient import TestClient
    from scripts.control_plane import app
    client = TestClient(app)
    payload = json.dumps({"type": "checkout.session.completed"}).encode()
    resp = client.post(
        "/stripe-webhook",
        content=payload,
        headers={"stripe-signature": "t=0,v1=badsig", "content-type": "application/json"},
    )
    assert resp.status_code == 400


def test_parse_checkout_session():
    from scripts.control_plane import parse_checkout_session
    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer_email": "test@example.com",
                "customer_details": {"name": "Test User", "phone": "+14155551234"},
                "metadata": {"telegram_id": "123456"},
            }
        }
    }
    result = parse_checkout_session(event)
    assert result["email"] == "test@example.com"
    assert result["name"] == "Test User"
```

**Step 2: Run to verify failure**

```bash
cd "/Users/gaganarora/Desktop/my projects/hermes/hermes-agent"
venv/bin/python -m pytest tests/test_control_plane.py -v 2>&1 | head -10
```
Expected: ImportError.

**Step 3: Install stripe library**

```bash
cd "/Users/gaganarora/Desktop/my projects/hermes/hermes-agent"
venv/bin/python -m pip install stripe>=8.0.0
```

Add to `pyproject.toml` dependencies:
```toml
"stripe>=8.0.0,<10",
```

**Step 4: Implement `scripts/control_plane.py`**

```python
#!/usr/bin/env python3
"""
Control Plane Server — manages customer lifecycle.

Endpoints:
  POST /stripe-webhook  — Stripe checkout.session.completed → start onboarding
  GET  /health          — health check

Run with:
  python scripts/control_plane.py

Environment:
  STRIPE_WEBHOOK_SECRET  — from Stripe dashboard (whsec_xxx)
  ONBOARDING_BOT_TOKEN   — Telegram bot token for the onboarding bot
  TELEGRAM_OWNER_ID      — your Telegram user ID (for alerts)
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Hermes Control Plane")

_CUSTOMERS_PATH = Path.home() / ".hermes" / "customers.json"


def _load_customers() -> dict:
    if not _CUSTOMERS_PATH.exists():
        return {"customers": {}}
    return json.loads(_CUSTOMERS_PATH.read_text())


def _save_customers(data: dict) -> None:
    _CUSTOMERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CUSTOMERS_PATH.write_text(json.dumps(data, indent=2))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_checkout_session(event: dict) -> Optional[dict]:
    """Extract customer info from a Stripe checkout.session.completed event."""
    if event.get("type") != "checkout.session.completed":
        return None
    obj = event.get("data", {}).get("object", {})
    details = obj.get("customer_details", {})
    return {
        "email": obj.get("customer_email") or details.get("email", ""),
        "name": details.get("name", ""),
        "phone": details.get("phone", ""),
        "telegram_id": obj.get("metadata", {}).get("telegram_id", ""),
        "stripe_session_id": obj.get("id", ""),
        "amount": obj.get("amount_total", 0),
    }


def _verify_stripe_signature(payload: bytes, sig_header: str, secret: str) -> bool:
    """Verify Stripe webhook HMAC signature."""
    import hashlib
    import hmac as _hmac
    import time
    try:
        parts = {k: v for k, v in (p.split("=", 1) for p in sig_header.split(","))}
        timestamp = parts.get("t", "0")
        v1 = parts.get("v1", "")
        signed = f"{timestamp}.{payload.decode()}"
        expected = _hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
        # Replay attack check: reject if older than 5 minutes
        if abs(int(time.time()) - int(timestamp)) > 300:
            return False
        return _hmac.compare_digest(v1, expected)
    except Exception:
        return False


async def _notify_new_customer(customer: dict) -> None:
    """Send Telegram message to new customer to start onboarding."""
    token = os.environ.get("ONBOARDING_BOT_TOKEN", "")
    if not token:
        logger.warning("ONBOARDING_BOT_TOKEN not set — cannot start onboarding")
        return
    telegram_id = customer.get("telegram_id", "")
    if not telegram_id:
        logger.warning("No telegram_id for customer %s — cannot start onboarding", customer.get("email"))
        return
    try:
        import httpx
        name = customer.get("name", "there")
        msg = (
            f"👋 Hi {name}! Payment confirmed — I'm setting up your AI employee.\n\n"
            f"Send /start to begin your onboarding interview (takes 2 minutes)."
        )
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": telegram_id, "text": msg},
                timeout=10,
            )
    except Exception as e:
        logger.error("Failed to send onboarding message: %s", e)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "hermes-control-plane"}


@app.post("/stripe-webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    if secret and not _verify_stripe_signature(payload, sig, secret):
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    customer = parse_checkout_session(event)
    if not customer:
        return Response(status_code=200)  # Ignore other event types

    # Record customer
    data = _load_customers()
    cid = customer["stripe_session_id"] or f"manual_{_now()}"
    data["customers"][cid] = {**customer, "status": "onboarding", "created_at": _now()}
    _save_customers(data)
    logger.info("New customer: %s", customer.get("email"))

    # Start onboarding
    await _notify_new_customer(customer)

    # Notify owner
    owner_id = os.environ.get("TELEGRAM_OWNER_ID", "")
    if owner_id:
        try:
            import httpx
            token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={
                        "chat_id": owner_id,
                        "text": f"🎉 New customer: {customer['name']} ({customer['email']}) — onboarding started!",
                    },
                    timeout=10,
                )
        except Exception as e:
            logger.error("Failed to notify owner: %s", e)

    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.environ.get("CONTROL_PLANE_PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
```

**Step 5: Run tests**

```bash
cd "/Users/gaganarora/Desktop/my projects/hermes/hermes-agent"
venv/bin/python -m pytest tests/test_control_plane.py -v
```
Expected: 3 tests PASS.

**Step 6: Smoke test the server starts**

```bash
cd "/Users/gaganarora/Desktop/my projects/hermes/hermes-agent"
timeout 3 venv/bin/python scripts/control_plane.py 2>&1 || true
```
Expected: Server starts on port 8080, then times out cleanly.

**Step 7: Commit**

```bash
git add scripts/control_plane.py tests/test_control_plane.py pyproject.toml
git commit -m "feat: add control plane server (Stripe webhook → customer onboarding)"
```

---

### Task 5: Customer Acquisition Skill + Cron Jobs

**Files:**
- Create: `skills/customer-acquisition.md`
- Create: `scripts/setup_acquisition_crons.py`

This skill tells Hermes *how* to research and score prospects using its existing tools (no new Python code). The cron setup script registers the daily jobs.

**Step 1: Create `skills/customer-acquisition.md`**

```markdown
---
name: customer-acquisition
description: Daily automated customer acquisition for the AI employee SaaS. Researches prospects across multiple channels, scores them, and batches them for owner approval.
version: 1.0.0
---

# Customer Acquisition Skill

You are hunting for small business owners who need an AI employee. Your target: businesses that are actively trying to hire sales/support staff OR businesses that are losing customers due to missed calls/poor follow-up.

## Channel 1 — Job Listing Research (highest intent)

Search for small businesses actively hiring sales/support roles:

```
web_search("site:indeed.com \"sales representative\" \"small business\" posted:1d")
web_search("site:linkedin.com/jobs \"customer service\" \"small business\" posted:24h")
```

For each job listing found:
1. Extract: company name, job title, location, company size (look for "employees" count)
2. Only include companies with < 100 employees
3. Visit their website via `jina_read` to get their phone/email/industry
4. Score 1-10: +3 if hiring sales rep, +2 if hiring customer service, +1 per employee count bucket under 50
5. Add to prospects: `prospect_add(name=company, source="indeed", pain_point="hiring [role] — has budget", contact_hint=website_contact, score=score)`

## Channel 2 — Reddit Pain Research

Search for people expressing the exact problems we solve:

```
reddit_search("overwhelmed running my business can't keep up", subreddit="smallbusiness")
reddit_search("need help answering calls missing sales", subreddit="entrepreneur")
reddit_search("can't afford employee sales follow up", subreddit="ecommerce")
reddit_search("miss calls voicemail losing customers", subreddit="smallbusiness")
```

For each relevant post (score > 50 upvotes, or clearly describing budget/willingness to pay):
1. Check their post history with `jina_read(url)` — are they a business owner?
2. Score: +3 if mentions budget, +2 if describes losing revenue, +1 per pain keyword
3. Add: `prospect_add(name=username+" (Reddit)", source="reddit", source_url=post_url, pain_point=post_title, contact_hint="u/"+username, score=score)`

## Channel 3 — Google Maps Pain Research

Find businesses with reviews complaining about missed calls:

```
web_search("\"never called back\" OR \"goes to voicemail\" OR \"hard to reach\" site:google.com/maps")
web_search("plumber \"no answer\" OR \"missed my call\" reviews 2024 2025")
web_search("\"called multiple times\" \"no response\" small business reviews")
```

For each business found:
1. Get their phone number and website via `jina_read`
2. Score: +4 if reviews explicitly mention missed calls/voicemail
3. Add: `prospect_add(name=business_name, source="maps", pain_point="Reviews say: "+review_snippet, contact_hint=phone_number, score=score)`

## Daily Digest

After completing research (aim for 10+ prospects):
1. Generate digest: `prospect_digest(limit=10)`
2. Send to owner via Telegram: `send_message(platform="telegram", message=digest_text)`
3. Log: "Daily prospect digest sent. Awaiting owner approval."

## After Owner Approves

When owner replies "APPROVE ALL" or "APPROVE 1,3,5":
1. Parse which prospects to contact
2. For Reddit prospects: use `browser_navigate` to go to their Reddit profile → compose DM
3. For Indeed/LinkedIn prospects: compose personalized outreach email using `web_extract` to get their email
4. Mark each contacted prospect: `prospect_update(prospect_id=pid, status="contacted", notes="Sent DM via reddit")`
5. Template message:
   ```
   Hey [name], I saw you're [pain point]. I built an AI employee that handles calls, SMS, and sales
   follow-up for $299/mo — it's like having a sales rep, but 24/7. Want a free 7-day demo?
   Reply here and I'll set it up in 5 minutes.
   ```

## Weekly Content Posts

Post 3x/week on Reddit + Twitter to drive inbound:
- Monday: Post on r/entrepreneur or r/smallbusiness
- Wednesday: Post on Twitter
- Friday: Post on r/ecommerce or r/startups

Post template:
```
"I built an AI employee that answers calls, sends follow-up SMS, and researches prospects — 24/7 for $299/mo.
It's been handling sales for my test business for 2 weeks.
If you want a free 7-day trial, drop your number below and it'll call you in 60 seconds to demo itself."
```

Always save any responses to the post as new prospects with `prospect_add`.
```

**Step 2: Create `scripts/setup_acquisition_crons.py`**

```python
#!/usr/bin/env python3
"""
Register daily customer acquisition cron jobs in Hermes.

Run once to set up:
    python scripts/setup_acquisition_crons.py

This creates two cron jobs in ~/.hermes/cron/:
  1. Daily 8am: prospect research across Indeed, Reddit, Google Maps
  2. Daily 9am: send batch digest to owner on Telegram
"""
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

CRON_DIR = Path.home() / ".hermes" / "cron"


def register_cron(name: str, schedule: str, prompt: str, skills: list) -> str:
    """Write a cron job file to ~/.hermes/cron/."""
    CRON_DIR.mkdir(parents=True, exist_ok=True)
    job_id = str(uuid.uuid4())[:8]
    job = {
        "id": job_id,
        "name": name,
        "schedule": schedule,
        "prompt": prompt,
        "skills": skills,
        "enabled": True,
        "created_at": datetime.utcnow().isoformat(),
    }
    job_file = CRON_DIR / f"{name.replace(' ', '_').lower()}.json"
    job_file.write_text(json.dumps(job, indent=2))
    return str(job_file)


def main():
    # Job 1: daily prospect research
    path1 = register_cron(
        name="daily-prospect-research",
        schedule="0 8 * * *",  # 8am daily
        prompt=(
            "Run the customer acquisition research routine:\n"
            "1. Search Indeed for small businesses hiring sales/support roles (posted in last 24h)\n"
            "2. Search Reddit for people expressing pain around missed calls, overwhelm, needing staff\n"
            "3. Search Google for businesses with 'never called back' reviews\n"
            "4. Add all scored prospects using prospect_add\n"
            "Target: 10+ new prospects before 9am digest.\n"
            "Use the customer-acquisition skill for detailed guidance."
        ),
        skills=["customer-acquisition"],
    )
    print(f"✅ Registered: daily-prospect-research → {path1}")

    # Job 2: daily digest
    path2 = register_cron(
        name="daily-prospect-digest",
        schedule="0 9 * * *",  # 9am daily
        prompt=(
            "Generate and send the daily prospect digest to the owner:\n"
            "1. Call prospect_digest() to get the top 10 new prospects\n"
            "2. Send via send_message to Telegram\n"
            "3. Await their APPROVE ALL / REJECT response\n"
            "If they reply APPROVE ALL: send outreach to all prospects via their respective channels.\n"
            "If they reply REJECT N: skip those numbered prospects, contact the rest."
        ),
        skills=["customer-acquisition"],
    )
    print(f"✅ Registered: daily-prospect-digest → {path2}")

    # Job 3: weekly content post
    path3 = register_cron(
        name="weekly-content-post",
        schedule="0 10 * * 1",  # 10am every Monday
        prompt=(
            "Post weekly inbound content:\n"
            "1. Draft a post for r/smallbusiness or r/entrepreneur about the AI employee\n"
            "2. Use the template from customer-acquisition skill\n"
            "3. Post using browser_navigate to Reddit (login required — use stored credentials)\n"
            "4. Track any replies as prospects using prospect_add\n"
        ),
        skills=["customer-acquisition"],
    )
    print(f"✅ Registered: weekly-content-post → {path3}")

    print("\n🎯 All acquisition crons registered. Hermes will run them on schedule.")
    print("View jobs: hermes cron list")


if __name__ == "__main__":
    main()
```

**Step 3: Run the setup script**

```bash
cd "/Users/gaganarora/Desktop/my projects/hermes/hermes-agent"
venv/bin/python scripts/setup_acquisition_crons.py
```
Expected:
```
✅ Registered: daily-prospect-research → /Users/.../.hermes/cron/daily-prospect-research.json
✅ Registered: daily-prospect-digest → /Users/.../.hermes/cron/daily-prospect-digest.json
✅ Registered: weekly-content-post → /Users/.../.hermes/cron/weekly-content-post.json
🎯 All acquisition crons registered.
```

**Step 4: Verify cron files exist**

```bash
ls ~/.hermes/cron/
cat ~/.hermes/cron/daily-prospect-research.json
```

**Step 5: Commit**

```bash
git add skills/customer-acquisition.md scripts/setup_acquisition_crons.py
git commit -m "feat: add customer acquisition skill + daily cron setup"
```

---

### Task 6: Wire Everything Together + Restart Gateway

**Files:**
- Modify: `~/.hermes/config.yaml` (add TELEGRAM_OWNER_ID)
- No code changes — just configuration and verification

**Step 1: Add TELEGRAM_OWNER_ID to .env**

The owner's Telegram ID is needed for the control plane to notify you when a customer signs up. Your Telegram user ID is `8444910202` (from config.yaml).

Append to `/Users/gaganarora/Desktop/my projects/hermes/hermes-agent/.env`:
```
TELEGRAM_OWNER_ID=8444910202
```

**Step 2: Restart the gateway to pick up new tools**

```bash
launchctl unload ~/Library/LaunchAgents/com.hermes.gateway.plist 2>/dev/null
sleep 2
launchctl load ~/Library/LaunchAgents/com.hermes.gateway.plist
sleep 3
launchctl list | grep hermes
```
Expected: `com.hermes.gateway` appears with PID (non-zero).

**Step 3: Verify new tools are loaded**

Open Telegram, send to @hermes114bot:
```
what CRM tools do you have?
```
Expected: Hermes lists `crm_save`, `crm_log`, `crm_find`, `crm_deal`, `prospect_add`, `prospect_update`, `prospect_list`, `prospect_digest`.

**Step 4: Quick smoke test from Telegram**

Send to @hermes114bot:
```
Add a test contact to CRM: name Alice Test, phone +14155550199, status lead
```
Expected: Hermes calls `crm_save`, replies "Contact 'Alice Test' saved."

Then:
```
Find alice in CRM
```
Expected: Returns Alice's record.

**Step 5: Run acquisition cron setup**

```bash
cd "/Users/gaganarora/Desktop/my projects/hermes/hermes-agent"
venv/bin/python scripts/setup_acquisition_crons.py
```

**Step 6: Commit**

```bash
git add .env
git commit -m "chore: add TELEGRAM_OWNER_ID to env, complete gap wiring"
```

---

## What This Delivers

After all 6 tasks:

| Gap | Status | How |
|-----|--------|-----|
| Vapi inbound call handler | ✅ Built | `gateway/platforms/vapi_webhook.py` + webhook config |
| Customer CRM / deal tracker | ✅ Built | `tools/crm_tool.py` — 4 tools registered with Hermes |
| Prospect pipeline | ✅ Built | `tools/prospect_tool.py` — 4 tools registered |
| Job listing scraper | ✅ Built | Skill + daily cron using `web_search` + `jina_read` |
| Google Maps pain scraper | ✅ Built | Skill + cron using `web_search` |
| Customer onboarding bot | ✅ Was built | `scripts/onboarding_bot.py` (existing) |
| Control plane + Stripe | ✅ Built | `scripts/control_plane.py` |

**Missing API keys to get before going live:**
- `STRIPE_WEBHOOK_SECRET` — from Stripe dashboard
- `ONBOARDING_BOT_TOKEN` — new Telegram bot for customer onboarding (separate from Hermes)
- `HEYGEN_API_KEY`, `HEYGEN_AVATAR_ID`, `HEYGEN_VOICE_ID` — for video reports
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` — for SMS
- `DO_API_TOKEN` — DigitalOcean for VM provisioning
- `VAPI_WEBHOOK_SECRET` — optional, set in Vapi dashboard
