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
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="hermes-control-plane")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _customers_path() -> Path:
    """Return path to ~/.hermes/customers.json, creating dirs as needed."""
    home = Path(os.environ.get("HOME", Path.home()))
    hermes_dir = home / ".hermes"
    hermes_dir.mkdir(parents=True, exist_ok=True)
    return hermes_dir / "customers.json"


def _load_customers() -> dict:
    path = _customers_path()
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {"customers": {}}
    return {"customers": {}}


def _save_customers(data: dict) -> None:
    import tempfile
    path = _customers_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write to temp file in same directory, then atomic rename
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        os.write(fd, json.dumps(data, indent=2).encode())
        os.close(fd)
        os.chmod(tmp, 0o600)  # owner-only permissions
        os.replace(tmp, path)
    except Exception:
        os.close(fd)
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


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

    # Persist — deduplicate by txn_id
    data = _load_customers()
    txn_id = customer["txn_id"]
    if txn_id in data["customers"]:
        logger.info("Duplicate IPN for txn %s — ignoring", txn_id)
        return {"status": "ok", "duplicate": True}

    data["customers"][txn_id] = {
        **customer,
        "status": "onboarding",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_customers(data)
    logger.info("New customer: %s (%s)", customer["name"].strip(), customer["email"])

    asyncio.create_task(_notify_customer(customer))
    asyncio.create_task(_notify_owner(customer))

    return Response(status_code=200)  # PayPal requires 200 OK


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("CONTROL_PLANE_PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
