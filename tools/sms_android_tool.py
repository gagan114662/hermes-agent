"""
Android SMS Gateway Tool — send SMS using an Android phone as the modem.
Zero cost. No Twilio. Just an Android phone running the SMS Gateway app.

Self-hosting: https://github.com/capcom6/android-sms-gateway
Install app on Android → get IP → configure ANDROID_SMS_GATEWAY_URL

Env vars required:
    ANDROID_SMS_GATEWAY_URL      — Gateway URL (e.g. http://192.168.1.100:8080)
    ANDROID_SMS_GATEWAY_USER     — Username (default: user)
    ANDROID_SMS_GATEWAY_PASSWORD — Password (set in app)
"""
import logging
import os
import httpx
from tools.registry import registry

logger = logging.getLogger(__name__)


def _base() -> str:
    return os.environ.get("ANDROID_SMS_GATEWAY_URL", "").rstrip("/")


def _auth():
    return (
        os.environ.get("ANDROID_SMS_GATEWAY_USER", "user"),
        os.environ.get("ANDROID_SMS_GATEWAY_PASSWORD", ""),
    )


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------

def android_sms_send(to: str, message: str, sim_number: int = 1) -> str:
    """
    Send an SMS via Android SMS Gateway.
    to: recipient phone in E.164 format (e.g. +14155552671)
    sim_number: SIM slot to use (1 or 2 for dual-SIM phones)
    """
    base = _base()
    if not base:
        return "Error: ANDROID_SMS_GATEWAY_URL not set"
    if not message.strip():
        return "Error: message cannot be empty"

    payload = {
        "message": message,
        "phoneNumbers": [to],
        "simNumber": sim_number,
    }
    try:
        resp = httpx.post(
            f"{base}/api/v1/message",
            auth=_auth(),
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        msg_id = data.get("id", "")
        state = data.get("state", "")
        return f"SMS sent via Android gateway. ID: {msg_id}, State: {state}"
    except httpx.HTTPStatusError as e:
        return f"Error sending SMS: HTTP {e.response.status_code} — {e.response.text[:200]}"
    except Exception as e:
        logger.error("android_sms_send error: %s", e)
        return f"Error: {e}"


def android_sms_send_bulk(numbers: list, message: str) -> str:
    """Send the same SMS to multiple numbers via Android SMS Gateway."""
    base = _base()
    if not base:
        return "Error: ANDROID_SMS_GATEWAY_URL not set"
    if not numbers:
        return "Error: numbers list is empty"
    if not message.strip():
        return "Error: message cannot be empty"

    payload = {"message": message, "phoneNumbers": numbers}
    try:
        resp = httpx.post(
            f"{base}/api/v1/message",
            auth=_auth(),
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        msg_id = data.get("id", "")
        return f"Bulk SMS sent to {len(numbers)} numbers. ID: {msg_id}"
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code} — {e.response.text[:200]}"
    except Exception as e:
        return f"Error: {e}"


def android_sms_status(message_id: str) -> str:
    """Check the delivery status of a sent SMS."""
    base = _base()
    if not base:
        return "Error: ANDROID_SMS_GATEWAY_URL not set"
    try:
        resp = httpx.get(
            f"{base}/api/v1/message/{message_id}",
            auth=_auth(),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        state = data.get("state", "unknown")
        recipients = data.get("recipients", [])
        lines = [f"SMS {message_id}: {state}"]
        for r in recipients:
            lines.append(f"  • {r.get('phoneNumber', '')} → {r.get('state', '')}")
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code}"
    except Exception as e:
        return f"Error: {e}"


def android_sms_health() -> str:
    """Check if the Android SMS Gateway is reachable and the phone is connected."""
    base = _base()
    if not base:
        return "Error: ANDROID_SMS_GATEWAY_URL not set"
    try:
        resp = httpx.get(
            f"{base}/api/v1/health",
            auth=_auth(),
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        return f"Android SMS Gateway: {data.get('status', 'ok')} — {base}"
    except httpx.ConnectError:
        return f"Error: Cannot reach Android gateway at {base}. Check phone IP/WiFi."
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code}"
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _check_android_sms():
    if not os.environ.get("ANDROID_SMS_GATEWAY_URL"):
        return False, "ANDROID_SMS_GATEWAY_URL not set"
    if not os.environ.get("ANDROID_SMS_GATEWAY_PASSWORD"):
        return False, "ANDROID_SMS_GATEWAY_PASSWORD not set"
    return True, "Android SMS Gateway configured"


_ANDROID_ENVS = ["ANDROID_SMS_GATEWAY_URL", "ANDROID_SMS_GATEWAY_PASSWORD"]

registry.register(
    name="android_sms_send",
    toolset="sms-android",
    schema={
        "name": "android_sms_send",
        "description": "Send an SMS via an Android phone acting as SMS gateway. Zero cost — no Twilio needed.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient phone in E.164 format (e.g. +14155552671)"},
                "message": {"type": "string", "description": "SMS message text"},
                "sim_number": {"type": "integer", "description": "SIM slot to use: 1 or 2 (default 1)"},
            },
            "required": ["to", "message"],
        },
    },
    handler=lambda args, **kw: android_sms_send(
        args["to"], args["message"], args.get("sim_number", 1)
    ),
    check_fn=_check_android_sms,
    requires_env=_ANDROID_ENVS,
    emoji="📱",
)

registry.register(
    name="android_sms_send_bulk",
    toolset="sms-android",
    schema={
        "name": "android_sms_send_bulk",
        "description": "Send the same SMS to multiple phone numbers at once.",
        "parameters": {
            "type": "object",
            "properties": {
                "numbers": {"type": "array", "items": {"type": "string"}, "description": "List of E.164 phone numbers"},
                "message": {"type": "string", "description": "SMS message text"},
            },
            "required": ["numbers", "message"],
        },
    },
    handler=lambda args, **kw: android_sms_send_bulk(args["numbers"], args["message"]),
    check_fn=_check_android_sms,
    requires_env=_ANDROID_ENVS,
    emoji="📱",
)

registry.register(
    name="android_sms_status",
    toolset="sms-android",
    schema={
        "name": "android_sms_status",
        "description": "Check delivery status of a sent SMS.",
        "parameters": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "SMS message ID returned by android_sms_send"},
            },
            "required": ["message_id"],
        },
    },
    handler=lambda args, **kw: android_sms_status(args["message_id"]),
    check_fn=_check_android_sms,
    requires_env=_ANDROID_ENVS,
    emoji="📱",
)

registry.register(
    name="android_sms_health",
    toolset="sms-android",
    schema={
        "name": "android_sms_health",
        "description": "Check if the Android SMS Gateway is online and the phone is connected.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    handler=lambda args, **kw: android_sms_health(),
    check_fn=_check_android_sms,
    requires_env=_ANDROID_ENVS,
    emoji="📱",
)
