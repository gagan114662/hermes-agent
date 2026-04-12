"""Tests for control plane server."""
import json
import sys
import time
import hashlib
import hmac
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Avoid importing telegram at module level
sys.modules.setdefault('telegram', MagicMock())
sys.modules.setdefault('telegram.ext', MagicMock())


def _stripe_sig(payload: bytes, secret: str) -> str:
    timestamp = str(int(time.time()))
    signed = f"{timestamp}.{payload.decode()}"
    sig = hmac.new(secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig}"


def test_health_endpoint():
    from fastapi.testclient import TestClient
    from scripts.control_plane import app
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_stripe_webhook_rejects_bad_signature(tmp_path, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test123")
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()
    from fastapi.testclient import TestClient
    from scripts.control_plane import app
    client = TestClient(app)
    payload = json.dumps({"type": "checkout.session.completed"}).encode()
    resp = client.post(
        "/stripe-webhook",
        content=payload,
        headers={"stripe-signature": "t=0,v1=badsig", "content-type": "application/json"},
    )
    assert resp.status_code == 400


def test_stripe_webhook_accepts_valid_signature(tmp_path, monkeypatch):
    secret = "whsec_test123"
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", secret)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_OWNER_ID", "")
    monkeypatch.setenv("ONBOARDING_BOT_TOKEN", "")
    (tmp_path / ".hermes").mkdir()
    payload = json.dumps({"type": "payment_intent.created"}).encode()
    sig = _stripe_sig(payload, secret)
    from fastapi.testclient import TestClient
    from scripts.control_plane import app
    client = TestClient(app)
    resp = client.post(
        "/stripe-webhook",
        content=payload,
        headers={"stripe-signature": sig, "content-type": "application/json"},
    )
    assert resp.status_code == 200


def test_stripe_webhook_rejects_missing_secret(tmp_path, monkeypatch):
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()
    payload = json.dumps({"type": "checkout.session.completed"}).encode()
    from fastapi.testclient import TestClient
    from scripts.control_plane import app
    client = TestClient(app)
    resp = client.post(
        "/stripe-webhook",
        content=payload,
        headers={"stripe-signature": "t=0,v1=fake", "content-type": "application/json"},
    )
    assert resp.status_code == 500


def test_parse_checkout_session():
    from scripts.control_plane import parse_checkout_session
    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_123",
                "customer_email": "test@example.com",
                "customer_details": {"name": "Test User", "phone": "+14155551234"},
                "metadata": {"telegram_id": "123456"},
                "amount_total": 29900,
            }
        }
    }
    result = parse_checkout_session(event)
    assert result["email"] == "test@example.com"
    assert result["name"] == "Test User"
    assert result["telegram_id"] == "123456"
    assert result["stripe_session_id"] == "cs_test_123"


def test_parse_checkout_session_wrong_type():
    from scripts.control_plane import parse_checkout_session
    assert parse_checkout_session({"type": "payment_intent.created"}) is None
