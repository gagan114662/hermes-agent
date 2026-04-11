#!/usr/bin/env python3
"""
Control Plane Server — runs on the VPS and handles the customer lifecycle.

Env vars:
    PAYPAL_WEBHOOK_ID       — PayPal webhook ID (from PayPal developer dashboard)
    TELEGRAM_BOT_TOKEN      — Bot token used to notify customers / owner
    TELEGRAM_OWNER_ID       — Telegram user ID of the owner to notify
    CONTROL_PLANE_PORT      — Port to bind (default 8080)
"""
import asyncio
import ipaddress
import json
import logging
import os
import sqlite3
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SQLite setup
# ---------------------------------------------------------------------------

DB_PATH = Path(os.environ.get("HOME", Path.home())) / ".hermes" / "customers.db"


def init_db() -> None:
    """Initialize SQLite DB and migrate from JSON if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            customer_id TEXT PRIMARY KEY,
            telegram_chat_id TEXT,
            paypal_payer_id TEXT,
            email TEXT,
            ip TEXT,
            phone TEXT,
            status TEXT DEFAULT 'onboarding',
            created_at TEXT,
            updated_at TEXT
        )
    """)
    conn.commit()
    # Migrate from JSON if exists
    json_path = DB_PATH.parent / "customers.json"
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text())
            for cid, c in data.get("customers", {}).items():
                conn.execute(
                    "INSERT OR IGNORE INTO customers "
                    "(customer_id, email, paypal_payer_id, status, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        cid,
                        c.get("email", ""),
                        c.get("payer_id", ""),
                        c.get("status", "onboarding"),
                        c.get("created_at", ""),
                        c.get("created_at", ""),
                    ),
                )
            conn.commit()
            json_path.rename(json_path.with_suffix(".json.bak"))
            logger.info("Migrated customers.json → customers.db")
        except Exception as exc:
            logger.warning("JSON migration failed (non-fatal): %s", exc)
    conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="hermes-control-plane", lifespan=lifespan)


# ---------------------------------------------------------------------------
# PayPal IP allowlist
# ---------------------------------------------------------------------------

PAYPAL_IP_RANGES = [
    ipaddress.ip_network("64.4.240.0/21"),
    ipaddress.ip_network("212.112.232.0/21"),
    ipaddress.ip_network("173.0.80.0/20"),
]


def is_paypal_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return any(ip in net for net in PAYPAL_IP_RANGES)
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# PayPal IPN verification
# ---------------------------------------------------------------------------

async def _verify_paypal_ipn(raw_body: bytes) -> bool:
    """Verify PayPal IPN by posting back to PayPal with cmd=_notify-validate."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://ipnpb.paypal.com/cgi-bin/webscr",
                content=b"cmd=_notify-validate&" + raw_body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            return resp.text == "VERIFIED"
    except Exception as exc:
        logger.warning("PayPal IPN verification error: %s", exc)
        return False


def parse_paypal_ipn(params: dict) -> Optional[dict]:
    """
    Parse a PayPal IPN POST and return a customer dict for completed
    subscription payments. Returns None for other payment types.
    """
    # Accept: subscr_payment (recurring charge) or web_accept (one-time)
    txn_type = params.get("txn_type", "")
    payment_status = params.get("payment_status", "")

    if txn_type not in ("subscr_payment", "web_accept") or payment_status != "Completed":
        return None

    return {
        "email": params.get("payer_email", ""),
        "name": params.get("first_name", "") + " " + params.get("last_name", ""),
        "phone": params.get("contact_phone", ""),
        "telegram_id": params.get("custom", ""),  # pass telegram_id in PayPal custom field
        "txn_id": params.get("txn_id", ""),
        "subscr_id": params.get("subscr_id", ""),
        "amount": params.get("mc_gross", "0"),
        "payer_id": params.get("payer_id", ""),
    }


# ---------------------------------------------------------------------------
# Telegram notification helpers (fire-and-forget)
# ---------------------------------------------------------------------------

async def _send_telegram(bot_token: str, chat_id: str, text: str) -> None:
    """Send a Telegram message; log errors but never raise."""
    if not bot_token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={"chat_id": chat_id, "text": text})
            if resp.status_code != 200:
                logger.warning("Telegram send failed: %s %s", resp.status_code, resp.text)
    except Exception as exc:
        logger.warning("Telegram send error: %s", exc)


async def _notify_customer(customer: dict) -> None:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    telegram_id = customer.get("telegram_id", "")
    if not telegram_id:
        return
    name = customer.get("name", "there")
    text = (
        f"👋 Hi {name}! Payment confirmed — I'm setting up your AI employee. "
        "Send /start to begin your onboarding interview (takes 2 minutes)."
    )
    await _send_telegram(bot_token, telegram_id, text)


async def _notify_owner(customer: dict) -> None:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    owner_id = os.environ.get("TELEGRAM_OWNER_ID", "")
    if not owner_id:
        return
    name = customer.get("name", "")
    email = customer.get("email", "")
    text = f"🎉 New customer: {name} ({email}) — onboarding started!"
    await _send_telegram(bot_token, owner_id, text)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "service": "hermes-control-plane"}


@app.post("/paypal-ipn")
async def paypal_ipn(request: Request):
    """Receive PayPal IPN notifications for new subscriptions."""
    # PayPal IP allowlist check
    client_ip = request.client.host if request.client else ""
    if not is_paypal_ip(client_ip):
        logger.warning("Rejected PayPal IPN from non-PayPal IP: %s", client_ip)
        raise HTTPException(status_code=403, detail="Forbidden")

    raw_body = await request.body()

    # Verify with PayPal
    if not await _verify_paypal_ipn(raw_body):
        logger.warning("PayPal IPN verification failed")
        raise HTTPException(status_code=400, detail="IPN verification failed")

    # Parse form-encoded params
    params = {k: v[0] for k, v in parse_qs(raw_body.decode()).items()}
    logger.info("PayPal IPN: txn_type=%s status=%s email=%s",
                params.get("txn_type"), params.get("payment_status"), params.get("payer_email"))

    customer = parse_paypal_ipn(params)
    if not customer:
        return Response(status_code=200)  # Not a completed payment, ignore

    # Persist to SQLite — deduplicate by txn_id (used as customer_id)
    txn_id = customer["txn_id"]
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    existing = conn.execute(
        "SELECT customer_id FROM customers WHERE customer_id=?", (txn_id,)
    ).fetchone()
    if existing:
        conn.close()
        logger.info("Duplicate IPN for txn %s — ignoring", txn_id)
        return {"status": "ok", "duplicate": True}

    conn.execute(
        "INSERT INTO customers (customer_id, email, paypal_payer_id, telegram_chat_id, status, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            txn_id,
            customer.get("email", ""),
            customer.get("payer_id", ""),
            customer.get("telegram_id", ""),
            "onboarding",
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    logger.info("New customer: %s (%s)", customer["name"].strip(), customer["email"])

    asyncio.create_task(_notify_customer(customer))
    asyncio.create_task(_notify_owner(customer))

    return Response(status_code=200)  # PayPal requires 200 OK


@app.post("/internal/customer-ready")
async def customer_ready(request: Request) -> dict:
    body = await request.json()
    customer_id = body.get("customer_id", "")
    ip = body.get("ip", "")
    phone = body.get("phone", "")
    telegram_chat_id = body.get("telegram_chat_id", "")
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE customers SET ip=?, phone=?, telegram_chat_id=?, status='active', updated_at=? WHERE customer_id=?",
        (ip, phone, telegram_chat_id, now, customer_id),
    )
    conn.commit()
    conn.close()
    # Notify customer via Telegram
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if bot_token and telegram_chat_id:
        msg = (
            f"🎉 Your AI employee is ready!\n\n"
            f"📞 Phone: {phone}\n\n"
            f"Start sending it tasks via @hermes114bot"
        )
        try:
            urllib.request.urlopen(
                f"https://api.telegram.org/bot{bot_token}/sendMessage"
                f"?chat_id={urllib.parse.quote(str(telegram_chat_id))}"
                f"&text={urllib.parse.quote(msg)}",
                timeout=10,
            )
        except Exception as exc:
            logger.warning("Telegram notify failed in customer-ready: %s", exc)
    return {"ok": True}


@app.post("/admin")
async def admin(request: Request) -> dict:
    body = await request.json()
    if str(body.get("owner_id")) != os.environ.get("TELEGRAM_OWNER_ID", ""):
        raise HTTPException(status_code=403, detail="Forbidden")
    command = body.get("command", "").strip()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if command == "/customers":
        rows = conn.execute(
            "SELECT customer_id, email, status, phone, created_at FROM customers ORDER BY created_at DESC"
        ).fetchall()
        conn.close()
        lines = [
            f"{r['customer_id']} | {r['email']} | {r['status']} | {r['phone']}"
            for r in rows
        ]
        return {"result": "\n".join(lines) or "No customers yet"}
    elif command == "/revenue":
        count = conn.execute(
            "SELECT COUNT(*) FROM customers WHERE status='active'"
        ).fetchone()[0]
        conn.close()
        return {"result": f"{count} active customers — ${count * 299}/mo MRR"}
    conn.close()
    return {"result": f"Unknown command: {command}"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_checkout_session(event: dict):
    """Parse a Stripe event and return a customer dict for checkout.session.completed."""
    if event.get("type") != "checkout.session.completed":
        return None
    obj = event.get("data", {}).get("object", {})
    details = obj.get("customer_details", {})
    return {
        "email": obj.get("customer_email") or details.get("email", ""),
        "name": details.get("name", ""),
        "phone": details.get("phone", ""),
        "telegram_id": obj.get("metadata", {}).get("telegram_id", ""),
        "stripe_session_id": obj.get("id", ""),
        "amount": obj.get("amount_total", 0),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("CONTROL_PLANE_PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
