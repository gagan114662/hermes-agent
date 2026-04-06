"""
Feedback Tool — Scope Guard + Bug Triage

Every feedback item goes through a two-question filter:
1. Is this in scope?
2. Is this a bug or a preference?

Scope creep doesn't happen because clients are difficult.
It happens because the proposal was vague enough that both parties
had different mental models of what was being built.
"""

import json
import os
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

from tools.registry import registry


def _projects_dir(client: str) -> Path:
    safe = client.lower().replace(" ", "_").replace("/", "_")
    d = Path(os.path.expanduser(f"~/.hermes/projects/{safe}"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_feedback(client: str) -> dict:
    path = _projects_dir(client) / "feedback.json"
    if path.exists():
        return json.loads(path.read_text())
    return {"items": []}


def _save_feedback(client: str, data: dict) -> None:
    path = _projects_dir(client) / "feedback.json"
    path.write_text(json.dumps(data, indent=2))


def _ollama(prompt: str, timeout: int = 45) -> str:
    model = os.environ.get("OLLAMA_MODEL", "gemma3:4b")
    base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(
        f"{base}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read()).get("response", "").strip()
    except Exception as e:
        return f"Error: {e}"


def feedback_log(client_name: str, request: str, description: str = "") -> str:
    """
    Log a client feedback item and automatically triage it.

    Runs two-question filter:
    1. Is this in scope? (checks SOW)
    2. Is this a bug or a preference change?

    Routes to: bug (fix within SLA) or change_request (needs pricing)

    Args:
        client_name: Client name
        request: Short description of what the client is asking for
        description: Full details of the request (optional)
    """
    # Check SOW if available
    sow_path = _projects_dir(client_name) / "sow.md"
    sow_context = sow_path.read_text()[:1500] if sow_path.exists() else "(No SOW found)"

    full_request = f"{request}: {description}" if description else request

    prompt = f"""You are a project manager triaging a client feedback item.

SOW (what was agreed):
{sow_context}

Client request: "{full_request}"

Answer these two questions:

Q1: Is this in scope?
Options: IN_SCOPE / OUT_OF_SCOPE
Reason: (one sentence)

Q2: Is this a bug or a preference?
- BUG: Something agreed to in the SOW is broken or not working as specified
- CHANGE_REQUEST: Client wants something different from what was specified (even if it seems minor)
Type: BUG / CHANGE_REQUEST
Reason: (one sentence)

Action: (one sentence — what should happen next)

Format:
Q1_RESULT: [IN_SCOPE / OUT_OF_SCOPE]
Q1_REASON: ...
Q2_TYPE: [BUG / CHANGE_REQUEST]
Q2_REASON: ...
ACTION: ..."""

    triage = _ollama(prompt, timeout=45)

    # Parse triage result
    fb_type = "change_request"
    if "Q2_TYPE: BUG" in triage or "Q2_TYPE:BUG" in triage:
        fb_type = "bug"
    if "OUT_OF_SCOPE" in triage:
        fb_type = "change_request"

    feedback_id = str(uuid.uuid4())[:8]
    data = _load_feedback(client_name)
    data["items"].append({
        "id": feedback_id,
        "request": request,
        "description": description,
        "type": fb_type,
        "status": "open",
        "triage": triage,
        "created_at": datetime.now().isoformat(),
        "resolved_at": None,
        "resolution": "",
    })
    _save_feedback(client_name, data)

    type_label = "🐛 BUG" if fb_type == "bug" else "📋 CHANGE REQUEST"
    action = "Fix within SLA." if fb_type == "bug" else "Price and scope as separate engagement before doing any work."

    return (
        f"Feedback logged [{feedback_id}] for {client_name}.\n"
        f"Type: {type_label}\n\n"
        f"Triage:\n{triage}\n\n"
        f"Action: {action}"
    )


def feedback_list(client_name: str, feedback_type: str = "all") -> str:
    """
    List open feedback items for a client.

    Args:
        client_name: Client name
        feedback_type: Filter by 'bug', 'change_request', or 'all' (default)
    """
    data = _load_feedback(client_name)
    items = data.get("items", [])

    if not items:
        return f"No feedback logged for '{client_name}'."

    if feedback_type != "all":
        items = [i for i in items if i["type"] == feedback_type]

    open_items = [i for i in items if i["status"] == "open"]
    resolved = [i for i in items if i["status"] == "resolved"]

    lines = [f"Feedback for {client_name}: {len(open_items)} open, {len(resolved)} resolved\n"]

    if open_items:
        lines.append("OPEN:")
        for item in open_items:
            icon = "🐛" if item["type"] == "bug" else "📋"
            lines.append(f"  {icon} [{item['id']}] {item['request']}")
            lines.append(f"     Type: {item['type']} | {item['created_at'][:10]}")

    if resolved:
        lines.append(f"\nRESOLVED ({len(resolved)}):")
        for item in resolved[-3:]:  # last 3
            lines.append(f"  ✅ [{item['id']}] {item['request']} — {item['resolution'][:60]}")

    lines.append(f"\nUse feedback_resolve('{client_name}', feedback_id, resolution) to close items.")
    return "\n".join(lines)


def feedback_resolve(client_name: str, feedback_id: str, resolution: str) -> str:
    """
    Mark a feedback item as resolved. Document the resolution and root cause.

    Args:
        client_name: Client name
        feedback_id: The 8-character feedback ID
        resolution: What was done to resolve it (including root cause for bugs)
    """
    data = _load_feedback(client_name)
    for item in data["items"]:
        if item["id"] == feedback_id:
            item["status"] = "resolved"
            item["resolution"] = resolution
            item["resolved_at"] = datetime.now().isoformat()
            _save_feedback(client_name, data)
            return (
                f"Feedback [{feedback_id}] resolved.\n"
                f"Request: {item['request']}\n"
                f"Resolution: {resolution}"
            )
    return f"Feedback item '{feedback_id}' not found for '{client_name}'."


registry.register(
    name="feedback_log",
    toolset="crm",
    schema={
        "name": "feedback_log",
        "description": "Log a client feedback item and automatically triage it as a BUG (fix within SLA) or CHANGE_REQUEST (needs pricing as new scope). Run this before acting on ANY client request — prevents scope creep.",
        "parameters": {
            "type": "object",
            "properties": {
                "client_name": {"type": "string", "description": "Client name"},
                "request": {"type": "string", "description": "Short description of what the client is asking for"},
                "description": {"type": "string", "description": "Full details of the request (optional)"},
            },
            "required": ["client_name", "request"],
        },
    },
    handler=lambda args, **kw: feedback_log(
        client_name=args["client_name"],
        request=args["request"],
        description=args.get("description", ""),
    ),
)

registry.register(
    name="feedback_list",
    toolset="crm",
    schema={
        "name": "feedback_list",
        "description": "List open and resolved feedback items for a client. Filter by 'bug', 'change_request', or 'all'.",
        "parameters": {
            "type": "object",
            "properties": {
                "client_name": {"type": "string", "description": "Client name"},
                "feedback_type": {"type": "string", "enum": ["bug", "change_request", "all"], "description": "Filter type (default: all)", "default": "all"},
            },
            "required": ["client_name"],
        },
    },
    handler=lambda args, **kw: feedback_list(
        client_name=args["client_name"],
        feedback_type=args.get("feedback_type", "all"),
    ),
)

registry.register(
    name="feedback_resolve",
    toolset="crm",
    schema={
        "name": "feedback_resolve",
        "description": "Mark a feedback item resolved. Always document the resolution and root cause for bugs — this builds institutional memory.",
        "parameters": {
            "type": "object",
            "properties": {
                "client_name": {"type": "string", "description": "Client name"},
                "feedback_id": {"type": "string", "description": "8-character feedback ID from feedback_list"},
                "resolution": {"type": "string", "description": "What was done to resolve it, including root cause for bugs"},
            },
            "required": ["client_name", "feedback_id", "resolution"],
        },
    },
    handler=lambda args, **kw: feedback_resolve(
        client_name=args["client_name"],
        feedback_id=args["feedback_id"],
        resolution=args["resolution"],
    ),
)
