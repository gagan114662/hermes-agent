"""Tests for control plane server — SQLite-backed, PayPal IPN, Sprint 3."""
import json
import sys
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed; install with: pip install 'hermes-agent[scale]'")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Avoid importing telegram at module level
sys.modules.setdefault("telegram", MagicMock())
sys.modules.setdefault("telegram.ext", MagicMock())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(tmp_path, monkeypatch, owner_id: str = ""):
    """Return a (started) TestClient with HOME isolated to tmp_path.

    Triggers the app lifespan so init_db() runs and the customers table exists.
    Pass owner_id to set TELEGRAM_OWNER_ID for admin endpoint tests.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_OWNER_ID", owner_id)
    (tmp_path / ".hermes").mkdir(parents=True, exist_ok=True)

    # Re-import so DB_PATH is recomputed under tmp_path
    import importlib
    import scripts.control_plane as cp_mod
    importlib.reload(cp_mod)

    from fastapi.testclient import TestClient
    client = TestClient(cp_mod.app)
    client.__enter__()   # triggers lifespan → init_db()
    return client, cp_mod


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health_endpoint(tmp_path, monkeypatch):
    client, _ = _make_client(tmp_path, monkeypatch)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# init_db
# ---------------------------------------------------------------------------

def test_init_db_creates_table(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()
    import importlib
    import scripts.control_plane as cp_mod
    importlib.reload(cp_mod)
    cp_mod.init_db()
    conn = sqlite3.connect(cp_mod.DB_PATH)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
    assert "customers" in tables


def test_init_db_migrates_json(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    hermes_dir = tmp_path / ".hermes"
    hermes_dir.mkdir()
    # Write legacy JSON
    legacy = {
        "customers": {
            "txn_001": {
                "email": "alice@example.com",
                "payer_id": "PAY1",
                "status": "onboarding",
                "created_at": "2024-01-01T00:00:00+00:00",
            }
        }
    }
    (hermes_dir / "customers.json").write_text(json.dumps(legacy))
    import importlib
    import scripts.control_plane as cp_mod
    importlib.reload(cp_mod)
    cp_mod.init_db()
    conn = sqlite3.connect(cp_mod.DB_PATH)
    rows = conn.execute("SELECT customer_id, email FROM customers").fetchall()
    conn.close()
    assert any(r[0] == "txn_001" and r[1] == "alice@example.com" for r in rows)
    # JSON should be renamed
    assert not (hermes_dir / "customers.json").exists()
    assert (hermes_dir / "customers.json.bak").exists()


# ---------------------------------------------------------------------------
# PayPal IPN
# ---------------------------------------------------------------------------

def test_paypal_ipn_rejects_non_paypal_ip(tmp_path, monkeypatch):
    client, _ = _make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/paypal-ipn",
        content=b"payment_status=Completed&txn_type=web_accept",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    # Non-PayPal IP (127.0.0.1 from TestClient) → 403
    assert resp.status_code == 403


def test_paypal_ipn_accepts_valid_ip(tmp_path, monkeypatch):
    client, cp_mod = _make_client(tmp_path, monkeypatch)

    with patch.object(cp_mod, "_verify_paypal_ipn", new=AsyncMock(return_value=True)), \
         patch.object(cp_mod, "is_paypal_ip", return_value=True):
        raw = (
            b"txn_type=web_accept&payment_status=Completed"
            b"&payer_email=buyer@example.com&payer_id=PAY1"
            b"&txn_id=TXN001&mc_gross=299.00"
            b"&first_name=Alice&last_name=Smith"
        )
        resp = client.post(
            "/paypal-ipn",
            content=raw,
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
    assert resp.status_code == 200
    # Verify persisted to SQLite
    conn = sqlite3.connect(cp_mod.DB_PATH)
    row = conn.execute("SELECT email, status FROM customers WHERE customer_id='TXN001'").fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "buyer@example.com"
    assert row[1] == "onboarding"


def test_paypal_ipn_deduplicates(tmp_path, monkeypatch):
    client, cp_mod = _make_client(tmp_path, monkeypatch)

    with patch.object(cp_mod, "_verify_paypal_ipn", new=AsyncMock(return_value=True)), \
         patch.object(cp_mod, "is_paypal_ip", return_value=True):
        raw = (
            b"txn_type=web_accept&payment_status=Completed"
            b"&payer_email=dup@example.com&payer_id=PAY2"
            b"&txn_id=TXN_DUP&mc_gross=299.00"
        )
        client.post("/paypal-ipn", content=raw, headers={"content-type": "application/x-www-form-urlencoded"})
        resp2 = client.post("/paypal-ipn", content=raw, headers={"content-type": "application/x-www-form-urlencoded"})
    data = resp2.json()
    assert data.get("duplicate") is True
    conn = sqlite3.connect(cp_mod.DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM customers WHERE customer_id='TXN_DUP'").fetchone()[0]
    conn.close()
    assert count == 1


# ---------------------------------------------------------------------------
# /internal/customer-ready
# ---------------------------------------------------------------------------

def test_customer_ready_updates_db(tmp_path, monkeypatch):
    client, cp_mod = _make_client(tmp_path, monkeypatch)
    # Seed a customer
    conn = sqlite3.connect(cp_mod.DB_PATH)
    conn.execute(
        "INSERT INTO customers (customer_id, email, status, created_at, updated_at) VALUES (?,?,?,?,?)",
        ("CUST1", "test@example.com", "onboarding", "2024-01-01", "2024-01-01"),
    )
    conn.commit()
    conn.close()

    resp = client.post(
        "/internal/customer-ready",
        json={"customer_id": "CUST1", "ip": "1.2.3.4", "phone": "+14155551234", "telegram_chat_id": "99999"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    conn = sqlite3.connect(cp_mod.DB_PATH)
    row = conn.execute("SELECT ip, phone, status FROM customers WHERE customer_id='CUST1'").fetchone()
    conn.close()
    assert row[0] == "1.2.3.4"
    assert row[1] == "+14155551234"
    assert row[2] == "active"


# ---------------------------------------------------------------------------
# /admin
# ---------------------------------------------------------------------------

def test_admin_forbidden_wrong_owner(tmp_path, monkeypatch):
    client, _ = _make_client(tmp_path, monkeypatch, owner_id="12345")
    resp = client.post("/admin", json={"owner_id": "99999", "command": "/customers"})
    assert resp.status_code == 403


def test_admin_customers_command(tmp_path, monkeypatch):
    client, cp_mod = _make_client(tmp_path, monkeypatch, owner_id="12345")
    # Seed data
    conn = sqlite3.connect(cp_mod.DB_PATH)
    conn.execute(
        "INSERT INTO customers (customer_id, email, status, phone, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        ("C1", "jane@example.com", "active", "+1415", "2024-01-01", "2024-01-01"),
    )
    conn.commit()
    conn.close()
    resp = client.post("/admin", json={"owner_id": "12345", "command": "/customers"})
    assert resp.status_code == 200
    assert "jane@example.com" in resp.json()["result"]


def test_admin_revenue_command(tmp_path, monkeypatch):
    client, cp_mod = _make_client(tmp_path, monkeypatch, owner_id="12345")
    # Seed 2 active customers
    conn = sqlite3.connect(cp_mod.DB_PATH)
    for i in range(2):
        conn.execute(
            "INSERT INTO customers (customer_id, email, status, created_at, updated_at) VALUES (?,?,?,?,?)",
            (f"REV{i}", f"c{i}@example.com", "active", "2024-01-01", "2024-01-01"),
        )
    conn.commit()
    conn.close()
    resp = client.post("/admin", json={"owner_id": "12345", "command": "/revenue"})
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert "2 active" in result
    assert "$598" in result


def test_admin_unknown_command(tmp_path, monkeypatch):
    client, _ = _make_client(tmp_path, monkeypatch, owner_id="42")
    resp = client.post("/admin", json={"owner_id": "42", "command": "/unknown"})
    assert resp.status_code == 200
    assert "Unknown" in resp.json()["result"]


# ---------------------------------------------------------------------------
# parse_paypal_ipn
# ---------------------------------------------------------------------------

def test_parse_paypal_ipn_completed():
    import importlib
    import scripts.control_plane as cp_mod
    importlib.reload(cp_mod)
    params = {
        "txn_type": "web_accept",
        "payment_status": "Completed",
        "payer_email": "buyer@example.com",
        "payer_id": "PAY1",
        "txn_id": "TXN1",
        "mc_gross": "299.00",
        "first_name": "Bob",
        "last_name": "Jones",
    }
    result = cp_mod.parse_paypal_ipn(params)
    assert result is not None
    assert result["email"] == "buyer@example.com"
    assert result["txn_id"] == "TXN1"


def test_parse_paypal_ipn_non_completed():
    import importlib
    import scripts.control_plane as cp_mod
    importlib.reload(cp_mod)
    params = {"txn_type": "web_accept", "payment_status": "Pending"}
    assert cp_mod.parse_paypal_ipn(params) is None


# ---------------------------------------------------------------------------
# is_paypal_ip
# ---------------------------------------------------------------------------

def test_is_paypal_ip_known_range():
    import importlib
    import scripts.control_plane as cp_mod
    importlib.reload(cp_mod)
    # 64.4.240.1 is within 64.4.240.0/21
    assert cp_mod.is_paypal_ip("64.4.240.1") is True


def test_is_paypal_ip_unknown():
    import importlib
    import scripts.control_plane as cp_mod
    importlib.reload(cp_mod)
    assert cp_mod.is_paypal_ip("127.0.0.1") is False


def test_is_paypal_ip_invalid():
    import importlib
    import scripts.control_plane as cp_mod
    importlib.reload(cp_mod)
    assert cp_mod.is_paypal_ip("not-an-ip") is False
