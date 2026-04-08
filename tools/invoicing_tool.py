"""
Crater Invoicing Tool — create invoices, estimates/quotes, and track payments.

Env vars required:
    CRATER_BASE_URL   — Your Crater instance URL (e.g. https://invoice.yourdomain.com)
    CRATER_API_TOKEN  — Crater API token (Profile → API Tokens)
    CRATER_COMPANY_ID — Crater company ID (numeric, from URL when logged in)
"""
import logging
import os
import httpx
from tools.registry import registry

logger = logging.getLogger(__name__)


def _base() -> str:
    return os.environ.get("CRATER_BASE_URL", "").rstrip("/")


def _headers():
    return {
        "Authorization": f"Bearer {os.environ.get('CRATER_API_TOKEN', '')}",
        "Content-Type": "application/json",
        "company-id": os.environ.get("CRATER_COMPANY_ID", ""),
    }


def _company_id() -> str:
    return os.environ.get("CRATER_COMPANY_ID", "")


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------

def invoice_create(
    customer_name: str,
    customer_email: str,
    items: list,
    due_date: str = "",
    notes: str = "",
) -> str:
    """
    Create an invoice in Crater and return the invoice number + view URL.

    items: list of dicts with keys: name, quantity, price (in cents)
    e.g. [{"name": "Web design", "quantity": 1, "price": 50000}]
    due_date: YYYY-MM-DD (optional, defaults to 30 days from today)
    """
    base = _base()
    if not base:
        return "Error: CRATER_BASE_URL not set"

    # Ensure customer exists or create
    try:
        # Search for existing customer
        r = httpx.get(
            f"{base}/api/v1/customers",
            headers=_headers(),
            params={"search": customer_email, "company_id": _company_id()},
            timeout=10,
        )
        r.raise_for_status()
        customers = r.json().get("data", [])
        if customers:
            customer_id = customers[0]["id"]
        else:
            # Create customer
            cr = httpx.post(
                f"{base}/api/v1/customers",
                headers=_headers(),
                json={"name": customer_name, "email": customer_email, "company_id": _company_id()},
                timeout=10,
            )
            cr.raise_for_status()
            customer_id = cr.json()["data"]["id"]
    except httpx.HTTPStatusError as e:
        return f"Error creating customer: HTTP {e.response.status_code} — {e.response.text[:200]}"
    except Exception as e:
        logger.error("invoice customer error: %s", e)
        return f"Error: {e}"

    # Build invoice items
    invoice_items = [
        {
            "name": item.get("name", "Service"),
            "quantity": item.get("quantity", 1),
            "price": item.get("price", 0),
            "discount": 0,
            "tax": [],
        }
        for item in items
    ]

    import datetime
    if not due_date:
        due_date = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()

    payload = {
        "customer_id": customer_id,
        "due_date": due_date,
        "invoice_date": datetime.date.today().isoformat(),
        "status": "DRAFT",
        "notes": notes,
        "items": invoice_items,
        "company_id": _company_id(),
    }

    try:
        resp = httpx.post(
            f"{base}/api/v1/invoices",
            headers=_headers(),
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        inv_id = data.get("id")
        inv_num = data.get("invoice_number", inv_id)
        total = data.get("total", 0) / 100
        return (
            f"Invoice #{inv_num} created for {customer_name}. "
            f"Total: ${total:.2f}. Due: {due_date}. "
            f"View: {base}/invoices/{inv_id}/view"
        )
    except httpx.HTTPStatusError as e:
        return f"Error creating invoice: HTTP {e.response.status_code} — {e.response.text[:300]}"
    except Exception as e:
        logger.error("invoice_create error: %s", e)
        return f"Error: {e}"


def invoice_send(invoice_id: str, message: str = "") -> str:
    """Send an invoice to the customer via email."""
    base = _base()
    if not base:
        return "Error: CRATER_BASE_URL not set"
    try:
        resp = httpx.post(
            f"{base}/api/v1/invoices/{invoice_id}/send",
            headers=_headers(),
            json={"message": message or "Please find your invoice attached.", "company_id": _company_id()},
            timeout=15,
        )
        resp.raise_for_status()
        return f"Invoice {invoice_id} sent to customer."
    except httpx.HTTPStatusError as e:
        return f"Error sending invoice: HTTP {e.response.status_code}"
    except Exception as e:
        return f"Error: {e}"


def invoice_list(status: str = "UNPAID", limit: int = 10) -> str:
    """List invoices filtered by status (UNPAID, PAID, DRAFT, OVERDUE)."""
    base = _base()
    if not base:
        return "Error: CRATER_BASE_URL not set"
    try:
        resp = httpx.get(
            f"{base}/api/v1/invoices",
            headers=_headers(),
            params={"status": status, "per_page": limit, "company_id": _company_id()},
            timeout=15,
        )
        resp.raise_for_status()
        invoices = resp.json().get("data", [])
        if not invoices:
            return f"No {status.lower()} invoices."
        lines = [f"{status.title()} invoices:"]
        for inv in invoices:
            total = inv.get("total", 0) / 100
            due = inv.get("due_date", "")
            customer = inv.get("customer", {}).get("name", "Unknown")
            lines.append(f"  • #{inv.get('invoice_number')} — {customer} — ${total:.2f} (due {due})")
        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        return f"Error listing invoices: HTTP {e.response.status_code}"
    except Exception as e:
        return f"Error: {e}"


def estimate_create(
    customer_name: str,
    customer_email: str,
    items: list,
    valid_days: int = 30,
    notes: str = "",
) -> str:
    """
    Create a quote/estimate and return the estimate number + link.
    Items: list of dicts with name, quantity, price (in cents).
    """
    base = _base()
    if not base:
        return "Error: CRATER_BASE_URL not set"

    # Get/create customer
    try:
        r = httpx.get(
            f"{base}/api/v1/customers",
            headers=_headers(),
            params={"search": customer_email, "company_id": _company_id()},
            timeout=10,
        )
        r.raise_for_status()
        customers = r.json().get("data", [])
        if customers:
            customer_id = customers[0]["id"]
        else:
            cr = httpx.post(
                f"{base}/api/v1/customers",
                headers=_headers(),
                json={"name": customer_name, "email": customer_email, "company_id": _company_id()},
                timeout=10,
            )
            cr.raise_for_status()
            customer_id = cr.json()["data"]["id"]
    except Exception as e:
        return f"Error with customer: {e}"

    import datetime
    expiry = (datetime.date.today() + datetime.timedelta(days=valid_days)).isoformat()

    estimate_items = [
        {"name": i.get("name", "Service"), "quantity": i.get("quantity", 1), "price": i.get("price", 0), "discount": 0, "tax": []}
        for i in items
    ]

    try:
        resp = httpx.post(
            f"{base}/api/v1/estimates",
            headers=_headers(),
            json={
                "customer_id": customer_id,
                "estimate_date": datetime.date.today().isoformat(),
                "expiry_date": expiry,
                "notes": notes,
                "items": estimate_items,
                "company_id": _company_id(),
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        est_num = data.get("estimate_number", data.get("id"))
        total = data.get("total", 0) / 100
        est_id = data.get("id")
        return (
            f"Estimate #{est_num} created for {customer_name}. "
            f"Total: ${total:.2f}. Valid for {valid_days} days. "
            f"View: {base}/estimates/{est_id}/view"
        )
    except httpx.HTTPStatusError as e:
        return f"Error creating estimate: HTTP {e.response.status_code} — {e.response.text[:300]}"
    except Exception as e:
        return f"Error: {e}"


def payment_record(invoice_id: str, amount_cents: int, payment_method: str = "Bank Transfer", notes: str = "") -> str:
    """Record a payment received against an invoice."""
    base = _base()
    if not base:
        return "Error: CRATER_BASE_URL not set"
    import datetime
    try:
        resp = httpx.post(
            f"{base}/api/v1/payments",
            headers=_headers(),
            json={
                "invoice_id": invoice_id,
                "amount": amount_cents,
                "payment_date": datetime.date.today().isoformat(),
                "payment_method": payment_method,
                "notes": notes,
                "company_id": _company_id(),
            },
            timeout=15,
        )
        resp.raise_for_status()
        amount = amount_cents / 100
        return f"Payment of ${amount:.2f} recorded for invoice {invoice_id}."
    except httpx.HTTPStatusError as e:
        return f"Error recording payment: HTTP {e.response.status_code}"
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _check_invoicing():
    if not os.environ.get("CRATER_BASE_URL"):
        return False, "CRATER_BASE_URL not set"
    if not os.environ.get("CRATER_API_TOKEN"):
        return False, "CRATER_API_TOKEN not set"
    return True, "Crater invoicing configured"


registry.register(
    name="invoice_create",
    toolset="invoicing",
    schema={
        "name": "invoice_create",
        "description": "Create an invoice for a customer. Specify items as a list of {name, quantity, price} where price is in cents.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string", "description": "Customer full name"},
                "customer_email": {"type": "string", "description": "Customer email address"},
                "items": {
                    "type": "array",
                    "description": "Line items: [{name, quantity, price}] where price is in cents (e.g. 50000 = $500.00)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "quantity": {"type": "integer"},
                            "price": {"type": "integer"},
                        },
                    },
                },
                "due_date": {"type": "string", "description": "Due date YYYY-MM-DD (default: 30 days from today)"},
                "notes": {"type": "string", "description": "Optional notes on the invoice"},
            },
            "required": ["customer_name", "customer_email", "items"],
        },
    },
    handler=lambda args, **kw: invoice_create(
        args["customer_name"], args["customer_email"], args["items"],
        args.get("due_date", ""), args.get("notes", "")
    ),
    check_fn=_check_invoicing,
    requires_env=["CRATER_BASE_URL", "CRATER_API_TOKEN"],
    emoji="🧾",
)

registry.register(
    name="invoice_send",
    toolset="invoicing",
    schema={
        "name": "invoice_send",
        "description": "Email an invoice to the customer.",
        "parameters": {
            "type": "object",
            "properties": {
                "invoice_id": {"type": "string", "description": "Crater invoice ID"},
                "message": {"type": "string", "description": "Optional message to include with the invoice"},
            },
            "required": ["invoice_id"],
        },
    },
    handler=lambda args, **kw: invoice_send(args["invoice_id"], args.get("message", "")),
    check_fn=_check_invoicing,
    requires_env=["CRATER_BASE_URL", "CRATER_API_TOKEN"],
    emoji="🧾",
)

registry.register(
    name="invoice_list",
    toolset="invoicing",
    schema={
        "name": "invoice_list",
        "description": "List invoices by status: UNPAID, PAID, DRAFT, or OVERDUE.",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Invoice status filter (UNPAID, PAID, DRAFT, OVERDUE)"},
                "limit": {"type": "integer", "description": "Max results (default 10)"},
            },
            "required": [],
        },
    },
    handler=lambda args, **kw: invoice_list(args.get("status", "UNPAID"), args.get("limit", 10)),
    check_fn=_check_invoicing,
    requires_env=["CRATER_BASE_URL", "CRATER_API_TOKEN"],
    emoji="🧾",
)

registry.register(
    name="estimate_create",
    toolset="invoicing",
    schema={
        "name": "estimate_create",
        "description": "Create a quote/estimate for a customer before the job starts.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string"},
                "customer_email": {"type": "string"},
                "items": {
                    "type": "array",
                    "description": "Line items: [{name, quantity, price}] where price is in cents",
                    "items": {"type": "object"},
                },
                "valid_days": {"type": "integer", "description": "Days the quote is valid for (default 30)"},
                "notes": {"type": "string"},
            },
            "required": ["customer_name", "customer_email", "items"],
        },
    },
    handler=lambda args, **kw: estimate_create(
        args["customer_name"], args["customer_email"], args["items"],
        args.get("valid_days", 30), args.get("notes", "")
    ),
    check_fn=_check_invoicing,
    requires_env=["CRATER_BASE_URL", "CRATER_API_TOKEN"],
    emoji="🧾",
)

registry.register(
    name="payment_record",
    toolset="invoicing",
    schema={
        "name": "payment_record",
        "description": "Record a payment received against an invoice.",
        "parameters": {
            "type": "object",
            "properties": {
                "invoice_id": {"type": "string"},
                "amount_cents": {"type": "integer", "description": "Amount in cents (e.g. 50000 = $500.00)"},
                "payment_method": {"type": "string", "description": "e.g. Bank Transfer, Cash, Stripe, PayPal"},
                "notes": {"type": "string"},
            },
            "required": ["invoice_id", "amount_cents"],
        },
    },
    handler=lambda args, **kw: payment_record(
        args["invoice_id"], args["amount_cents"],
        args.get("payment_method", "Bank Transfer"), args.get("notes", "")
    ),
    check_fn=_check_invoicing,
    requires_env=["CRATER_BASE_URL", "CRATER_API_TOKEN"],
    emoji="🧾",
)
