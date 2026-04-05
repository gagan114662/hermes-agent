"""
Cal.com Booking Tool — create booking links, list availability, manage appointments.

Env vars required:
    CALCOM_API_KEY   — Cal.com API key (get from cal.com/settings/developer/api-keys)
    CALCOM_EVENT_ID  — Default event type ID (numeric, from cal.com/event-types)

Optional:
    CALCOM_BASE_URL  — Override for self-hosted Cal.com (default: https://api.cal.com/v1)
"""
import logging
import os
import httpx
from tools.registry import registry

logger = logging.getLogger(__name__)

CALCOM_BASE = os.getenv("CALCOM_BASE_URL", "https://api.cal.com/v1")


def _headers():
    key = os.environ.get("CALCOM_API_KEY", "")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _api_key():
    return os.environ.get("CALCOM_API_KEY", "")


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------

def booking_create_link(event_type_id: str = "", duration_minutes: int = 30) -> str:
    """
    Return a shareable booking link for a given Cal.com event type.
    If event_type_id is omitted, uses CALCOM_EVENT_ID env var.
    """
    eid = event_type_id or os.environ.get("CALCOM_EVENT_ID", "")
    if not eid:
        return "Error: provide event_type_id or set CALCOM_EVENT_ID"
    try:
        resp = httpx.get(
            f"{CALCOM_BASE}/event-types/{eid}",
            params={"apiKey": _api_key()},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("event_type", resp.json())
        slug = data.get("slug", "")
        username = data.get("users", [{}])[0].get("username", "me")
        link = f"https://cal.com/{username}/{slug}"
        return f"Booking link: {link}"
    except httpx.HTTPStatusError as e:
        return f"Error fetching event type: HTTP {e.response.status_code}"
    except Exception as e:
        logger.error("booking_create_link error: %s", e)
        return f"Error: {e}"


def booking_list_slots(date: str, event_type_id: str = "") -> str:
    """
    List available booking slots for a date (YYYY-MM-DD).
    Returns a formatted list of open time slots.
    """
    eid = event_type_id or os.environ.get("CALCOM_EVENT_ID", "")
    if not eid:
        return "Error: provide event_type_id or set CALCOM_EVENT_ID"
    if not date:
        return "Error: date is required (YYYY-MM-DD)"
    try:
        resp = httpx.get(
            f"{CALCOM_BASE}/slots",
            params={
                "apiKey": _api_key(),
                "eventTypeId": eid,
                "startTime": f"{date}T00:00:00Z",
                "endTime": f"{date}T23:59:59Z",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        slots = data.get("slots", {})
        if not slots:
            return f"No available slots on {date}"
        result = [f"Available slots on {date}:"]
        for day_slots in slots.values():
            for slot in day_slots[:20]:
                result.append(f"  • {slot.get('time', '')}")
        return "\n".join(result)
    except httpx.HTTPStatusError as e:
        return f"Error fetching slots: HTTP {e.response.status_code}"
    except Exception as e:
        logger.error("booking_list_slots error: %s", e)
        return f"Error: {e}"


def booking_list_upcoming(limit: int = 10) -> str:
    """
    List upcoming confirmed bookings for the Cal.com account.
    """
    try:
        resp = httpx.get(
            f"{CALCOM_BASE}/bookings",
            params={"apiKey": _api_key(), "status": "upcoming", "take": limit},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        bookings = data.get("bookings", [])
        if not bookings:
            return "No upcoming bookings."
        lines = ["Upcoming bookings:"]
        for b in bookings:
            attendees = ", ".join(a.get("name", "") for a in b.get("attendees", []))
            lines.append(
                f"  • {b.get('startTime', '')[:16]} — {b.get('title', 'Meeting')} "
                f"with {attendees} (ID: {b.get('id')})"
            )
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        return f"Error fetching bookings: HTTP {e.response.status_code}"
    except Exception as e:
        logger.error("booking_list_upcoming error: %s", e)
        return f"Error: {e}"


def booking_cancel(booking_id: str, reason: str = "Cancelled by AI employee") -> str:
    """Cancel a booking by its ID."""
    if not booking_id:
        return "Error: booking_id is required"
    try:
        resp = httpx.delete(
            f"{CALCOM_BASE}/bookings/{booking_id}",
            params={"apiKey": _api_key()},
            json={"reason": reason},
            timeout=10,
        )
        resp.raise_for_status()
        return f"Booking {booking_id} cancelled."
    except httpx.HTTPStatusError as e:
        return f"Error cancelling booking: HTTP {e.response.status_code}"
    except Exception as e:
        logger.error("booking_cancel error: %s", e)
        return f"Error: {e}"


def booking_reschedule(booking_id: str, new_start_time: str, reason: str = "") -> str:
    """
    Reschedule a booking to a new time.
    new_start_time: ISO 8601 format (e.g. 2026-04-10T14:00:00Z)
    """
    if not booking_id or not new_start_time:
        return "Error: booking_id and new_start_time are required"
    try:
        resp = httpx.patch(
            f"{CALCOM_BASE}/bookings/{booking_id}",
            params={"apiKey": _api_key()},
            json={"startTime": new_start_time, "rescheduleReason": reason},
            timeout=10,
        )
        resp.raise_for_status()
        return f"Booking {booking_id} rescheduled to {new_start_time}."
    except httpx.HTTPStatusError as e:
        return f"Error rescheduling: HTTP {e.response.status_code}"
    except Exception as e:
        logger.error("booking_reschedule error: %s", e)
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _check_booking():
    if not os.environ.get("CALCOM_API_KEY"):
        return False, "CALCOM_API_KEY not set"
    return True, "Cal.com configured"


registry.register(
    name="booking_create_link",
    toolset="booking",
    schema={
        "name": "booking_create_link",
        "description": "Get a shareable Cal.com booking link customers can use to schedule an appointment.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_type_id": {"type": "string", "description": "Cal.com event type ID (numeric). Uses CALCOM_EVENT_ID env var if omitted."},
                "duration_minutes": {"type": "integer", "description": "Meeting duration in minutes (default 30)"},
            },
            "required": [],
        },
    },
    handler=lambda args, **kw: booking_create_link(
        args.get("event_type_id", ""), args.get("duration_minutes", 30)
    ),
    check_fn=_check_booking,
    requires_env=["CALCOM_API_KEY"],
    emoji="📅",
)

registry.register(
    name="booking_list_slots",
    toolset="booking",
    schema={
        "name": "booking_list_slots",
        "description": "List available appointment slots on a specific date.",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                "event_type_id": {"type": "string", "description": "Cal.com event type ID (optional)"},
            },
            "required": ["date"],
        },
    },
    handler=lambda args, **kw: booking_list_slots(args["date"], args.get("event_type_id", "")),
    check_fn=_check_booking,
    requires_env=["CALCOM_API_KEY"],
    emoji="📅",
)

registry.register(
    name="booking_list_upcoming",
    toolset="booking",
    schema={
        "name": "booking_list_upcoming",
        "description": "List upcoming confirmed appointments/bookings.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max number of bookings to return (default 10)"},
            },
            "required": [],
        },
    },
    handler=lambda args, **kw: booking_list_upcoming(args.get("limit", 10)),
    check_fn=_check_booking,
    requires_env=["CALCOM_API_KEY"],
    emoji="📅",
)

registry.register(
    name="booking_cancel",
    toolset="booking",
    schema={
        "name": "booking_cancel",
        "description": "Cancel a booking by its ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "booking_id": {"type": "string", "description": "The Cal.com booking ID to cancel"},
                "reason": {"type": "string", "description": "Cancellation reason"},
            },
            "required": ["booking_id"],
        },
    },
    handler=lambda args, **kw: booking_cancel(args["booking_id"], args.get("reason", "Cancelled by AI employee")),
    check_fn=_check_booking,
    requires_env=["CALCOM_API_KEY"],
    emoji="📅",
)

registry.register(
    name="booking_reschedule",
    toolset="booking",
    schema={
        "name": "booking_reschedule",
        "description": "Reschedule an existing booking to a new time.",
        "parameters": {
            "type": "object",
            "properties": {
                "booking_id": {"type": "string", "description": "The Cal.com booking ID"},
                "new_start_time": {"type": "string", "description": "New start time in ISO 8601 format (e.g. 2026-04-10T14:00:00Z)"},
                "reason": {"type": "string", "description": "Reason for rescheduling"},
            },
            "required": ["booking_id", "new_start_time"],
        },
    },
    handler=lambda args, **kw: booking_reschedule(
        args["booking_id"], args["new_start_time"], args.get("reason", "")
    ),
    check_fn=_check_booking,
    requires_env=["CALCOM_API_KEY"],
    emoji="📅",
)
