"""
Scoping Tool — Make Every Assumption Explicit, Every Boundary Visible

A proposal is not a feature list. It's a document that makes every assumption
explicit and every boundary visible. Scope creep happens because the proposal
was vague enough that both parties had different mental models.

This tool generates SOWs and guards scope on every subsequent request.
"""

import json
import os
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from tools.registry import registry


def _projects_dir(client: str) -> Path:
    safe = client.lower().replace(" ", "_").replace("/", "_")
    d = Path(os.path.expanduser(f"~/.hermes/projects/{safe}"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ollama(prompt: str, timeout: int = 90) -> str:
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


def scope_create(
    client_name: str,
    deliverables: str,
    out_of_scope: str,
    timeline_weeks: int = 6,
    price: str = "",
    sla_hours: int = 24,
) -> str:
    """
    Generate a Statement of Work (SOW) for a client engagement.
    Makes every in-scope deliverable precise and every out-of-scope item explicit.

    Args:
        client_name: Client or business name
        deliverables: Comma-separated list of specific deliverables
        out_of_scope: Comma-separated list of things explicitly NOT included
        timeline_weeks: Project duration in weeks (default: 6)
        price: Project price (optional, e.g. "$5,000" or "$299/mo")
        sla_hours: Response time for critical issues in hours (default: 24)
    """
    # Read discovery doc if exists for context
    discovery_path = _projects_dir(client_name) / "discovery.md"
    discovery_context = ""
    if discovery_path.exists():
        discovery_context = discovery_path.read_text()[:1000]

    start_date = datetime.now()
    milestones = []
    weeks_per_phase = max(1, timeline_weeks // 3)
    for i, phase in enumerate(["Phase 1: Core Infrastructure", "Phase 2: Integrations & Logic", "Phase 3: UI, Testing & Handoff"]):
        phase_end = start_date + timedelta(weeks=(i + 1) * weeks_per_phase)
        milestones.append(f"- {phase}: {phase_end.strftime('%Y-%m-%d')}")

    deliverable_list = [d.strip() for d in deliverables.split(",") if d.strip()]
    out_of_scope_list = [d.strip() for d in out_of_scope.split(",") if d.strip()]

    prompt = f"""Write a professional Statement of Work for a software project.

Client: {client_name}
{'Discovery context: ' + discovery_context if discovery_context else ''}

In-scope deliverables: {', '.join(deliverable_list)}
Explicitly out of scope: {', '.join(out_of_scope_list)}
Timeline: {timeline_weeks} weeks
{('Price: ' + price) if price else ''}
SLA: {sla_hours}h response for critical issues

Write the SOW with these sections:
## In Scope
(List each deliverable with precise technical description — not vague. E.g. not "AI chatbot" but "n8n workflow that pulls leads from Apollo, scores via local LLM, pushes qualified to Airtable with Slack notification")

## Explicitly Out of Scope
(List each with one sentence explaining why it's excluded)

## Milestone Timeline
(Use the dates provided)

## SLA & Support
(Response times, what counts as critical vs. non-critical)

## Compliance & Data
(Any data handling requirements, GDPR, IP ownership, what happens if a dependency changes)

## Change Request Process
(How out-of-scope requests are handled — priced and scoped separately)

Be extremely precise. Vague SOWs cause arguments. Write for a client who will hold you to every word."""

    sow_body = _ollama(prompt, timeout=90)
    if sow_body.startswith("Error"):
        return sow_body

    doc = f"# Statement of Work: {client_name}\n\n"
    doc += f"**Date:** {start_date.strftime('%Y-%m-%d')}\n"
    doc += f"**Timeline:** {timeline_weeks} weeks\n"
    if price:
        doc += f"**Price:** {price}\n"
    doc += "\n---\n\n"
    doc += sow_body

    path = _projects_dir(client_name) / "sow.md"
    path.write_text(doc)

    return (
        f"SOW created for {client_name}.\n"
        f"Saved to: {path}\n\n"
        f"--- PREVIEW ---\n{sow_body[:800]}...\n\n"
        f"Send to client for approval before starting any work."
    )


def scope_check(client_name: str, new_request: str) -> str:
    """
    Check whether a new client request is in scope, out of scope, or a bug.

    Returns one of:
      IN_SCOPE   — proceed, this is covered by the SOW
      OUT_OF_SCOPE — this is new work, needs pricing as a separate engagement
      BUG        — this is a defect in already-delivered work, fix within SLA

    Use this before acting on any client feedback or request.
    """
    sow_path = _projects_dir(client_name) / "sow.md"
    if not sow_path.exists():
        return f"No SOW found for '{client_name}'. Create one with scope_create first."

    sow = sow_path.read_text()[:2000]

    prompt = f"""You are a project manager reviewing a client request against a Statement of Work.

SOW (excerpt):
{sow}

New client request: "{new_request}"

Classify this request as exactly one of:
- IN_SCOPE: The request is covered by the SOW deliverables. Client can expect this without additional cost.
- OUT_OF_SCOPE: The request is NOT in the SOW. It's new work that needs a separate engagement and pricing.
- BUG: The request is reporting that something already delivered is broken or not working as specified.

Respond with:
CLASSIFICATION: [IN_SCOPE / OUT_OF_SCOPE / BUG]
REASON: [One sentence explaining why]
ACTION: [What to do next]"""

    result = _ollama(prompt, timeout=45)
    if result.startswith("Error"):
        return result

    return f"Scope check for '{client_name}':\nRequest: \"{new_request}\"\n\n{result}"


def scope_read(client_name: str) -> str:
    """Read the SOW for a client."""
    path = _projects_dir(client_name) / "sow.md"
    if not path.exists():
        return f"No SOW found for '{client_name}'. Run scope_create first."
    return path.read_text()


registry.register(
    name="scope_create",
    toolset="crm",
    schema={
        "name": "scope_create",
        "description": "Generate a Statement of Work (SOW) for a client. Makes every deliverable precise and every out-of-scope item explicit. Prevents scope creep. Run this after discovery_run and before any technical work begins.",
        "parameters": {
            "type": "object",
            "properties": {
                "client_name": {"type": "string", "description": "Client or business name"},
                "deliverables": {"type": "string", "description": "Comma-separated list of specific in-scope deliverables"},
                "out_of_scope": {"type": "string", "description": "Comma-separated list of things explicitly NOT included"},
                "timeline_weeks": {"type": "integer", "description": "Project duration in weeks (default: 6)", "default": 6},
                "price": {"type": "string", "description": "Project price (optional, e.g. '$5,000' or '$299/mo')"},
                "sla_hours": {"type": "integer", "description": "Response time for critical issues in hours (default: 24)", "default": 24},
            },
            "required": ["client_name", "deliverables", "out_of_scope"],
        },
    },
    handler=lambda args, **kw: scope_create(
        client_name=args["client_name"],
        deliverables=args["deliverables"],
        out_of_scope=args["out_of_scope"],
        timeline_weeks=args.get("timeline_weeks", 6),
        price=args.get("price", ""),
        sla_hours=args.get("sla_hours", 24),
    ),
)

registry.register(
    name="scope_check",
    toolset="crm",
    schema={
        "name": "scope_check",
        "description": "Check if a new client request is IN_SCOPE, OUT_OF_SCOPE, or a BUG. Run this before acting on any client feedback or feature request to prevent scope creep.",
        "parameters": {
            "type": "object",
            "properties": {
                "client_name": {"type": "string", "description": "Client name"},
                "new_request": {"type": "string", "description": "The client's new request or feedback"},
            },
            "required": ["client_name", "new_request"],
        },
    },
    handler=lambda args, **kw: scope_check(
        client_name=args["client_name"],
        new_request=args["new_request"],
    ),
)

registry.register(
    name="scope_read",
    toolset="crm",
    schema={
        "name": "scope_read",
        "description": "Read the Statement of Work for a client.",
        "parameters": {
            "type": "object",
            "properties": {
                "client_name": {"type": "string", "description": "Client name"},
            },
            "required": ["client_name"],
        },
    },
    handler=lambda args, **kw: scope_read(client_name=args["client_name"]),
)
