"""
PRD Tool — Product Requirement Document Generator

The PRD is the most important artifact in the SDLC.
It's also the one most people skip or produce in skeleton form.
A serious PRD takes time to write. It saves weeks of rework.

This tool generates full PRDs from discovery + SOW docs using local Ollama.
"""

import json
import os
import urllib.request
from datetime import datetime
from pathlib import Path

from tools.registry import registry


def _projects_dir(client: str) -> Path:
    safe = client.lower().replace(" ", "_").replace("/", "_")
    d = Path(os.path.expanduser(f"~/.hermes/projects/{safe}"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ollama(prompt: str, timeout: int = 120) -> str:
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


def prd_generate(client_name: str, additional_context: str = "") -> str:
    """
    Generate a full Product Requirement Document from discovery + SOW.

    Reads discovery.md and sow.md from the client's project folder.
    Uses Ollama to produce a complete PRD covering all 8 sections.

    The PRD is what gets handed to the build agent. Every decision
    the AI needs to make correctly must be specified here.
    """
    proj = _projects_dir(client_name)
    discovery = (proj / "discovery.md").read_text() if (proj / "discovery.md").exists() else ""
    sow = (proj / "sow.md").read_text() if (proj / "sow.md").exists() else ""

    if not discovery and not sow:
        return (
            f"No discovery or SOW found for '{client_name}'.\n"
            "Run discovery_run first, then scope_create, then prd_generate."
        )

    context = f"""Discovery Document:
{discovery[:800]}

Statement of Work:
{sow[:800]}

{('Additional context: ' + additional_context) if additional_context else ''}"""

    prompt = f"""You are a senior systems architect writing a Product Requirement Document.

{context}

Write a complete PRD with these sections:

## 1. User Flows
For each major feature: describe the step-by-step flow. Include what happens on:
- Happy path
- Empty state (no data yet)
- Loading state
- Error state (API down, invalid input, timeout)

## 2. Function Specifications
For each function/endpoint, specify precisely:
- Input parameters and types
- Processing logic (not vague — "score leads above 70 route to A-list" not "score leads")
- Output format
- Error handling

## 3. Integrations & APIs
For each external service:
- Specific endpoints used
- Authentication method
- Rate limits
- Fallback behavior if service is unavailable

## 4. Architecture
- Frontend layer (what runs in browser/client)
- Backend layer (what runs on server)
- Background layer (scheduled jobs, webhooks, queues)
- Data models and storage

## 5. Deployment
- Which component deploys where
- Environment variables required
- CI/CD approach

## 6. AI Guardrails
- What happens when the model returns unexpected output
- What gets logged
- What triggers human review
- Fallback behavior

## 7. Security & Compliance
- Authentication and authorization
- Data handling (PII, retention, encryption)
- OWASP considerations

## 8. Testing Plan
- Automated tests (unit, integration)
- Beta testing criteria (5 business days, real data)
- Security testing checklist

Be precise and specific. Vague PRDs produce systems that "work in demo but fail in production."
Write as if the build agent will read this and make every architectural decision from it alone."""

    prd_body = _ollama(prompt, timeout=120)
    if prd_body.startswith("Error"):
        return prd_body

    doc = f"# PRD: {client_name}\n\n"
    doc += f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
    doc += f"**Status:** Draft — review before build\n\n"
    doc += "---\n\n"
    doc += prd_body

    path = proj / "prd.md"
    path.write_text(doc)

    return (
        f"PRD generated for {client_name}.\n"
        f"Saved to: {path}\n\n"
        f"--- PREVIEW (first 600 chars) ---\n{prd_body[:600]}...\n\n"
        f"Review with prd_read('{client_name}') before starting the build."
    )


def prd_read(client_name: str) -> str:
    """Read the PRD for a client."""
    path = _projects_dir(client_name) / "prd.md"
    if not path.exists():
        return f"No PRD found for '{client_name}'. Run prd_generate first."
    return path.read_text()


registry.register(
    name="prd_generate",
    toolset="crm",
    schema={
        "name": "prd_generate",
        "description": "Generate a full Product Requirement Document from the client's discovery and SOW docs. Covers user flows, function specs, integrations, architecture, AI guardrails, security, and testing plan. Run after scope_create.",
        "parameters": {
            "type": "object",
            "properties": {
                "client_name": {"type": "string", "description": "Client name"},
                "additional_context": {"type": "string", "description": "Any additional context not captured in discovery/SOW (optional)"},
            },
            "required": ["client_name"],
        },
    },
    handler=lambda args, **kw: prd_generate(
        client_name=args["client_name"],
        additional_context=args.get("additional_context", ""),
    ),
)

registry.register(
    name="prd_read",
    toolset="crm",
    schema={
        "name": "prd_read",
        "description": "Read the Product Requirement Document for a client.",
        "parameters": {
            "type": "object",
            "properties": {
                "client_name": {"type": "string", "description": "Client name"},
            },
            "required": ["client_name"],
        },
    },
    handler=lambda args, **kw: prd_read(client_name=args["client_name"]),
)
