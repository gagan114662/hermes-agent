"""Vapi.ai inbound call webhook handler.

Parses Vapi end-of-call-report webhook payloads and formats them into
Hermes agent prompts that save caller to CRM, log the interaction,
detect hot leads, and notify the business owner via Telegram.
"""

import hmac
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Hot-lead keywords to detect in summary / transcript
_HOT_KEYWORDS = ["interested", "pricing", "sign up", "demo", "yes", "how much", "when can"]

# Max transcript length included in the agent prompt
_TRANSCRIPT_MAX_CHARS = 2000


def validate_secret(header_value: str) -> bool:
    """Validate the x-vapi-secret header against VAPI_WEBHOOK_SECRET env var.

    If the env var is not set (empty string) we are in dev mode — log a
    warning and accept all requests.  When set, use constant-time comparison
    to prevent timing attacks.
    """
    expected = os.environ.get("VAPI_WEBHOOK_SECRET", "")
    if not expected:
        logger.warning(
            "VAPI_WEBHOOK_SECRET is not set — accepting all webhook requests (dev mode)"
        )
        return True
    return hmac.compare_digest(header_value, expected)


def parse_vapi_event(payload: dict) -> Optional[dict]:
    """Parse a Vapi webhook payload.

    Returns a normalised event dict for end-of-call-report events, or None
    for any other event type (including malformed payloads).
    """
    msg = payload.get("message", {})
    event_type = msg.get("type")
    if event_type != "end-of-call-report":
        return None

    call = msg.get("call", {})
    customer = call.get("customer", {})

    return {
        "type": event_type,
        "call_id": call.get("id", ""),
        "caller": customer.get("number", "unknown"),
        "duration": call.get("duration", 0),
        "ended_reason": call.get("endedReason", ""),
        "transcript": msg.get("transcript", ""),
        "summary": msg.get("summary", ""),
        "recording_url": msg.get("recordingUrl", ""),
    }


def format_agent_prompt(event: dict) -> str:
    """Build a Hermes agent prompt from a parsed Vapi end-of-call event.

    Detects hot leads by scanning summary and transcript for keywords and
    prepends a HOT LEAD flag when found.  The prompt instructs Hermes to:

    1. Save / update the caller in the CRM (crm_save)
    2. Log the call interaction (crm_log)
    3. If hot lead, add to prospect tracker with score ≥ 7 (prospect_add)
    4. Notify business owner on Telegram (send_message)
    5. If follow-up requested, schedule an SMS in 24 h (cronjob)
    """
    caller = event.get("caller", "unknown")
    duration = event.get("duration", 0)
    call_id = event.get("call_id", "")
    ended_reason = event.get("ended_reason", "")
    summary = event.get("summary", "")
    recording_url = event.get("recording_url", "")

    transcript_raw = event.get("transcript", "")
    transcript = transcript_raw[:_TRANSCRIPT_MAX_CHARS]
    if len(transcript_raw) > _TRANSCRIPT_MAX_CHARS:
        transcript += "\n[... transcript truncated ...]"

    # Detect hot lead
    combined_text = (summary + " " + transcript).lower()
    is_hot = any(kw in combined_text for kw in _HOT_KEYWORDS)

    # Detect follow-up request
    follow_up_keywords = ["follow up", "follow-up", "call me back", "call back", "reach out", "contact me"]
    needs_follow_up = any(kw in combined_text for kw in follow_up_keywords)

    hot_prefix = "🔥 HOT LEAD — " if is_hot else ""

    prospect_instruction = ""
    if is_hot:
        prospect_instruction = f"""
3. **prospect_add** — Add {caller} to the prospect tracker with score ≥ 7, noting they showed strong buying signals."""

    follow_up_instruction = ""
    if needs_follow_up:
        follow_up_instruction = f"""
5. **cronjob** — Schedule an SMS follow-up to {caller} in 24 hours thanking them for the call and offering next steps."""

    prompt = f"""{hot_prefix}A call just ended on the Vapi AI phone system. Please handle the following actions:

**Call Details**
- Caller: {caller}
- Call ID: {call_id}
- Duration: {duration} seconds
- Ended reason: {ended_reason}
- Recording: {recording_url or "not available"}

**Summary**
{summary}

**Transcript**
{transcript}

---

**Required Actions**

1. **crm_save** — Add or update {caller} as a contact in the CRM. Include the caller number, call date, and any details from the summary.

2. **crm_log** — Log this call interaction for {caller} with duration {duration}s, the summary above, and call ID {call_id}.
{prospect_instruction}
4. **send_message** — Notify the business owner on Telegram with the following:
   - Caller: {caller}
   - Duration: {duration} seconds
   - Summary: {summary}
{follow_up_instruction}

Complete all required actions now."""

    return prompt
