"""
Customer CRM Tool — manage contacts, deals, and interaction history.

Data is persisted to ~/.hermes/crm.json.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from tools.registry import registry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _crm_path() -> str:
    return str(Path.home() / ".hermes" / "crm.json")


def _load() -> dict:
    p = Path(_crm_path())
    if not p.exists():
        return {"contacts": {}}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.error("CRM file corrupted, cannot load: %s", e)
        raise


def _save(data: dict) -> None:
    p = Path(_crm_path())
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_contact(data: dict, key: str) -> "tuple[str, dict] | tuple[None, None]":
    """Find a contact by phone or email key. Returns (key, contact) or (None, None)."""
    contacts = data.get("contacts", {})
    if key in contacts:
        return key, contacts[key]
    # Also search by stored phone/email fields
    for k, c in contacts.items():
        if c.get("phone") == key or c.get("email") == key:
            return k, c
    return None, None


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------

def crm_save_fn(
    name: str,
    phone: str = "",
    email: str = "",
    notes: str = "",
    status: str = "lead",
) -> str:
    """Add or update a contact in the CRM."""
    phone = (phone or "").strip()
    email = (email or "").strip()

    if not phone and not email:
        return "Error: provide at least a phone number or email address."

    key = phone if phone else email

    data = _load()
    contacts = data.setdefault("contacts", {})
    now = _now()

    if key in contacts:
        c = contacts[key]
        c["name"] = name
        if phone:
            c["phone"] = phone
        if email:
            c["email"] = email
        if notes:
            c["notes"] = notes
        c["status"] = status
        c["updated_at"] = now
        action = "updated"
    else:
        contacts[key] = {
            "name": name,
            "phone": phone,
            "email": email,
            "notes": notes,
            "status": status,
            "created_at": now,
            "updated_at": now,
            "interactions": [],
            "deals": [],
        }
        action = "saved"

    _save(data)
    return f"Contact '{name}' {action} (key: {key})."


def crm_log_fn(phone: str, channel: str, summary: str) -> str:
    """Log an interaction for a contact."""
    phone = (phone or "").strip()
    data = _load()

    _key, contact = _find_contact(data, phone)
    if contact is None:
        return f"Error: no contact found with phone '{phone}'."

    now = _now()
    contact.setdefault("interactions", []).append({
        "at": now,
        "channel": channel,
        "summary": summary,
    })
    contact["updated_at"] = now
    _save(data)

    name = contact.get("name", phone)

    # Auto-update business wiki in background (Karpathy LLM-wiki pattern)
    try:
        from tools.wiki_tool import crm_log_wiki_hook
        crm_log_wiki_hook(phone=phone, channel=channel, summary=summary, contact_name=name)
    except Exception:
        pass  # wiki hook is non-critical

    return f"Interaction logged for {name} ({channel}): {summary[:80]}"


def crm_find_fn(query: str) -> str:
    """Search contacts by name, phone, email, or status."""
    query_lower = query.lower()
    data = _load()
    contacts = data.get("contacts", {})

    matches = []
    for key, c in contacts.items():
        if (
            query_lower in c.get("name", "").lower()
            or query_lower in c.get("phone", "").lower()
            or query_lower in c.get("email", "").lower()
            or query_lower in c.get("status", "").lower()
        ):
            interactions = c.get("interactions", [])
            last = interactions[-1]["summary"][:60] if interactions else "none"
            matches.append(
                f"{c.get('name', key)} | {c.get('phone', '')} | {c.get('email', '')} "
                f"| {c.get('status', '')} | last: {last}"
            )

    if not matches:
        return f"No contacts matching '{query}'."
    return "\n".join(matches)


def crm_deal_fn(
    phone: str,
    title: str,
    value: float = 0,
    status: str = "open",
    notes: str = "",
) -> str:
    """Add or update a deal for a contact."""
    phone = (phone or "").strip()
    data = _load()

    _key, contact = _find_contact(data, phone)
    if contact is None:
        return f"Error: no contact found with phone '{phone}'."
    contact.setdefault("deals", [])
    now = _now()

    # Find existing deal by title
    existing = next((d for d in contact["deals"] if d["title"] == title), None)

    if existing:
        existing["value"] = value
        existing["status"] = status
        if notes:
            existing["notes"] = notes
        existing["updated_at"] = now
        action = "updated"
    else:
        contact["deals"].append({
            "title": title,
            "value": value,
            "status": status,
            "notes": notes,
            "created_at": now,
            "updated_at": now,
        })
        action = "added"

    contact["updated_at"] = now
    _save(data)

    name = contact.get("name", phone)
    if action == "added":
        return f"Deal '{title}' (${value}) added for {name}."
    return f"Deal '{title}' updated for {name}."


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

registry.register(
    name="crm_save",
    toolset="crm",
    schema={
        "name": "crm_save",
        "description": "Add or update a contact in the CRM. Use this after every new lead, call, or customer interaction.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Full name"},
                "phone": {"type": "string", "description": "E.164 phone number e.g. +14155551234"},
                "email": {"type": "string", "description": "Email address"},
                "notes": {"type": "string", "description": "Free-text notes about this contact"},
                "status": {
                    "type": "string",
                    "enum": ["lead", "prospect", "customer", "churned"],
                    "description": "Contact status",
                    "default": "lead",
                },
            },
            "required": ["name"],
        },
    },
    handler=lambda args, **kw: crm_save_fn(
        name=args["name"],
        phone=args.get("phone", ""),
        email=args.get("email", ""),
        notes=args.get("notes", ""),
        status=args.get("status", "lead"),
    ),
)

registry.register(
    name="crm_log",
    toolset="crm",
    schema={
        "name": "crm_log",
        "description": "Log an interaction for a contact (call, SMS, email, meeting, or DM).",
        "parameters": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "E.164 phone number of the contact"},
                "channel": {
                    "type": "string",
                    "enum": ["call", "sms", "email", "meeting", "dm"],
                    "description": "Communication channel used",
                },
                "summary": {"type": "string", "description": "Brief summary of the interaction"},
            },
            "required": ["phone", "channel", "summary"],
        },
    },
    handler=lambda args, **kw: crm_log_fn(
        phone=args["phone"],
        channel=args["channel"],
        summary=args["summary"],
    ),
)

registry.register(
    name="crm_find",
    toolset="crm",
    schema={
        "name": "crm_find",
        "description": "Search CRM contacts by name, phone, email, or status.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search string (name, phone, email, or status)"},
            },
            "required": ["query"],
        },
    },
    handler=lambda args, **kw: crm_find_fn(query=args["query"]),
)

registry.register(
    name="crm_deal",
    toolset="crm",
    schema={
        "name": "crm_deal",
        "description": "Add or update a deal for a CRM contact.",
        "parameters": {
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "E.164 phone number of the contact"},
                "title": {"type": "string", "description": "Deal title (used as unique key)"},
                "value": {"type": "number", "description": "Monthly value in dollars", "default": 0},
                "status": {
                    "type": "string",
                    "enum": ["open", "won", "lost"],
                    "description": "Deal status",
                    "default": "open",
                },
                "notes": {"type": "string", "description": "Notes about the deal"},
            },
            "required": ["phone", "title"],
        },
    },
    handler=lambda args, **kw: crm_deal_fn(
        phone=args["phone"],
        title=args["title"],
        value=args.get("value", 0),
        status=args.get("status", "open"),
        notes=args.get("notes", ""),
    ),
)
