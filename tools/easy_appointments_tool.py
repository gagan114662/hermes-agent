"""
Easy!Appointments Booking Tool — manage appointments via self-hosted Easy!Appointments.
Open source alternative to Cal.com / Calendly. No API key needed — just Basic Auth.

Self-hosting: https://github.com/alextselegidis/easyappointments (PHP)
Docker: docker run -d -p 8080:80 alextselegidis/easyappointments

Env vars required:
    EASYAPP_URL       — Base URL (e.g. http://localhost:8080 or https://book.yourdomain.com)
    EASYAPP_USERNAME  — Admin username
    EASYAPP_PASSWORD  — Admin password
"""
import logging
import os
import httpx
from tools.registry import registry

logger = logging.getLogger(__name__)


def _base() -> str:
    url = os.environ.get("EASYAPP_URL", "").rstrip("/")
    return f"{url}/index.php/api/v1"


def _auth():
    return (
        os.environ.get("EASYAPP_USERNAME", ""),
        os.environ.get("EASYAPP_PASSWORD", ""),
    )


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------

def easyapp_list_appointments(date: str = "", limit: int = 20) -> str:
    """
    List upcoming appointments.
    date: filter by date YYYY-MM-DD (optional)
    """
    base = _base()
    if not os.environ.get("EASYAPP_URL"):
        return "Error: EASYAPP_URL not set"
    params = {"length": limit, "sort": "start_datetime"}
    if date:
        params["q"] = date
    try:
        resp = httpx.get(f"{base}/appointments", auth=_auth(), params=params, timeout=15)
        resp.raise_for_status()
        appts = resp.json()
        if not appts:
            return "No appointments found."
        lines = ["Appointments:"]
        for a in appts[:limit]:
            start = a.get("start_datetime", "")[:16]
            end = a.get("end_datetime", "")[:16]
            customer = a.get("customer", {})
            name = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip() or "Unknown"
            service = a.get("service", {}).get("name", "")
            notes = a.get("notes", "")
            lines.append(f"  • {start} → {end} | {name} | {service}" + (f" | {notes}" if notes else ""))
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code} — {e.response.text[:200]}"
    except Exception as e:
        logger.error("easyapp_list_appointments error: %s", e)
        return f"Error: {e}"


def easyapp_create_appointment(
    customer_name: str,
    customer_email: str,
    customer_phone: str,
    service_id: int,
    provider_id: int,
    start_datetime: str,
    end_datetime: str,
    notes: str = "",
) -> str:
    """
    Create an appointment.
    start_datetime / end_datetime: format 'YYYY-MM-DD HH:MM:SS'
    """
    base = _base()
    if not os.environ.get("EASYAPP_URL"):
        return "Error: EASYAPP_URL not set"

    first, *rest = customer_name.split(" ")
    last = " ".join(rest) if rest else ""

    payload = {
        "start_datetime": start_datetime,
        "end_datetime": end_datetime,
        "notes": notes,
        "service_id": service_id,
        "provider_id": provider_id,
        "customer": {
            "first_name": first,
            "last_name": last,
            "email": customer_email,
            "phone_number": customer_phone,
        },
    }
    try:
        resp = httpx.post(f"{base}/appointments", auth=_auth(), json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        appt_id = data.get("id", "")
        return (
            f"Appointment created. ID: {appt_id} | "
            f"{customer_name} | {start_datetime} | Service ID: {service_id}"
        )
    except httpx.HTTPStatusError as e:
        return f"Error creating appointment: HTTP {e.response.status_code} — {e.response.text[:300]}"
    except Exception as e:
        return f"Error: {e}"


def easyapp_cancel_appointment(appointment_id: int) -> str:
    """Cancel (delete) an appointment by ID."""
    base = _base()
    if not os.environ.get("EASYAPP_URL"):
        return "Error: EASYAPP_URL not set"
    try:
        resp = httpx.delete(f"{base}/appointments/{appointment_id}", auth=_auth(), timeout=10)
        resp.raise_for_status()
        return f"Appointment {appointment_id} cancelled."
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code}"
    except Exception as e:
        return f"Error: {e}"


def easyapp_list_services() -> str:
    """List all services available for booking."""
    base = _base()
    if not os.environ.get("EASYAPP_URL"):
        return "Error: EASYAPP_URL not set"
    try:
        resp = httpx.get(f"{base}/services", auth=_auth(), timeout=10)
        resp.raise_for_status()
        services = resp.json()
        if not services:
            return "No services configured."
        lines = ["Available services:"]
        for s in services:
            duration = s.get("duration", "")
            price = s.get("price", "")
            lines.append(f"  • ID:{s.get('id')} — {s.get('name')} | {duration} min | ${price}")
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code}"
    except Exception as e:
        return f"Error: {e}"


def easyapp_list_providers() -> str:
    """List all service providers (staff/employees)."""
    base = _base()
    if not os.environ.get("EASYAPP_URL"):
        return "Error: EASYAPP_URL not set"
    try:
        resp = httpx.get(f"{base}/providers", auth=_auth(), timeout=10)
        resp.raise_for_status()
        providers = resp.json()
        if not providers:
            return "No providers configured."
        lines = ["Providers:"]
        for p in providers:
            name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
            lines.append(f"  • ID:{p.get('id')} — {name} | {p.get('email', '')}")
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code}"
    except Exception as e:
        return f"Error: {e}"


def easyapp_get_availability(service_id: int, provider_id: int, date: str) -> str:
    """
    Get available time slots for a service/provider on a date.
    date: YYYY-MM-DD
    """
    base = _base()
    if not os.environ.get("EASYAPP_URL"):
        return "Error: EASYAPP_URL not set"
    try:
        resp = httpx.get(
            f"{base}/availabilities",
            auth=_auth(),
            params={"service_id": service_id, "provider_id": provider_id, "date": date},
            timeout=15,
        )
        resp.raise_for_status()
        slots = resp.json()
        if not slots:
            return f"No available slots for service {service_id} on {date}."
        lines = [f"Available slots on {date} (Service {service_id}, Provider {provider_id}):"]
        for slot in slots[:30]:
            lines.append(f"  • {slot}")
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code}"
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _check_easyapp():
    if not os.environ.get("EASYAPP_URL"):
        return False, "EASYAPP_URL not set"
    if not os.environ.get("EASYAPP_USERNAME"):
        return False, "EASYAPP_USERNAME not set"
    return True, "Easy!Appointments configured"


_EASYAPP_ENVS = ["EASYAPP_URL", "EASYAPP_USERNAME", "EASYAPP_PASSWORD"]

registry.register(
    name="easyapp_list_appointments",
    toolset="easy-appointments",
    schema={
        "name": "easyapp_list_appointments",
        "description": "List upcoming appointments from self-hosted Easy!Appointments booking system.",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Filter by date YYYY-MM-DD (optional)"},
                "limit": {"type": "integer", "description": "Max results (default 20)"},
            },
            "required": [],
        },
    },
    handler=lambda args, **kw: easyapp_list_appointments(args.get("date", ""), args.get("limit", 20)),
    check_fn=_check_easyapp,
    requires_env=_EASYAPP_ENVS,
    emoji="📅",
)

registry.register(
    name="easyapp_create_appointment",
    toolset="easy-appointments",
    schema={
        "name": "easyapp_create_appointment",
        "description": "Book an appointment in Easy!Appointments for a customer.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string"},
                "customer_email": {"type": "string"},
                "customer_phone": {"type": "string"},
                "service_id": {"type": "integer", "description": "Service ID from easyapp_list_services"},
                "provider_id": {"type": "integer", "description": "Provider ID from easyapp_list_providers"},
                "start_datetime": {"type": "string", "description": "Start time: 'YYYY-MM-DD HH:MM:SS'"},
                "end_datetime": {"type": "string", "description": "End time: 'YYYY-MM-DD HH:MM:SS'"},
                "notes": {"type": "string"},
            },
            "required": ["customer_name", "customer_email", "customer_phone", "service_id", "provider_id", "start_datetime", "end_datetime"],
        },
    },
    handler=lambda args, **kw: easyapp_create_appointment(
        args["customer_name"], args["customer_email"], args["customer_phone"],
        args["service_id"], args["provider_id"],
        args["start_datetime"], args["end_datetime"], args.get("notes", "")
    ),
    check_fn=_check_easyapp,
    requires_env=_EASYAPP_ENVS,
    emoji="📅",
)

registry.register(
    name="easyapp_cancel_appointment",
    toolset="easy-appointments",
    schema={
        "name": "easyapp_cancel_appointment",
        "description": "Cancel an appointment by its ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "appointment_id": {"type": "integer", "description": "Appointment ID to cancel"},
            },
            "required": ["appointment_id"],
        },
    },
    handler=lambda args, **kw: easyapp_cancel_appointment(args["appointment_id"]),
    check_fn=_check_easyapp,
    requires_env=_EASYAPP_ENVS,
    emoji="📅",
)

registry.register(
    name="easyapp_list_services",
    toolset="easy-appointments",
    schema={
        "name": "easyapp_list_services",
        "description": "List all bookable services and their durations/prices.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    handler=lambda args, **kw: easyapp_list_services(),
    check_fn=_check_easyapp,
    requires_env=_EASYAPP_ENVS,
    emoji="📅",
)

registry.register(
    name="easyapp_list_providers",
    toolset="easy-appointments",
    schema={
        "name": "easyapp_list_providers",
        "description": "List all service providers/staff available for booking.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    handler=lambda args, **kw: easyapp_list_providers(),
    check_fn=_check_easyapp,
    requires_env=_EASYAPP_ENVS,
    emoji="📅",
)

registry.register(
    name="easyapp_get_availability",
    toolset="easy-appointments",
    schema={
        "name": "easyapp_get_availability",
        "description": "Get available time slots for a service and provider on a specific date.",
        "parameters": {
            "type": "object",
            "properties": {
                "service_id": {"type": "integer"},
                "provider_id": {"type": "integer"},
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
            },
            "required": ["service_id", "provider_id", "date"],
        },
    },
    handler=lambda args, **kw: easyapp_get_availability(
        args["service_id"], args["provider_id"], args["date"]
    ),
    check_fn=_check_easyapp,
    requires_env=_EASYAPP_ENVS,
    emoji="📅",
)
