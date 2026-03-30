#!/usr/bin/env python3
"""
Control Plane Server — runs on the VPS and handles the customer lifecycle.

Env vars:
    STRIPE_WEBHOOK_SECRET   — Stripe webhook signing secret
    TELEGRAM_BOT_TOKEN      — Bot token used to notify customers / owner
    TELEGRAM_OWNER_ID       — Telegram user ID of the owner to notify
    CONTROL_PLANE_PORT      — Port to bind (default 8080)
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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
# Stripe signature verification
# ---------------------------------------------------------------------------

def _verify_stripe_signature(payload: bytes, sig_header: str, secret: str) -> bool:
    """Verify Stripe webhook signature with replay protection (±300 s)."""
    try:
        parts = {}
        for item in sig_header.split(","):
            k, _, v = item.partition("=")
            parts.setdefault(k, v)

        timestamp = parts.get("t", "")
        v1 = parts.get("v1", "")
        if not timestamp or not v1:
            return False

        ts_int = int(timestamp)
        now = int(time.time())
        if abs(now - ts_int) > 300:
            return False

        signed_payload = f"{timestamp}.{payload.decode()}"
        computed = hmac.new(
            secret.encode(),
            signed_payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(v1, computed)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Stripe event parsing
# ---------------------------------------------------------------------------

def parse_checkout_session(event: dict) -> Optional[dict]:
    """
    Parse a Stripe event and return a customer dict if it is a
    checkout.session.completed event; otherwise return None.
    """
    if event.get("type") != "checkout.session.completed":
        return None

    obj = event.get("data", {}).get("object", {})
    details = obj.get("customer_details", {})

    email = obj.get("customer_email") or details.get("email", "")
    name = details.get("name", "")
    phone = details.get("phone", "")
    telegram_id = obj.get("metadata", {}).get("telegram_id", "")
    stripe_session_id = obj.get("id", "")
    amount = obj.get("amount_total", 0)

    return {
        "email": email,
        "name": name,
        "phone": phone,
        "telegram_id": telegram_id,
        "stripe_session_id": stripe_session_id,
        "amount": amount,
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


@app.post("/stripe-webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    if not secret:
        raise HTTPException(status_code=500, detail="Webhook secret not configured")
    if not _verify_stripe_signature(payload, sig, secret):
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        event = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc

    customer = parse_checkout_session(event)
    if not customer:
        return Response(status_code=200)

    # Persist customer record
    data = _load_customers()
    session_id = customer["stripe_session_id"]

    # Duplicate session guard — skip re-processing
    if session_id in data["customers"]:
        logger.info("Duplicate webhook for session %s — ignoring", session_id)
        return {"status": "ok", "duplicate": True}

    data["customers"][session_id] = {
        **customer,
        "status": "onboarding",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_customers(data)
    logger.info("New customer recorded: %s (%s)", customer["name"], customer["email"])

    # Fire-and-forget Telegram notifications (errors are logged, not raised)
    asyncio.create_task(_notify_customer(customer))
    asyncio.create_task(_notify_owner(customer))

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("CONTROL_PLANE_PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
