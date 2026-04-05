"""
Fonoster Voice Tool — make/receive calls and manage phone numbers via self-hosted Fonoster.
Open source Vapi/Twilio alternative. No per-minute fees.

Self-hosting: https://github.com/fonoster/fonoster (Docker Compose)
Docs: https://fonoster.com/docs

Env vars required:
    FONOSTER_ACCESS_KEY_ID     — From Fonoster dashboard (Project → API Keys)
    FONOSTER_ACCESS_KEY_SECRET — From Fonoster dashboard
    FONOSTER_APP_REF           — Voice application reference (handles call logic)

Optional:
    FONOSTER_API_URL           — Override for self-hosted (default: api.fonoster.io:50051)
"""
import logging
import os
import httpx
from tools.registry import registry

logger = logging.getLogger(__name__)

# Fonoster exposes a REST gateway alongside gRPC.
# We use the REST gateway (port 8080 on self-hosted, or api.fonoster.io/rest).
FONOSTER_REST_URL = os.getenv("FONOSTER_API_URL", "https://api.fonoster.io")


def _rest_base() -> str:
    return os.environ.get("FONOSTER_API_URL", FONOSTER_REST_URL).rstrip("/")


def _auth():
    """HTTP Basic auth using access key ID + secret."""
    return (
        os.environ.get("FONOSTER_ACCESS_KEY_ID", ""),
        os.environ.get("FONOSTER_ACCESS_KEY_SECRET", ""),
    )


def _app_ref() -> str:
    return os.environ.get("FONOSTER_APP_REF", "")


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------

def fonoster_call_make(to: str, from_number: str = "", task: str = "") -> str:
    """
    Initiate an outbound voice call via Fonoster.
    to: destination phone in E.164 format (e.g. +14155552671)
    from_number: caller ID (E.164). Uses FONOSTER_FROM_NUMBER env if omitted.
    task: optional instruction injected as metadata for the voice app.
    """
    base = _rest_base()
    from_number = from_number or os.environ.get("FONOSTER_FROM_NUMBER", "")
    app_ref = _app_ref()
    if not app_ref:
        return "Error: FONOSTER_APP_REF not set — create a voice application in Fonoster first"
    if not from_number:
        return "Error: from_number required or set FONOSTER_FROM_NUMBER"

    payload = {
        "from": from_number,
        "to": to,
        "appRef": app_ref,
    }
    if task:
        payload["metadata"] = {"task": task}

    try:
        resp = httpx.post(
            f"{base}/api/v1beta2/calls",
            auth=_auth(),
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        call_ref = data.get("ref", data.get("callId", ""))
        return f"Call initiated to {to}. Call ref: {call_ref}"
    except httpx.HTTPStatusError as e:
        return f"Error making call: HTTP {e.response.status_code} — {e.response.text[:300]}"
    except Exception as e:
        logger.error("fonoster_call_make error: %s", e)
        return f"Error: {e}"


def fonoster_call_list(limit: int = 10) -> str:
    """List recent calls from Fonoster call history."""
    base = _rest_base()
    try:
        resp = httpx.get(
            f"{base}/api/v1beta2/calls",
            auth=_auth(),
            params={"pageSize": limit},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        calls = data.get("items", data.get("calls", []))
        if not calls:
            return "No recent calls."
        lines = ["Recent calls:"]
        for c in calls[:limit]:
            direction = c.get("direction", "")
            status = c.get("status", "")
            from_ = c.get("from", "")
            to_ = c.get("to", "")
            duration = c.get("duration", 0)
            lines.append(f"  • {direction} {from_} → {to_} | {status} | {duration}s")
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code}"
    except Exception as e:
        return f"Error: {e}"


def fonoster_number_list() -> str:
    """List phone numbers registered in Fonoster."""
    base = _rest_base()
    try:
        resp = httpx.get(
            f"{base}/api/v1beta2/numbers",
            auth=_auth(),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        numbers = data.get("items", data.get("numbers", []))
        if not numbers:
            return "No numbers found in Fonoster."
        lines = ["Fonoster numbers:"]
        for n in numbers:
            num = n.get("e164Number", n.get("number", ""))
            name = n.get("name", "")
            lines.append(f"  • {num} — {name}")
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code}"
    except Exception as e:
        return f"Error: {e}"


def fonoster_app_list() -> str:
    """List voice applications in Fonoster."""
    base = _rest_base()
    try:
        resp = httpx.get(
            f"{base}/api/v1beta2/applications",
            auth=_auth(),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        apps = data.get("items", data.get("applications", []))
        if not apps:
            return "No voice applications found."
        lines = ["Voice applications:"]
        for a in apps:
            ref = a.get("ref", "")
            name = a.get("name", "")
            endpoint = a.get("endpoint", "")
            lines.append(f"  • {name} (ref: {ref}) → {endpoint}")
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code}"
    except Exception as e:
        return f"Error: {e}"


def fonoster_agent_create(name: str, username: str, secret: str = "") -> str:
    """
    Create a SIP agent (extension) in Fonoster for an AI voice employee.
    Returns the agent reference.
    """
    base = _rest_base()
    import secrets as _secrets
    if not secret:
        secret = _secrets.token_urlsafe(12)
    try:
        resp = httpx.post(
            f"{base}/api/v1beta2/agents",
            auth=_auth(),
            json={"name": name, "username": username, "secret": secret},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        ref = data.get("ref", "")
        return f"Agent '{name}' created. Username: {username}, Secret: {secret}, Ref: {ref}"
    except httpx.HTTPStatusError as e:
        return f"Error creating agent: HTTP {e.response.status_code} — {e.response.text[:200]}"
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _check_fonoster():
    if not os.environ.get("FONOSTER_ACCESS_KEY_ID"):
        return False, "FONOSTER_ACCESS_KEY_ID not set"
    if not os.environ.get("FONOSTER_ACCESS_KEY_SECRET"):
        return False, "FONOSTER_ACCESS_KEY_SECRET not set"
    return True, "Fonoster voice configured"


_FONOSTER_ENVS = ["FONOSTER_ACCESS_KEY_ID", "FONOSTER_ACCESS_KEY_SECRET"]

registry.register(
    name="fonoster_call_make",
    toolset="voice",
    schema={
        "name": "fonoster_call_make",
        "description": "Make an outbound phone call via Fonoster (self-hosted open source voice platform — no Vapi/Twilio needed).",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Destination phone number in E.164 format (e.g. +14155552671)"},
                "from_number": {"type": "string", "description": "Caller ID in E.164 format. Uses FONOSTER_FROM_NUMBER if omitted."},
                "task": {"type": "string", "description": "Task or script instruction for the AI voice agent handling the call"},
            },
            "required": ["to"],
        },
    },
    handler=lambda args, **kw: fonoster_call_make(
        args["to"], args.get("from_number", ""), args.get("task", "")
    ),
    check_fn=_check_fonoster,
    requires_env=_FONOSTER_ENVS,
    emoji="📞",
)

registry.register(
    name="fonoster_call_list",
    toolset="voice",
    schema={
        "name": "fonoster_call_list",
        "description": "List recent inbound and outbound calls from Fonoster.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max calls to return (default 10)"},
            },
            "required": [],
        },
    },
    handler=lambda args, **kw: fonoster_call_list(args.get("limit", 10)),
    check_fn=_check_fonoster,
    requires_env=_FONOSTER_ENVS,
    emoji="📞",
)

registry.register(
    name="fonoster_number_list",
    toolset="voice",
    schema={
        "name": "fonoster_number_list",
        "description": "List phone numbers registered in Fonoster.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    handler=lambda args, **kw: fonoster_number_list(),
    check_fn=_check_fonoster,
    requires_env=_FONOSTER_ENVS,
    emoji="📞",
)

registry.register(
    name="fonoster_app_list",
    toolset="voice",
    schema={
        "name": "fonoster_app_list",
        "description": "List voice applications configured in Fonoster.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    handler=lambda args, **kw: fonoster_app_list(),
    check_fn=_check_fonoster,
    requires_env=_FONOSTER_ENVS,
    emoji="📞",
)

registry.register(
    name="fonoster_agent_create",
    toolset="voice",
    schema={
        "name": "fonoster_agent_create",
        "description": "Create a SIP agent/extension in Fonoster for an AI voice employee.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Display name for the agent"},
                "username": {"type": "string", "description": "SIP username (e.g. alex-sales)"},
                "secret": {"type": "string", "description": "SIP password (auto-generated if omitted)"},
            },
            "required": ["name", "username"],
        },
    },
    handler=lambda args, **kw: fonoster_agent_create(
        args["name"], args["username"], args.get("secret", "")
    ),
    check_fn=_check_fonoster,
    requires_env=_FONOSTER_ENVS,
    emoji="📞",
)
