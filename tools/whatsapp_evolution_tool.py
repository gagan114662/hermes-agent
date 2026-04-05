"""
Evolution API WhatsApp Tool — send/receive WhatsApp messages via self-hosted Evolution API.
No Twilio required. Runs on your own server. Connects via WhatsApp Web QR scan.

Self-hosting: docker run -d -p 8080:8080 atendai/evolution-api:latest
Docs: https://doc.evolution-api.com

Env vars required:
    EVOLUTION_API_URL      — Your Evolution API base URL (e.g. http://localhost:8080)
    EVOLUTION_API_KEY      — API key set in Evolution API config (self-generated)
    EVOLUTION_INSTANCE     — WhatsApp instance name (e.g. "business" — created once via QR scan)
"""
import logging
import os
import httpx
from tools.registry import registry

logger = logging.getLogger(__name__)


def _base() -> str:
    return os.environ.get("EVOLUTION_API_URL", "").rstrip("/")


def _headers():
    return {
        "apikey": os.environ.get("EVOLUTION_API_KEY", ""),
        "Content-Type": "application/json",
    }


def _instance() -> str:
    return os.environ.get("EVOLUTION_INSTANCE", "default")


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------

def wa_send_text(to: str, message: str) -> str:
    """
    Send a WhatsApp text message.
    to: phone number in international format without + (e.g. 14155552671) or JID (e.g. 14155552671@s.whatsapp.net)
    """
    base = _base()
    if not base:
        return "Error: EVOLUTION_API_URL not set"
    # Normalise number
    to = to.lstrip("+").replace(" ", "").replace("-", "")
    if not to.endswith("@s.whatsapp.net") and not to.endswith("@g.us"):
        to = f"{to}@s.whatsapp.net"
    try:
        resp = httpx.post(
            f"{base}/message/sendText/{_instance()}",
            headers=_headers(),
            json={"number": to, "text": message},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        msg_id = data.get("key", {}).get("id", data.get("messageId", ""))
        return f"WhatsApp message sent. ID: {msg_id}"
    except httpx.HTTPStatusError as e:
        return f"Error sending WhatsApp: HTTP {e.response.status_code} — {e.response.text[:200]}"
    except Exception as e:
        logger.error("wa_send_text error: %s", e)
        return f"Error: {e}"


def wa_send_media(to: str, media_url: str, caption: str = "", media_type: str = "image") -> str:
    """
    Send a WhatsApp media message (image, video, document, audio).
    media_type: image | video | document | audio
    """
    base = _base()
    if not base:
        return "Error: EVOLUTION_API_URL not set"
    to = to.lstrip("+").replace(" ", "").replace("-", "")
    if not to.endswith("@s.whatsapp.net") and not to.endswith("@g.us"):
        to = f"{to}@s.whatsapp.net"
    endpoint_map = {
        "image": "sendMedia",
        "video": "sendMedia",
        "document": "sendMedia",
        "audio": "sendWhatsAppAudio",
    }
    endpoint = endpoint_map.get(media_type, "sendMedia")
    payload = {
        "number": to,
        "mediatype": media_type,
        "mimetype": f"{media_type}/{'jpeg' if media_type == 'image' else 'mp4'}",
        "caption": caption,
        "media": media_url,
    }
    try:
        resp = httpx.post(
            f"{base}/message/{endpoint}/{_instance()}",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return f"WhatsApp {media_type} sent to {to}."
    except httpx.HTTPStatusError as e:
        return f"Error sending media: HTTP {e.response.status_code} — {e.response.text[:200]}"
    except Exception as e:
        return f"Error: {e}"


def wa_send_button(to: str, message: str, buttons: list) -> str:
    """
    Send a WhatsApp message with reply buttons.
    buttons: list of strings (button labels), max 3.
    """
    base = _base()
    if not base:
        return "Error: EVOLUTION_API_URL not set"
    to = to.lstrip("+").replace(" ", "").replace("-", "")
    if not to.endswith("@s.whatsapp.net") and not to.endswith("@g.us"):
        to = f"{to}@s.whatsapp.net"
    button_list = [{"buttonId": str(i), "buttonText": {"displayText": b}, "type": 1} for i, b in enumerate(buttons[:3])]
    try:
        resp = httpx.post(
            f"{base}/message/sendButtons/{_instance()}",
            headers=_headers(),
            json={
                "number": to,
                "title": "",
                "description": message,
                "footer": "",
                "buttons": button_list,
            },
            timeout=20,
        )
        resp.raise_for_status()
        return f"WhatsApp button message sent to {to}."
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code} — {e.response.text[:200]}"
    except Exception as e:
        return f"Error: {e}"


def wa_get_messages(contact_number: str, limit: int = 20) -> str:
    """Retrieve recent WhatsApp messages from a contact."""
    base = _base()
    if not base:
        return "Error: EVOLUTION_API_URL not set"
    contact_number = contact_number.lstrip("+").replace(" ", "").replace("-", "")
    try:
        resp = httpx.post(
            f"{base}/chat/findMessages/{_instance()}",
            headers=_headers(),
            json={"where": {"key": {"remoteJid": f"{contact_number}@s.whatsapp.net"}}, "limit": limit},
            timeout=15,
        )
        resp.raise_for_status()
        messages = resp.json()
        if not messages:
            return f"No messages found with {contact_number}."
        lines = [f"Recent messages with {contact_number}:"]
        for m in (messages if isinstance(messages, list) else [messages])[:limit]:
            msg_obj = m.get("message", {})
            text = (
                msg_obj.get("conversation")
                or msg_obj.get("extendedTextMessage", {}).get("text", "")
                or "[media]"
            )
            from_me = m.get("key", {}).get("fromMe", False)
            sender = "You" if from_me else contact_number
            lines.append(f"  [{sender}]: {text[:120]}")
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        return f"Error fetching messages: HTTP {e.response.status_code}"
    except Exception as e:
        return f"Error: {e}"


def wa_get_chats(limit: int = 20) -> str:
    """List recent WhatsApp chats/contacts."""
    base = _base()
    if not base:
        return "Error: EVOLUTION_API_URL not set"
    try:
        resp = httpx.post(
            f"{base}/chat/findChats/{_instance()}",
            headers=_headers(),
            json={},
            timeout=15,
        )
        resp.raise_for_status()
        chats = resp.json()
        if not chats:
            return "No chats found."
        lines = ["Recent WhatsApp chats:"]
        for c in (chats if isinstance(chats, list) else [])[:limit]:
            jid = c.get("id", "")
            name = c.get("name") or c.get("pushName") or jid
            unread = c.get("unreadCount", 0)
            unread_str = f" ({unread} unread)" if unread else ""
            lines.append(f"  • {name} [{jid}]{unread_str}")
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code}"
    except Exception as e:
        return f"Error: {e}"


def wa_instance_status() -> str:
    """Check if the WhatsApp instance is connected."""
    base = _base()
    if not base:
        return "Error: EVOLUTION_API_URL not set"
    try:
        resp = httpx.get(
            f"{base}/instance/connectionState/{_instance()}",
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        state = data.get("instance", {}).get("state", data.get("state", "unknown"))
        return f"WhatsApp instance '{_instance()}' state: {state}"
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code}"
    except Exception as e:
        return f"Error: {e}"


def wa_get_qr() -> str:
    """Get the QR code URL/base64 to connect a new WhatsApp instance."""
    base = _base()
    if not base:
        return "Error: EVOLUTION_API_URL not set"
    try:
        resp = httpx.get(
            f"{base}/instance/connect/{_instance()}",
            headers=_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        qr = data.get("qrcode", {})
        if isinstance(qr, dict):
            pairingCode = qr.get("pairingCode", "")
            if pairingCode:
                return f"WhatsApp pairing code: {pairingCode}\nOpen WhatsApp → Linked Devices → Link with phone number"
            base64 = qr.get("base64", "")
            if base64:
                return f"QR code (base64 PNG): open in browser to scan\ndata:image/png;base64,{base64[:100]}..."
        return f"QR response: {str(data)[:300]}"
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code} — {e.response.text[:200]}"
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _check_evolution():
    if not os.environ.get("EVOLUTION_API_URL"):
        return False, "EVOLUTION_API_URL not set"
    if not os.environ.get("EVOLUTION_API_KEY"):
        return False, "EVOLUTION_API_KEY not set"
    return True, "Evolution API (WhatsApp) configured"


_EVOLUTION_ENVS = ["EVOLUTION_API_URL", "EVOLUTION_API_KEY", "EVOLUTION_INSTANCE"]

registry.register(
    name="wa_send_text",
    toolset="whatsapp",
    schema={
        "name": "wa_send_text",
        "description": "Send a WhatsApp text message to a phone number (no Twilio required — uses self-hosted Evolution API).",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient phone in international format without + (e.g. 14155552671)"},
                "message": {"type": "string", "description": "Message text to send"},
            },
            "required": ["to", "message"],
        },
    },
    handler=lambda args, **kw: wa_send_text(args["to"], args["message"]),
    check_fn=_check_evolution,
    requires_env=["EVOLUTION_API_URL", "EVOLUTION_API_KEY"],
    emoji="💚",
)

registry.register(
    name="wa_send_media",
    toolset="whatsapp",
    schema={
        "name": "wa_send_media",
        "description": "Send a WhatsApp image, video, document, or audio file.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient phone number"},
                "media_url": {"type": "string", "description": "Publicly accessible URL of the media file"},
                "caption": {"type": "string", "description": "Optional caption"},
                "media_type": {"type": "string", "description": "image | video | document | audio"},
            },
            "required": ["to", "media_url"],
        },
    },
    handler=lambda args, **kw: wa_send_media(
        args["to"], args["media_url"], args.get("caption", ""), args.get("media_type", "image")
    ),
    check_fn=_check_evolution,
    requires_env=["EVOLUTION_API_URL", "EVOLUTION_API_KEY"],
    emoji="💚",
)

registry.register(
    name="wa_send_button",
    toolset="whatsapp",
    schema={
        "name": "wa_send_button",
        "description": "Send a WhatsApp message with up to 3 reply buttons.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient phone number"},
                "message": {"type": "string", "description": "Message body"},
                "buttons": {"type": "array", "items": {"type": "string"}, "description": "List of button labels (max 3)"},
            },
            "required": ["to", "message", "buttons"],
        },
    },
    handler=lambda args, **kw: wa_send_button(args["to"], args["message"], args["buttons"]),
    check_fn=_check_evolution,
    requires_env=["EVOLUTION_API_URL", "EVOLUTION_API_KEY"],
    emoji="💚",
)

registry.register(
    name="wa_get_messages",
    toolset="whatsapp",
    schema={
        "name": "wa_get_messages",
        "description": "Retrieve recent WhatsApp messages from a contact.",
        "parameters": {
            "type": "object",
            "properties": {
                "contact_number": {"type": "string", "description": "Contact phone number"},
                "limit": {"type": "integer", "description": "Max messages to return (default 20)"},
            },
            "required": ["contact_number"],
        },
    },
    handler=lambda args, **kw: wa_get_messages(args["contact_number"], args.get("limit", 20)),
    check_fn=_check_evolution,
    requires_env=["EVOLUTION_API_URL", "EVOLUTION_API_KEY"],
    emoji="💚",
)

registry.register(
    name="wa_get_chats",
    toolset="whatsapp",
    schema={
        "name": "wa_get_chats",
        "description": "List recent WhatsApp conversations.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max chats to return (default 20)"},
            },
            "required": [],
        },
    },
    handler=lambda args, **kw: wa_get_chats(args.get("limit", 20)),
    check_fn=_check_evolution,
    requires_env=["EVOLUTION_API_URL", "EVOLUTION_API_KEY"],
    emoji="💚",
)

registry.register(
    name="wa_instance_status",
    toolset="whatsapp",
    schema={
        "name": "wa_instance_status",
        "description": "Check if the WhatsApp instance is connected and ready.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    handler=lambda args, **kw: wa_instance_status(),
    check_fn=_check_evolution,
    requires_env=["EVOLUTION_API_URL", "EVOLUTION_API_KEY"],
    emoji="💚",
)

registry.register(
    name="wa_get_qr",
    toolset="whatsapp",
    schema={
        "name": "wa_get_qr",
        "description": "Get the QR code or pairing code to connect a new WhatsApp instance.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    handler=lambda args, **kw: wa_get_qr(),
    check_fn=_check_evolution,
    requires_env=["EVOLUTION_API_URL", "EVOLUTION_API_KEY"],
    emoji="💚",
)
