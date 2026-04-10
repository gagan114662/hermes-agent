"""
Hermes Worker Mailbox

Each worker has a dedicated email address: {name}-{slug}@hermes-worker.com

Inbound:  Mailgun webhooks POST to /mailbox/inbound on the gateway.
          The message is pushed to Redis so the worker processes it like
          any other message.

Outbound: Call send_as_worker() from within a worker session.
          Sends via Mailgun API from the worker's address.

Env vars:
    MAILGUN_API_KEY   your Mailgun API key
    MAILGUN_DOMAIN    your Mailgun domain (e.g. mg.hermes-worker.com)
"""

import logging
import os

import httpx

logger = logging.getLogger("hermes.mailbox")

MAILGUN_API_KEY = os.getenv("MAILGUN_API_KEY", "")
MAILGUN_DOMAIN = os.getenv("MAILGUN_DOMAIN", "mg.hermes-worker.com")


def send_as_worker(
    from_address: str,
    to: str,
    subject: str,
    body: str,
    reply_to: str | None = None,
) -> bool:
    """
    Send an email from a worker's address via Mailgun.

    Args:
        from_address: The worker's email (e.g. marco-marios-pizza@hermes-worker.com)
        to: Recipient email address
        subject: Email subject line
        body: Plain text body
        reply_to: Optional reply-to address

    Returns:
        True if sent successfully, False otherwise.
    """
    if not MAILGUN_API_KEY:
        logger.warning("MAILGUN_API_KEY not set — cannot send email")
        return False

    data = {
        "from": from_address,
        "to": to,
        "subject": subject,
        "text": body,
    }
    if reply_to:
        data["h:Reply-To"] = reply_to

    try:
        resp = httpx.post(
            f"https://api.mailgun.net/v3/{MAILGUN_DOMAIN}/messages",
            auth=("api", MAILGUN_API_KEY),
            data=data,
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("Email sent from %s to %s (subject: %s)", from_address, to, subject)
        return True
    except httpx.HTTPError as e:
        logger.error("Mailgun send failed: %s", e)
        return False
