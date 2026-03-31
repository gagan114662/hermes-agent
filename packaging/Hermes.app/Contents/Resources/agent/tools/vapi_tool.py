"""
Vapi Voice Tool — make outbound calls and list recent calls via Vapi.ai.

Env vars required:
    VAPI_API_KEY      — Vapi private key
    VAPI_PHONE_ID     — Vapi phone number ID for this agent
    VAPI_ASSISTANT_ID — Vapi assistant ID configured for this agent
"""
import logging
import os
import httpx
from tools.registry import registry

logger = logging.getLogger(__name__)

VAPI_BASE = "https://api.vapi.ai"


def _headers():
    return {
        "Authorization": f"Bearer {os.environ['VAPI_API_KEY']}",
        "Content-Type": "application/json",
    }


def vapi_outbound_call_tool(phone_number: str, task: str) -> str:
    """Make an outbound call via Vapi to a phone number with a given task/script."""
    import re
    if not re.match(r"^\+[1-9]\d{1,14}$", phone_number):
        return "Error: phone_number must be in E.164 format (e.g. +14155552671)"
    payload = {
        "phoneNumberId": os.environ["VAPI_PHONE_ID"],
        "assistantId": os.environ["VAPI_ASSISTANT_ID"],
        "customer": {"number": phone_number},
        "assistantOverrides": {
            "firstMessage": task,
        },
    }
    try:
        resp = httpx.post(
            f"{VAPI_BASE}/call/phone",
            headers=_headers(),
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return f"Call initiated. Call ID: {data.get('id')}. Status: {data.get('status')}"
    except httpx.HTTPStatusError as e:
        logger.error("Vapi call error: %s %s", e.response.status_code, e.response.text)
        return f"Error making call: HTTP {e.response.status_code}"
    except httpx.TimeoutException:
        return "Error: Vapi request timed out"
    except httpx.ConnectError:
        return "Error: Could not connect to Vapi API"
    except Exception as e:
        logger.error("Vapi unexpected error: %s", e)
        return "Error: unexpected error making call"


def vapi_list_calls_tool(limit: int = 10) -> str:
    """List recent calls handled by this agent."""
    try:
        resp = httpx.get(
            f"{VAPI_BASE}/call",
            headers=_headers(),
            params={"limit": limit},
            timeout=15,
        )
        resp.raise_for_status()
        calls = resp.json()
        if not calls:
            return "No calls found."
        lines = ["Recent calls:\n"]
        for c in calls[:limit]:
            cid = c.get("id", "")[:8]
            status = c.get("status", "")
            duration = c.get("duration", 0)
            customer = c.get("customer", {}).get("number", "unknown")
            ended = c.get("endedReason", "")
            lines.append(f"- {cid} | {customer} | {status} | {duration}s | {ended}")
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        logger.error("Vapi list calls error: %s", e.response.status_code)
        return f"Error listing calls: HTTP {e.response.status_code}"
    except httpx.TimeoutException:
        return "Error: Vapi request timed out"
    except httpx.ConnectError:
        return "Error: Could not connect to Vapi API"
    except Exception as e:
        logger.error("Vapi unexpected error: %s", e)
        return "Error: unexpected error listing calls"


def _check_vapi():
    if not os.getenv("VAPI_API_KEY"):
        return False, "VAPI_API_KEY not set"
    if not os.getenv("VAPI_PHONE_ID"):
        return False, "VAPI_PHONE_ID not set"
    if not os.getenv("VAPI_ASSISTANT_ID"):
        return False, "VAPI_ASSISTANT_ID not set"
    return True, "Vapi configured"


registry.register(
    name="vapi_call",
    toolset="voice",
    schema={
        "name": "vapi_call",
        "description": "Make an outbound phone call to a customer using Vapi AI voice. Provide the phone number and what the call should accomplish.",
        "parameters": {
            "type": "object",
            "properties": {
                "phone_number": {"type": "string", "description": "Phone number to call in E.164 format (e.g. +14155552671)"},
                "task": {"type": "string", "description": "What the AI should say/accomplish on this call"},
            },
            "required": ["phone_number", "task"],
        },
    },
    handler=lambda args, **kw: vapi_outbound_call_tool(args["phone_number"], args["task"]),
    check_fn=_check_vapi,
    requires_env=["VAPI_API_KEY", "VAPI_PHONE_ID"],
    emoji="📞",
)

registry.register(
    name="vapi_calls",
    toolset="voice",
    schema={
        "name": "vapi_calls",
        "description": "List recent phone calls handled by this AI agent.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of calls to return (default 10)", "default": 10},
            },
            "required": [],
        },
    },
    handler=lambda args, **kw: vapi_list_calls_tool(args.get("limit", 10)),
    check_fn=_check_vapi,
    requires_env=["VAPI_API_KEY"],
    emoji="📋",
)
