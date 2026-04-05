"""
Twilio SMS Tool — send SMS messages via Twilio.

Env vars required:
    TWILIO_ACCOUNT_SID   — Twilio Account SID
    TWILIO_AUTH_TOKEN    — Twilio Auth Token
    TWILIO_PHONE_NUMBER  — The agent's Twilio number in E.164 format
"""
import logging
import os
import re
from tools.registry import registry

logger = logging.getLogger(__name__)


def sms_send_tool(to: str, message: str) -> str:
    """Send an SMS via Twilio."""
    try:
        from twilio.rest import Client
    except ImportError:
        return "Error: twilio not installed. Run: pip install twilio"

    if not re.match(r"^\+[1-9]\d{1,14}$", to):
        return "Error: 'to' must be in E.164 format (e.g. +14155552671)"
    if not message.strip():
        return "Error: message cannot be empty"
    if len(message) > 1600:
        return "Error: message too long (max 1600 chars)"

    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_PHONE_NUMBER")

    if not all([sid, token, from_number]):
        return "Error: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER must be set in .env"

    try:
        client = Client(sid, token)
        msg = client.messages.create(body=message, from_=from_number, to=to)
        return f"SMS sent. SID: {msg.sid}. Status: {msg.status}"
    except Exception as e:
        logger.error("Twilio SMS error: %s", type(e).__name__)
        return f"Error sending SMS: {type(e).__name__}"


def _check_twilio():
    if not os.getenv("TWILIO_ACCOUNT_SID"):
        return False, "TWILIO_ACCOUNT_SID not set"
    if not os.getenv("TWILIO_AUTH_TOKEN"):
        return False, "TWILIO_AUTH_TOKEN not set"
    if not os.getenv("TWILIO_PHONE_NUMBER"):
        return False, "TWILIO_PHONE_NUMBER not set"
    return True, "Twilio configured"


registry.register(
    name="sms_send",
    toolset="messaging",
    schema={
        "name": "sms_send",
        "description": "Send an SMS message to a phone number via Twilio.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient phone number in E.164 format (e.g. +14155552671)"},
                "message": {"type": "string", "description": "SMS message body (max 1600 chars)"},
            },
            "required": ["to", "message"],
        },
    },
    handler=lambda args, **kw: sms_send_tool(args["to"], args["message"]),
    check_fn=_check_twilio,
    requires_env=["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER"],
    emoji="💬",
)


# ---------------------------------------------------------------------------
# WhatsApp — uses same Twilio credentials + a WhatsApp-enabled number
# Env: TWILIO_WHATSAPP_NUMBER (e.g. whatsapp:+14155552671) or falls back to
#      TWILIO_PHONE_NUMBER with whatsapp: prefix
# ---------------------------------------------------------------------------

def whatsapp_send_tool(to: str, message: str) -> str:
    """Send a WhatsApp message via Twilio WhatsApp Business API."""
    try:
        from twilio.rest import Client
    except ImportError:
        return "Error: twilio not installed. Run: pip install twilio"

    if not re.match(r"^\+[1-9]\d{1,14}$", to):
        return "Error: 'to' must be in E.164 format (e.g. +14155552671)"
    if not message.strip():
        return "Error: message cannot be empty"
    if len(message) > 1600:
        return "Error: message too long (max 1600 chars)"

    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_WHATSAPP_NUMBER") or f"whatsapp:{os.getenv('TWILIO_PHONE_NUMBER', '')}"

    if not all([sid, token]) or not from_number.startswith("whatsapp:"):
        return (
            "Error: Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and "
            "TWILIO_WHATSAPP_NUMBER (whatsapp:+1XXXXXXXXXX format)"
        )

    try:
        client = Client(sid, token)
        msg = client.messages.create(
            body=message,
            from_=from_number,
            to=f"whatsapp:{to}",
        )
        return f"WhatsApp message sent. SID: {msg.sid}. Status: {msg.status}"
    except Exception as e:
        logger.error("Twilio WhatsApp error: %s", type(e).__name__)
        return f"Error sending WhatsApp: {type(e).__name__}"


def _check_whatsapp():
    if not os.getenv("TWILIO_ACCOUNT_SID"):
        return False, "TWILIO_ACCOUNT_SID not set"
    if not os.getenv("TWILIO_AUTH_TOKEN"):
        return False, "TWILIO_AUTH_TOKEN not set"
    wa_num = os.getenv("TWILIO_WHATSAPP_NUMBER") or os.getenv("TWILIO_PHONE_NUMBER", "")
    if not wa_num:
        return False, "TWILIO_WHATSAPP_NUMBER not set"
    return True, "WhatsApp configured"


registry.register(
    name="whatsapp_send",
    toolset="messaging",
    schema={
        "name": "whatsapp_send",
        "description": "Send a WhatsApp message to a phone number via Twilio WhatsApp Business API.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient phone number in E.164 format (e.g. +14155552671)"},
                "message": {"type": "string", "description": "WhatsApp message body"},
            },
            "required": ["to", "message"],
        },
    },
    handler=lambda args, **kw: whatsapp_send_tool(args["to"], args["message"]),
    check_fn=_check_whatsapp,
    requires_env=["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"],
    emoji="💚",
)
