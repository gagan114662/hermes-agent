"""
Mautic Email Marketing Tool — manage contacts, send campaigns, and run drip sequences.

Env vars required:
    MAUTIC_BASE_URL  — Your Mautic instance URL (e.g. https://mail.yourdomain.com)
    MAUTIC_USERNAME  — Mautic API username
    MAUTIC_PASSWORD  — Mautic API password

Mautic uses HTTP Basic Auth for API v1.
"""
import logging
import os
import httpx
from tools.registry import registry

logger = logging.getLogger(__name__)


def _base() -> str:
    return os.environ.get("MAUTIC_BASE_URL", "").rstrip("/")


def _auth():
    return (
        os.environ.get("MAUTIC_USERNAME", ""),
        os.environ.get("MAUTIC_PASSWORD", ""),
    )


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------

def email_contact_add(email: str, first_name: str = "", last_name: str = "", tags: list = None) -> str:
    """Add or update a contact in Mautic. Returns contact ID."""
    base = _base()
    if not base:
        return "Error: MAUTIC_BASE_URL not set"
    payload = {"email": email}
    if first_name:
        payload["firstname"] = first_name
    if last_name:
        payload["lastname"] = last_name
    if tags:
        payload["tags"] = tags
    try:
        resp = httpx.post(
            f"{base}/api/contacts/new",
            auth=_auth(),
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("contact", {})
        contact_id = data.get("id")
        return f"Contact added/updated. ID: {contact_id}, Email: {email}"
    except httpx.HTTPStatusError as e:
        return f"Error adding contact: HTTP {e.response.status_code} — {e.response.text[:200]}"
    except Exception as e:
        logger.error("email_contact_add error: %s", e)
        return f"Error: {e}"


def email_campaign_send(campaign_id: str, contact_emails: list = None) -> str:
    """
    Trigger an email campaign. If contact_emails is provided, adds those contacts first.
    campaign_id: Mautic campaign ID (numeric string)
    """
    base = _base()
    if not base:
        return "Error: MAUTIC_BASE_URL not set"

    added = []
    if contact_emails:
        for email in contact_emails:
            try:
                r = httpx.post(
                    f"{base}/api/contacts/new",
                    auth=_auth(),
                    json={"email": email},
                    timeout=10,
                )
                r.raise_for_status()
                cid = r.json().get("contact", {}).get("id")
                if cid:
                    added.append(cid)
            except Exception:
                pass

    # Add contacts to campaign
    results = []
    for cid in added:
        try:
            r = httpx.post(
                f"{base}/api/campaigns/{campaign_id}/contact/{cid}/add",
                auth=_auth(),
                timeout=10,
            )
            results.append(f"Contact {cid}: {'added' if r.status_code < 300 else 'failed'}")
        except Exception as e:
            results.append(f"Contact {cid}: error — {e}")

    summary = f"Campaign {campaign_id} triggered."
    if results:
        summary += f" {len(added)} contacts enrolled.\n" + "\n".join(results)
    return summary


def email_broadcast_send(email_id: str) -> str:
    """
    Send a broadcast email (one-off blast) to its configured segment.
    email_id: Mautic email ID (numeric string)
    """
    base = _base()
    if not base:
        return "Error: MAUTIC_BASE_URL not set"
    try:
        resp = httpx.post(
            f"{base}/api/emails/{email_id}/send",
            auth=_auth(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        sent = data.get("sentCount", "unknown")
        failed = data.get("failedCount", 0)
        return f"Broadcast sent. Sent: {sent}, Failed: {failed}"
    except httpx.HTTPStatusError as e:
        return f"Error sending broadcast: HTTP {e.response.status_code} — {e.response.text[:200]}"
    except Exception as e:
        return f"Error: {e}"


def email_list_campaigns() -> str:
    """List all campaigns in Mautic."""
    base = _base()
    if not base:
        return "Error: MAUTIC_BASE_URL not set"
    try:
        resp = httpx.get(
            f"{base}/api/campaigns",
            auth=_auth(),
            params={"limit": 50},
            timeout=15,
        )
        resp.raise_for_status()
        campaigns = resp.json().get("campaigns", {})
        if not campaigns:
            return "No campaigns found."
        lines = ["Campaigns:"]
        for cid, camp in campaigns.items():
            published = "✅" if camp.get("isPublished") else "⏸"
            lines.append(f"  {published} ID:{cid} — {camp.get('name')}")
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        return f"Error listing campaigns: HTTP {e.response.status_code}"
    except Exception as e:
        return f"Error: {e}"


def email_list_emails() -> str:
    """List all email templates/broadcasts in Mautic."""
    base = _base()
    if not base:
        return "Error: MAUTIC_BASE_URL not set"
    try:
        resp = httpx.get(
            f"{base}/api/emails",
            auth=_auth(),
            params={"limit": 50},
            timeout=15,
        )
        resp.raise_for_status()
        emails = resp.json().get("emails", {})
        if not emails:
            return "No email templates found."
        lines = ["Email templates:"]
        for eid, email in emails.items():
            etype = email.get("emailType", "")
            lines.append(f"  ID:{eid} — {email.get('name')} [{etype}]")
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        return f"Error listing emails: HTTP {e.response.status_code}"
    except Exception as e:
        return f"Error: {e}"


def email_stats(email_id: str) -> str:
    """Get open/click stats for an email."""
    base = _base()
    if not base:
        return "Error: MAUTIC_BASE_URL not set"
    try:
        resp = httpx.get(
            f"{base}/api/emails/{email_id}",
            auth=_auth(),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("email", {})
        name = data.get("name", email_id)
        sent = data.get("sentCount", 0)
        read = data.get("readCount", 0)
        clicks = data.get("clickCount", 0)
        rate = round(read / sent * 100, 1) if sent else 0
        return (
            f"Email '{name}': Sent {sent}, Opens {read} ({rate}% rate), Clicks {clicks}"
        )
    except httpx.HTTPStatusError as e:
        return f"Error getting email stats: HTTP {e.response.status_code}"
    except Exception as e:
        return f"Error: {e}"


def email_segment_add_contact(segment_id: str, email: str) -> str:
    """Add a contact to a Mautic segment (list)."""
    base = _base()
    if not base:
        return "Error: MAUTIC_BASE_URL not set"
    # First find contact ID
    try:
        r = httpx.get(
            f"{base}/api/contacts",
            auth=_auth(),
            params={"search": email, "limit": 1},
            timeout=10,
        )
        r.raise_for_status()
        contacts = r.json().get("contacts", {})
        if not contacts:
            # Create contact
            cr = httpx.post(f"{base}/api/contacts/new", auth=_auth(), json={"email": email}, timeout=10)
            cr.raise_for_status()
            contact_id = cr.json().get("contact", {}).get("id")
        else:
            contact_id = list(contacts.values())[0]["id"]

        sr = httpx.post(
            f"{base}/api/segments/{segment_id}/contact/{contact_id}/add",
            auth=_auth(),
            timeout=10,
        )
        sr.raise_for_status()
        return f"Contact {email} added to segment {segment_id}."
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code}"
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _check_email_marketing():
    if not os.environ.get("MAUTIC_BASE_URL"):
        return False, "MAUTIC_BASE_URL not set"
    if not os.environ.get("MAUTIC_USERNAME"):
        return False, "MAUTIC_USERNAME not set"
    return True, "Mautic email marketing configured"


_MAUTIC_ENVS = ["MAUTIC_BASE_URL", "MAUTIC_USERNAME", "MAUTIC_PASSWORD"]

registry.register(
    name="email_contact_add",
    toolset="email-marketing",
    schema={
        "name": "email_contact_add",
        "description": "Add or update a contact in the email marketing system (Mautic).",
        "parameters": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "description": "Contact email address"},
                "first_name": {"type": "string"},
                "last_name": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags to apply to this contact"},
            },
            "required": ["email"],
        },
    },
    handler=lambda args, **kw: email_contact_add(
        args["email"], args.get("first_name", ""), args.get("last_name", ""), args.get("tags")
    ),
    check_fn=_check_email_marketing,
    requires_env=_MAUTIC_ENVS,
    emoji="📧",
)

registry.register(
    name="email_campaign_send",
    toolset="email-marketing",
    schema={
        "name": "email_campaign_send",
        "description": "Enroll contacts into an email drip campaign (nurture sequence).",
        "parameters": {
            "type": "object",
            "properties": {
                "campaign_id": {"type": "string", "description": "Mautic campaign ID"},
                "contact_emails": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Email addresses to enroll (optional if they are already in Mautic)",
                },
            },
            "required": ["campaign_id"],
        },
    },
    handler=lambda args, **kw: email_campaign_send(args["campaign_id"], args.get("contact_emails")),
    check_fn=_check_email_marketing,
    requires_env=_MAUTIC_ENVS,
    emoji="📧",
)

registry.register(
    name="email_broadcast_send",
    toolset="email-marketing",
    schema={
        "name": "email_broadcast_send",
        "description": "Send a one-time broadcast email to its configured segment.",
        "parameters": {
            "type": "object",
            "properties": {
                "email_id": {"type": "string", "description": "Mautic email template ID to send"},
            },
            "required": ["email_id"],
        },
    },
    handler=lambda args, **kw: email_broadcast_send(args["email_id"]),
    check_fn=_check_email_marketing,
    requires_env=_MAUTIC_ENVS,
    emoji="📧",
)

registry.register(
    name="email_list_campaigns",
    toolset="email-marketing",
    schema={
        "name": "email_list_campaigns",
        "description": "List all email drip campaigns in the marketing system.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    handler=lambda args, **kw: email_list_campaigns(),
    check_fn=_check_email_marketing,
    requires_env=_MAUTIC_ENVS,
    emoji="📧",
)

registry.register(
    name="email_list_emails",
    toolset="email-marketing",
    schema={
        "name": "email_list_emails",
        "description": "List all email templates and broadcasts.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    handler=lambda args, **kw: email_list_emails(),
    check_fn=_check_email_marketing,
    requires_env=_MAUTIC_ENVS,
    emoji="📧",
)

registry.register(
    name="email_stats",
    toolset="email-marketing",
    schema={
        "name": "email_stats",
        "description": "Get open rate, click rate, and send count stats for an email.",
        "parameters": {
            "type": "object",
            "properties": {
                "email_id": {"type": "string", "description": "Mautic email ID"},
            },
            "required": ["email_id"],
        },
    },
    handler=lambda args, **kw: email_stats(args["email_id"]),
    check_fn=_check_email_marketing,
    requires_env=_MAUTIC_ENVS,
    emoji="📧",
)

registry.register(
    name="email_segment_add_contact",
    toolset="email-marketing",
    schema={
        "name": "email_segment_add_contact",
        "description": "Add a contact to a specific email list/segment.",
        "parameters": {
            "type": "object",
            "properties": {
                "segment_id": {"type": "string", "description": "Mautic segment ID"},
                "email": {"type": "string", "description": "Contact email address"},
            },
            "required": ["segment_id", "email"],
        },
    },
    handler=lambda args, **kw: email_segment_add_contact(args["segment_id"], args["email"]),
    check_fn=_check_email_marketing,
    requires_env=_MAUTIC_ENVS,
    emoji="📧",
)
