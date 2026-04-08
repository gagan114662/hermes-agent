"""Tests for tools/crm_tool.py — CRM contacts, deals, and interactions."""
from __future__ import annotations

import json
import importlib
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers: redirect CRM file path to tmp_path
# ---------------------------------------------------------------------------

def _setup_crm(tmp_path, monkeypatch):
    """Point crm_path to a temp dir and reload the module."""
    crm_dir = tmp_path / ".hermes"
    crm_dir.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    import tools.crm_tool as crm_mod
    importlib.reload(crm_mod)
    return crm_mod


# ── _crm_path / _load / _save ─────────────────────────────────────────────

class TestCrmHelpers:
    def test_load_returns_empty_contacts_when_missing(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        result = mod._load()
        assert result == {"contacts": {}}

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        data = {"contacts": {"bob": {"name": "Bob"}}}
        mod._save(data)
        loaded = mod._load()
        assert loaded["contacts"]["bob"]["name"] == "Bob"

    def test_load_raises_on_corrupt_json(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        crm_file = Path(mod._crm_path())
        crm_file.parent.mkdir(parents=True, exist_ok=True)
        crm_file.write_text("{not valid json}")
        with pytest.raises(json.JSONDecodeError):
            mod._load()

    def test_now_returns_iso_string(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        ts = mod._now()
        assert "T" in ts  # ISO 8601 format

    def test_find_contact_by_phone(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        data = {"contacts": {"+1234": {"name": "Alice", "phone": "+1234", "email": ""}}}
        key, contact = mod._find_contact(data, "+1234")
        assert key == "+1234"
        assert contact["name"] == "Alice"

    def test_find_contact_by_email_field(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        data = {"contacts": {"alice@test.com": {"name": "Alice", "phone": "", "email": "alice@test.com"}}}
        key, contact = mod._find_contact(data, "alice@test.com")
        assert key == "alice@test.com"

    def test_find_contact_not_found(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        key, contact = mod._find_contact({"contacts": {}}, "+9999")
        assert key is None
        assert contact is None


# ── crm_save_fn ───────────────────────────────────────────────────────────

class TestCrmSaveFn:
    def test_requires_phone_or_email(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        result = mod.crm_save_fn(name="Alice", phone="", email="")
        assert "Error" in result

    def test_creates_new_contact_with_phone(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        result = mod.crm_save_fn(name="Alice", phone="+1555000001")
        assert "Alice" in result
        assert "saved" in result

    def test_creates_new_contact_with_email(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        result = mod.crm_save_fn(name="Bob", email="bob@test.com")
        assert "Bob" in result

    def test_updates_existing_contact(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        mod.crm_save_fn(name="Alice", phone="+1555000001")
        result = mod.crm_save_fn(name="Alice Updated", phone="+1555000001")
        assert "updated" in result

    def test_persists_to_file(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        mod.crm_save_fn(name="Carol", phone="+1555000002", notes="test note")
        data = mod._load()
        assert "+1555000002" in data["contacts"]
        assert data["contacts"]["+1555000002"]["name"] == "Carol"

    def test_status_default_is_lead(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        mod.crm_save_fn(name="Dave", phone="+1555000003")
        data = mod._load()
        assert data["contacts"]["+1555000003"]["status"] == "lead"

    def test_custom_status(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        mod.crm_save_fn(name="Eve", phone="+1555000004", status="customer")
        data = mod._load()
        assert data["contacts"]["+1555000004"]["status"] == "customer"


# ── crm_log_fn ────────────────────────────────────────────────────────────

class TestCrmLogFn:
    def _create_contact(self, mod, phone="+1555999001"):
        mod.crm_save_fn(name="TestUser", phone=phone)
        return phone

    def test_error_for_unknown_phone(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        result = mod.crm_log_fn("+9999", "call", "test")
        assert "Error" in result

    def test_logs_interaction(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        phone = self._create_contact(mod)
        result = mod.crm_log_fn(phone, "call", "Had a great call")
        assert "Had a great call" in result or phone in result or "TestUser" in result

    def test_interaction_saved_to_file(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        phone = self._create_contact(mod)
        mod.crm_log_fn(phone, "sms", "Sent follow-up")
        data = mod._load()
        interactions = data["contacts"][phone]["interactions"]
        assert len(interactions) == 1
        assert interactions[0]["channel"] == "sms"
        assert interactions[0]["summary"] == "Sent follow-up"

    def test_multiple_interactions_accumulate(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        phone = self._create_contact(mod)
        mod.crm_log_fn(phone, "call", "First call")
        mod.crm_log_fn(phone, "email", "Sent proposal")
        data = mod._load()
        assert len(data["contacts"][phone]["interactions"]) == 2


# ── crm_find_fn ───────────────────────────────────────────────────────────

class TestCrmFindFn:
    def test_returns_no_matches_message(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        result = mod.crm_find_fn("nonexistent")
        assert "No contacts" in result

    def test_finds_by_name(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        mod.crm_save_fn(name="Alice Wonder", phone="+1555001001")
        result = mod.crm_find_fn("Alice")
        assert "Alice Wonder" in result

    def test_finds_by_phone(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        mod.crm_save_fn(name="Bob", phone="+1555002002")
        result = mod.crm_find_fn("+1555002002")
        assert "Bob" in result

    def test_finds_by_email(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        mod.crm_save_fn(name="Carol", email="carol@acme.com")
        result = mod.crm_find_fn("carol@acme.com")
        assert "Carol" in result

    def test_finds_by_status(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        mod.crm_save_fn(name="Dave", phone="+1555003003", status="customer")
        result = mod.crm_find_fn("customer")
        assert "Dave" in result

    def test_case_insensitive_search(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        mod.crm_save_fn(name="Eve Johnson", phone="+1555004004")
        result = mod.crm_find_fn("eve")
        assert "Eve Johnson" in result


# ── crm_deal_fn ───────────────────────────────────────────────────────────

class TestCrmDealFn:
    def _create_contact(self, mod, phone="+1555888001"):
        mod.crm_save_fn(name="DealContact", phone=phone)
        return phone

    def test_error_for_unknown_contact(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        result = mod.crm_deal_fn("+9999", "Website Deal")
        assert "Error" in result

    def test_adds_new_deal(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        phone = self._create_contact(mod)
        result = mod.crm_deal_fn(phone, "Website Project", value=5000.0)
        assert "added" in result
        assert "Website Project" in result

    def test_deal_saved_to_file(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        phone = self._create_contact(mod)
        mod.crm_deal_fn(phone, "SEO Deal", value=1000.0, status="open")
        data = mod._load()
        deals = data["contacts"][phone]["deals"]
        assert len(deals) == 1
        assert deals[0]["title"] == "SEO Deal"
        assert deals[0]["value"] == 1000.0

    def test_updates_existing_deal(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        phone = self._create_contact(mod)
        mod.crm_deal_fn(phone, "Big Deal", value=5000.0)
        result = mod.crm_deal_fn(phone, "Big Deal", value=7500.0, status="won")
        assert "updated" in result
        data = mod._load()
        deals = data["contacts"][phone]["deals"]
        assert len(deals) == 1  # Still one deal, updated not duplicated
        assert deals[0]["value"] == 7500.0
        assert deals[0]["status"] == "won"

    def test_deal_value_in_output(self, tmp_path, monkeypatch):
        mod = _setup_crm(tmp_path, monkeypatch)
        phone = self._create_contact(mod)
        result = mod.crm_deal_fn(phone, "Audit", value=2500.0)
        assert "2500" in result
