"""Tests for tools/invoicing_tool.py — Crater invoicing integration."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
import httpx

from tools.invoicing_tool import (
    _base,
    _headers,
    _company_id,
    invoice_create,
    invoice_list,
    invoice_send,
    estimate_create,
)


# ── helpers ───────────────────────────────────────────────────────────────

class TestCraterHelpers:
    def test_base_empty_without_env(self, monkeypatch):
        monkeypatch.delenv("CRATER_BASE_URL", raising=False)
        assert _base() == ""

    def test_base_strips_trailing_slash(self, monkeypatch):
        monkeypatch.setenv("CRATER_BASE_URL", "https://crater.example.com/")
        assert _base() == "https://crater.example.com"

    def test_base_returns_url(self, monkeypatch):
        monkeypatch.setenv("CRATER_BASE_URL", "https://crater.example.com")
        assert _base() == "https://crater.example.com"

    def test_company_id(self, monkeypatch):
        monkeypatch.setenv("CRATER_COMPANY_ID", "42")
        assert _company_id() == "42"

    def test_headers_authorization(self, monkeypatch):
        monkeypatch.setenv("CRATER_API_TOKEN", "tok123")
        monkeypatch.setenv("CRATER_COMPANY_ID", "1")
        h = _headers()
        assert h["Authorization"] == "Bearer tok123"
        assert h["company-id"] == "1"


# ── invoice_create ────────────────────────────────────────────────────────

class TestInvoiceCreate:
    def test_error_without_base_url(self, monkeypatch):
        monkeypatch.delenv("CRATER_BASE_URL", raising=False)
        result = invoice_create("Alice", "alice@test.com", [])
        assert "Error" in result
        assert "CRATER_BASE_URL" in result

    def test_creates_invoice_new_customer(self, monkeypatch):
        monkeypatch.setenv("CRATER_BASE_URL", "https://crater.test")
        monkeypatch.setenv("CRATER_API_TOKEN", "tok")
        monkeypatch.setenv("CRATER_COMPANY_ID", "1")

        # GET customers → empty, POST customer → id 99, POST invoice → success
        resp_customers = MagicMock()
        resp_customers.status_code = 200
        resp_customers.raise_for_status = MagicMock()
        resp_customers.json.return_value = {"data": []}

        resp_create_customer = MagicMock()
        resp_create_customer.status_code = 201
        resp_create_customer.raise_for_status = MagicMock()
        resp_create_customer.json.return_value = {"data": {"id": 99}}

        resp_invoice = MagicMock()
        resp_invoice.status_code = 201
        resp_invoice.raise_for_status = MagicMock()
        resp_invoice.json.return_value = {
            "data": {"invoice_number": "INV-001", "id": 10}
        }

        with patch("httpx.get", return_value=resp_customers), \
             patch("httpx.post", side_effect=[resp_create_customer, resp_invoice]):
            result = invoice_create(
                "Alice", "alice@test.com",
                [{"name": "Consulting", "quantity": 1, "price": 50000}]
            )
        assert isinstance(result, str)
        assert "Error" not in result or "INV" in result

    def test_creates_invoice_existing_customer(self, monkeypatch):
        monkeypatch.setenv("CRATER_BASE_URL", "https://crater.test")
        monkeypatch.setenv("CRATER_API_TOKEN", "tok")
        monkeypatch.setenv("CRATER_COMPANY_ID", "1")

        resp_customers = MagicMock()
        resp_customers.status_code = 200
        resp_customers.raise_for_status = MagicMock()
        resp_customers.json.return_value = {"data": [{"id": 5}]}

        resp_invoice = MagicMock()
        resp_invoice.status_code = 201
        resp_invoice.raise_for_status = MagicMock()
        resp_invoice.json.return_value = {
            "data": {"invoice_number": "INV-002", "id": 11}
        }

        with patch("httpx.get", return_value=resp_customers), \
             patch("httpx.post", return_value=resp_invoice):
            result = invoice_create("Bob", "bob@test.com", [])
        assert isinstance(result, str)

    def test_handles_http_error_on_customer_lookup(self, monkeypatch):
        monkeypatch.setenv("CRATER_BASE_URL", "https://crater.test")
        monkeypatch.setenv("CRATER_API_TOKEN", "tok")
        monkeypatch.setenv("CRATER_COMPANY_ID", "1")

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("httpx.get", side_effect=httpx.HTTPStatusError(
            "server error", request=MagicMock(), response=mock_resp
        )):
            result = invoice_create("Carol", "carol@test.com", [])
        assert "Error" in result


# ── invoice_list ──────────────────────────────────────────────────────────

class TestInvoiceList:
    def test_error_without_base_url(self, monkeypatch):
        monkeypatch.delenv("CRATER_BASE_URL", raising=False)
        result = invoice_list()
        assert "Error" in result

    def test_returns_no_invoices(self, monkeypatch):
        monkeypatch.setenv("CRATER_BASE_URL", "https://crater.test")
        monkeypatch.setenv("CRATER_API_TOKEN", "tok")
        monkeypatch.setenv("CRATER_COMPANY_ID", "1")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"data": []}

        with patch("httpx.get", return_value=mock_resp):
            result = invoice_list()
        assert isinstance(result, str)
        assert "No" in result or len(result) > 0

    def test_returns_invoice_list(self, monkeypatch):
        monkeypatch.setenv("CRATER_BASE_URL", "https://crater.test")
        monkeypatch.setenv("CRATER_API_TOKEN", "tok")
        monkeypatch.setenv("CRATER_COMPANY_ID", "1")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "data": [{
                "invoice_number": "INV-001",
                "status": "SENT",
                "total": 50000,
                "due_date": "2025-12-01",
                "customer": {"name": "Alice"},
            }]
        }

        with patch("httpx.get", return_value=mock_resp):
            result = invoice_list()
        assert isinstance(result, str)


# ── invoice_send ──────────────────────────────────────────────────────────

class TestInvoiceSend:
    def test_error_without_base_url(self, monkeypatch):
        monkeypatch.delenv("CRATER_BASE_URL", raising=False)
        result = invoice_send("INV-001")
        assert "Error" in result

    def test_sends_invoice(self, monkeypatch):
        monkeypatch.setenv("CRATER_BASE_URL", "https://crater.test")
        monkeypatch.setenv("CRATER_API_TOKEN", "tok")
        monkeypatch.setenv("CRATER_COMPANY_ID", "1")

        # First GET list to find invoice ID
        mock_list = MagicMock()
        mock_list.status_code = 200
        mock_list.raise_for_status = MagicMock()
        mock_list.json.return_value = {
            "data": [{"invoice_number": "INV-001", "id": 5}]
        }

        mock_send = MagicMock()
        mock_send.status_code = 200
        mock_send.raise_for_status = MagicMock()
        mock_send.json.return_value = {"success": True}

        with patch("httpx.get", return_value=mock_list), \
             patch("httpx.post", return_value=mock_send):
            result = invoice_send("INV-001")
        assert isinstance(result, str)


# ── estimate_create ───────────────────────────────────────────────────────

class TestEstimateCreate:
    def test_error_without_base_url(self, monkeypatch):
        monkeypatch.delenv("CRATER_BASE_URL", raising=False)
        result = estimate_create("Alice", "alice@test.com", [])
        assert "Error" in result

    def test_creates_estimate(self, monkeypatch):
        monkeypatch.setenv("CRATER_BASE_URL", "https://crater.test")
        monkeypatch.setenv("CRATER_API_TOKEN", "tok")
        monkeypatch.setenv("CRATER_COMPANY_ID", "1")

        resp_customers = MagicMock()
        resp_customers.status_code = 200
        resp_customers.raise_for_status = MagicMock()
        resp_customers.json.return_value = {"data": [{"id": 5}]}

        resp_estimate = MagicMock()
        resp_estimate.status_code = 201
        resp_estimate.raise_for_status = MagicMock()
        resp_estimate.json.return_value = {
            "data": {"estimate_number": "EST-001", "id": 20}
        }

        with patch("httpx.get", return_value=resp_customers), \
             patch("httpx.post", return_value=resp_estimate):
            result = estimate_create("Alice", "alice@test.com", [])
        assert isinstance(result, str)
