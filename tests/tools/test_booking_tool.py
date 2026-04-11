"""Tests for tools/booking_tool.py — Cal.com booking integration."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
import httpx

from tools.booking_tool import (
    _headers,
    _api_key,
    booking_create_link,
    booking_list_slots,
    booking_list_upcoming,
    booking_cancel,
    booking_reschedule,
)


# ── helpers ───────────────────────────────────────────────────────────────

class TestApiKey:
    def test_returns_empty_without_env(self, monkeypatch):
        monkeypatch.delenv("CALCOM_API_KEY", raising=False)
        assert _api_key() == ""

    def test_returns_key_from_env(self, monkeypatch):
        monkeypatch.setenv("CALCOM_API_KEY", "cal_test_123")
        assert _api_key() == "cal_test_123"


class TestHeaders:
    def test_authorization_header(self, monkeypatch):
        monkeypatch.setenv("CALCOM_API_KEY", "mykey")
        h = _headers()
        assert h["Authorization"] == "Bearer mykey"

    def test_content_type_json(self, monkeypatch):
        monkeypatch.setenv("CALCOM_API_KEY", "x")
        assert _headers()["Content-Type"] == "application/json"


# ── booking_create_link ───────────────────────────────────────────────────

class TestBookingCreateLink:
    def test_error_without_event_id(self, monkeypatch):
        monkeypatch.delenv("CALCOM_EVENT_ID", raising=False)
        result = booking_create_link(event_type_id="")
        assert "Error" in result

    def test_uses_env_event_id(self, monkeypatch):
        monkeypatch.setenv("CALCOM_EVENT_ID", "42")
        monkeypatch.setenv("CALCOM_API_KEY", "key")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "event_type": {"slug": "meeting", "users": [{"username": "alice"}]}
        }
        with patch("httpx.get", return_value=mock_resp):
            result = booking_create_link()
        assert "cal.com/alice/meeting" in result or "Booking link" in result

    def test_returns_booking_link(self, monkeypatch):
        monkeypatch.setenv("CALCOM_API_KEY", "key")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "event_type": {"slug": "30min", "users": [{"username": "bob"}]}
        }
        with patch("httpx.get", return_value=mock_resp):
            result = booking_create_link(event_type_id="99")
        assert "Booking link" in result
        assert "bob/30min" in result

    def test_handles_http_error(self, monkeypatch):
        monkeypatch.setenv("CALCOM_API_KEY", "key")
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch("httpx.get", side_effect=httpx.HTTPStatusError(
            "not found", request=MagicMock(), response=mock_resp
        )):
            result = booking_create_link(event_type_id="99")
        assert "Error" in result

    def test_handles_network_error(self, monkeypatch):
        monkeypatch.setenv("CALCOM_API_KEY", "key")
        with patch("httpx.get", side_effect=httpx.RequestError("timeout")):
            result = booking_create_link(event_type_id="99")
        assert "Error" in result


# ── booking_list_slots ────────────────────────────────────────────────────

class TestBookingListSlots:
    def test_error_without_event_id(self, monkeypatch):
        monkeypatch.delenv("CALCOM_EVENT_ID", raising=False)
        result = booking_list_slots("2025-12-01", event_type_id="")
        assert "Error" in result

    def test_error_without_date(self, monkeypatch):
        monkeypatch.setenv("CALCOM_EVENT_ID", "1")
        result = booking_list_slots("", event_type_id="1")
        assert "Error" in result

    def test_returns_no_slots_message(self, monkeypatch):
        monkeypatch.setenv("CALCOM_API_KEY", "key")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"slots": {}}
        with patch("httpx.get", return_value=mock_resp):
            result = booking_list_slots("2025-12-01", event_type_id="1")
        assert "No available slots" in result

    def test_returns_available_slots(self, monkeypatch):
        monkeypatch.setenv("CALCOM_API_KEY", "key")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "slots": {"2025-12-01": [{"time": "2025-12-01T09:00:00Z"}, {"time": "2025-12-01T10:00:00Z"}]}
        }
        with patch("httpx.get", return_value=mock_resp):
            result = booking_list_slots("2025-12-01", event_type_id="1")
        assert "Available slots" in result
        assert "09:00" in result or "2025-12-01" in result


# ── booking_list_upcoming ─────────────────────────────────────────────────

class TestBookingListUpcoming:
    def test_returns_no_bookings_message(self, monkeypatch):
        monkeypatch.setenv("CALCOM_API_KEY", "key")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"bookings": []}
        with patch("httpx.get", return_value=mock_resp):
            result = booking_list_upcoming()
        assert "No upcoming bookings" in result

    def test_returns_booking_list(self, monkeypatch):
        monkeypatch.setenv("CALCOM_API_KEY", "key")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "bookings": [{
                "id": "b1",
                "title": "Discovery Call",
                "startTime": "2025-12-01T10:00:00Z",
                "attendees": [{"name": "Alice"}]
            }]
        }
        with patch("httpx.get", return_value=mock_resp):
            result = booking_list_upcoming()
        assert "Discovery Call" in result or "Upcoming" in result

    def test_handles_http_error(self, monkeypatch):
        monkeypatch.setenv("CALCOM_API_KEY", "key")
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        with patch("httpx.get", side_effect=httpx.HTTPStatusError(
            "unauthorized", request=MagicMock(), response=mock_resp
        )):
            result = booking_list_upcoming()
        assert "Error" in result


# ── booking_cancel ────────────────────────────────────────────────────────

class TestBookingCancel:
    def test_error_without_booking_id(self):
        result = booking_cancel("")
        assert "Error" in result

    def test_cancels_booking(self, monkeypatch):
        monkeypatch.setenv("CALCOM_API_KEY", "key")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        with patch("httpx.delete", return_value=mock_resp):
            result = booking_cancel("booking123")
        assert "booking123" in result and "cancelled" in result.lower()

    def test_handles_http_error(self, monkeypatch):
        monkeypatch.setenv("CALCOM_API_KEY", "key")
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch("httpx.delete", side_effect=httpx.HTTPStatusError(
            "not found", request=MagicMock(), response=mock_resp
        )):
            result = booking_cancel("bad_id")
        assert "Error" in result


# ── booking_reschedule ────────────────────────────────────────────────────

class TestBookingReschedule:
    def test_error_without_required_args(self):
        result = booking_reschedule("", "")
        assert "Error" in result

    def test_error_without_booking_id(self):
        result = booking_reschedule("", "2025-12-01T10:00:00Z")
        assert "Error" in result

    def test_reschedules_booking(self, monkeypatch):
        monkeypatch.setenv("CALCOM_API_KEY", "key")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        with patch("httpx.patch", return_value=mock_resp):
            result = booking_reschedule("b123", "2025-12-02T14:00:00Z")
        assert "b123" in result and "rescheduled" in result.lower()

    def test_handles_http_error(self, monkeypatch):
        monkeypatch.setenv("CALCOM_API_KEY", "key")
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("httpx.patch", side_effect=httpx.HTTPStatusError(
            "server error", request=MagicMock(), response=mock_resp
        )):
            result = booking_reschedule("b123", "2025-12-02T14:00:00Z")
        assert "Error" in result
