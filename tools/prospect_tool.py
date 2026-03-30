"""Prospect Tracker Tool — manage outbound prospects from Reddit, job boards, Google Maps, etc.

Prospects are potential customers found through outbound research.
They are distinct from CRM contacts — they haven't paid yet.
Data is persisted to ~/.hermes/prospects.json.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from tools.registry import registry

logger = logging.getLogger(__name__)

_VALID_STATUSES = {"new", "contacted", "replied", "demo", "converted", "rejected"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _prospects_path() -> str:
    return str(Path.home() / ".hermes" / "prospects.json")


def _load() -> dict:
    p = Path(_prospects_path())
    if not p.exists():
        return {"prospects": {}}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Prospects file corrupted, cannot load: %s", e)
        raise


def _save(data: dict) -> None:
    p = Path(_prospects_path())
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------


def prospect_add_fn(
    name: str,
    source: str,
    pain_point: str,
    source_url: str = "",
    contact_hint: str = "",
    score: int = 5,
) -> str:
    """Add a new prospect to the outbound pipeline."""
    prospect_id = str(uuid.uuid4())[:8]
    now = _now()
    data = _load()
    data.setdefault("prospects", {})[prospect_id] = {
        "id": prospect_id,
        "name": name,
        "source": source,
        "source_url": source_url,
        "pain_point": pain_point,
        "contact_hint": contact_hint,
        "score": score,
        "status": "new",
        "notes": "",
        "created_at": now,
        "updated_at": now,
    }
    _save(data)
    return f"Prospect '{name}' added (id: {prospect_id}, score: {score}/10)."


def prospect_update_fn(
    prospect_id: str,
    status: str = "",
    notes: str = "",
) -> str:
    """Update status and/or notes for an existing prospect."""
    if status and status not in _VALID_STATUSES:
        valid = ", ".join(sorted(_VALID_STATUSES))
        return f"Error: invalid status '{status}'. Valid statuses: {valid}."

    data = _load()
    prospects = data.get("prospects", {})
    if prospect_id not in prospects:
        return f"Error: unknown prospect id '{prospect_id}'."

    p = prospects[prospect_id]
    if status:
        p["status"] = status
    if notes:
        p["notes"] = notes
    p["updated_at"] = _now()
    _save(data)

    name = p.get("name", prospect_id)
    return f"Prospect '{name}' updated: status={p['status']}."


def prospect_list_fn(status: str = "new", limit: int = 20) -> str:
    """List prospects filtered by status, sorted by score descending."""
    data = _load()
    prospects = list(data.get("prospects", {}).values())

    if status:
        prospects = [p for p in prospects if p.get("status") == status]

    if not prospects:
        label = f"status '{status}'" if status else "any status"
        return f"No prospects with {label}."

    prospects.sort(key=lambda p: p.get("score", 0), reverse=True)
    prospects = prospects[:limit]

    lines = []
    for p in prospects:
        pain = p.get("pain_point", "")[:60]
        lines.append(
            f"[{p['id']}] {p['name']} | score:{p.get('score', 0)}/10 "
            f"| src:{p.get('source', '')} | {pain}"
        )
    return "\n".join(lines)


def prospect_digest_fn(limit: int = 10) -> str:
    """Format a Telegram-ready numbered batch digest of NEW prospects for owner approval."""
    data = _load()
    prospects = [
        p for p in data.get("prospects", {}).values()
        if p.get("status") == "new"
    ]

    if not prospects:
        return "No new prospects today."

    prospects.sort(key=lambda p: p.get("score", 0), reverse=True)
    prospects = prospects[:limit]

    lines = []
    for i, p in enumerate(prospects, start=1):
        pain = p.get("pain_point", "")[:80]
        lines.append(
            f"{i}. {p['name']} | score:{p.get('score', 0)}/10 | src:{p.get('source', '')}\n"
            f"   Pain: {pain}\n"
            f"   Contact: {p.get('contact_hint', 'N/A')} | ID: {p['id']}"
        )

    footer = (
        "\nReply APPROVE ALL to send outreach to all, "
        "or REJECT 2,4 to skip those numbers."
    )
    return "\n\n".join(lines) + footer


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

registry.register(
    name="prospect_add",
    toolset="crm",
    schema={
        "name": "prospect_add",
        "description": "Add a new prospect to the outbound pipeline. Use after finding someone who needs an AI employee.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Business or person name"},
                "source": {"type": "string", "description": "Where found: reddit, twitter, indeed, maps, linkedin"},
                "pain_point": {"type": "string", "description": "Their stated pain or problem"},
                "source_url": {"type": "string", "description": "URL of the post or listing where found"},
                "contact_hint": {"type": "string", "description": "How to reach them: username, email, or phone"},
                "score": {"type": "integer", "description": "Fit score 1-10 (10=perfect match)", "default": 5},
            },
            "required": ["name", "source", "pain_point"],
        },
    },
    handler=lambda args, **kw: prospect_add_fn(
        name=args["name"],
        source=args["source"],
        pain_point=args["pain_point"],
        source_url=args.get("source_url", ""),
        contact_hint=args.get("contact_hint", ""),
        score=args.get("score", 5),
    ),
)

registry.register(
    name="prospect_update",
    toolset="crm",
    schema={
        "name": "prospect_update",
        "description": "Update the status and/or notes for a prospect in the outbound pipeline.",
        "parameters": {
            "type": "object",
            "properties": {
                "prospect_id": {"type": "string", "description": "The 8-character prospect ID"},
                "status": {
                    "type": "string",
                    "enum": ["new", "contacted", "replied", "demo", "converted", "rejected"],
                    "description": "New status for the prospect",
                },
                "notes": {"type": "string", "description": "Notes to attach to this prospect"},
            },
            "required": ["prospect_id"],
        },
    },
    handler=lambda args, **kw: prospect_update_fn(
        prospect_id=args["prospect_id"],
        status=args.get("status", ""),
        notes=args.get("notes", ""),
    ),
)

registry.register(
    name="prospect_list",
    toolset="crm",
    schema={
        "name": "prospect_list",
        "description": "List prospects from the outbound pipeline, filtered by status and sorted by score.",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter by status (new, contacted, replied, demo, converted, rejected). Empty string = all.",
                    "default": "new",
                },
                "limit": {"type": "integer", "description": "Maximum number of results to return", "default": 20},
            },
            "required": [],
        },
    },
    handler=lambda args, **kw: prospect_list_fn(
        status=args.get("status", "new"),
        limit=args.get("limit", 20),
    ),
)

registry.register(
    name="prospect_digest",
    toolset="crm",
    schema={
        "name": "prospect_digest",
        "description": "Generate a Telegram-ready numbered batch digest of NEW prospects for owner approval.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Maximum number of prospects to include", "default": 10},
            },
            "required": [],
        },
    },
    handler=lambda args, **kw: prospect_digest_fn(
        limit=args.get("limit", 10),
    ),
)
