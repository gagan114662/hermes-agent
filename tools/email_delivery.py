"""Shared email delivery module — Resend API with SMTP fallback.

Provides a single send_email() function used by:
- gateway/platforms/email.py (gateway replies)
- scripts/growth_engine.py (outbound sales)
- tools/send_message_tool.py (agent send_message tool)

Priority: Resend API (better deliverability) → SMTP fallback.

Environment variables:
    RESEND_API_KEY      — Resend API key (get one free at resend.com/api-keys)
    EMAIL_FROM_ADDRESS  — Verified sender (e.g., hermes@yourdomain.com)
    EMAIL_SMTP_HOST     — Fallback SMTP host
    EMAIL_SMTP_PORT     — Fallback SMTP port (default: 587)
    EMAIL_ADDRESS       — Fallback SMTP address
    EMAIL_PASSWORD      — Fallback SMTP password
"""

import json
import logging
import os
import smtplib
import ssl
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)


def _get_resend_key() -> str:
    """Read RESEND_API_KEY from env or ~/.hermes/.env."""
    key = os.environ.get("RESEND_API_KEY", "")
    if key:
        return key
    env_path = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("RESEND_API_KEY="):
                    return line.split("=", 1)[1].strip()
    return ""


def send_email(
    to: str,
    subject: str,
    body: str,
    from_address: Optional[str] = None,
    from_name: Optional[str] = None,
    reply_to: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
    html: Optional[str] = None,
) -> dict:
    """Send an email via Resend (preferred) or SMTP fallback.

    Returns: {"success": True, "message_id": "...", "provider": "resend"|"smtp"}
             or {"success": False, "error": "..."}
    """
    resend_key = _get_resend_key()
    if resend_key:
        result = _send_via_resend(
            resend_key, to, subject, body, from_address, from_name,
            reply_to, in_reply_to, references, html,
        )
        if result.get("success"):
            return result
        logger.warning("Resend failed (%s), falling back to SMTP", result.get("error"))

    return _send_via_smtp(
        to, subject, body, from_address, from_name,
        in_reply_to, references,
    )


def _send_via_resend(
    api_key: str,
    to: str,
    subject: str,
    body: str,
    from_address: Optional[str] = None,
    from_name: Optional[str] = None,
    reply_to: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
    html: Optional[str] = None,
) -> dict:
    """Send via Resend API (https://resend.com/docs/api-reference/emails/send-email)."""
    try:
        import urllib.request
    except ImportError:
        return {"success": False, "error": "urllib not available"}

    sender = from_address or os.environ.get("EMAIL_FROM_ADDRESS", "") or os.environ.get("EMAIL_ADDRESS", "")
    if not sender:
        return {"success": False, "error": "No sender address configured"}

    if from_name:
        sender_field = f"{from_name} <{sender}>"
    else:
        sender_field = sender

    payload = {
        "from": sender_field,
        "to": [to] if isinstance(to, str) else to,
        "subject": subject,
        "text": body,
    }
    if html:
        payload["html"] = html
    if reply_to:
        payload["reply_to"] = reply_to

    # Threading headers
    headers_list = []
    if in_reply_to:
        headers_list.append({"name": "In-Reply-To", "value": in_reply_to})
    if references:
        headers_list.append({"name": "References", "value": references})
    if headers_list:
        payload["headers"] = {h["name"]: h["value"] for h in headers_list}

    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            msg_id = result.get("id", "")
            logger.info("Email sent via Resend to %s (id: %s)", to, msg_id)
            return {"success": True, "message_id": msg_id, "provider": "resend"}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else str(e)
        logger.warning("Resend API error %d: %s", e.code, error_body)
        return {"success": False, "error": f"Resend API {e.code}: {error_body}"}
    except Exception as e:
        return {"success": False, "error": f"Resend request failed: {e}"}


def _send_via_smtp(
    to: str,
    subject: str,
    body: str,
    from_address: Optional[str] = None,
    from_name: Optional[str] = None,
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
) -> dict:
    """Send via SMTP as fallback."""
    smtp_host = os.environ.get("EMAIL_SMTP_HOST", "")
    smtp_port = int(os.environ.get("EMAIL_SMTP_PORT", "587"))
    address = from_address or os.environ.get("EMAIL_ADDRESS", "")
    password = os.environ.get("EMAIL_PASSWORD", "")

    if not all([smtp_host, address, password]):
        return {"success": False, "error": "SMTP not configured (EMAIL_SMTP_HOST, EMAIL_ADDRESS, EMAIL_PASSWORD required)"}

    try:
        msg = MIMEMultipart()
        if from_name:
            msg["From"] = f"{from_name} <{address}>"
        else:
            msg["From"] = address
        msg["To"] = to
        msg["Subject"] = subject

        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = references

        domain = address.split("@")[1] if "@" in address else "hermes.local"
        msg_id = f"<hermes-{uuid.uuid4().hex[:12]}@{domain}>"
        msg["Message-ID"] = msg_id

        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.starttls(context=ssl.create_default_context())
            server.login(address, password)
            server.send_message(msg)

        logger.info("Email sent via SMTP to %s", to)
        return {"success": True, "message_id": msg_id, "provider": "smtp"}
    except Exception as e:
        logger.warning("SMTP send failed to %s: %s", to, e)
        return {"success": False, "error": f"SMTP failed: {e}"}
