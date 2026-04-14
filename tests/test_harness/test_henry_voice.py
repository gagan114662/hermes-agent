# tests/test_harness/test_henry_voice.py
"""Tests for harness.henry_voice — evening report delivery system."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_update(employee: str, message: str, role: str = "outreach") -> dict:
    return {
        "employee": employee,
        "role": role,
        "message": message,
        "channel": "team",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# compile_daily_briefing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_compile_daily_briefing_groups_by_employee():
    from harness.henry_voice import compile_daily_briefing

    sample_updates = [
        _make_update("alex_outreach", "Sent 15 emails, got 3 replies"),
        _make_update("alex_outreach", "Updated prospect list with 20 new contacts"),
        _make_update("sarah_content", "Published 2 blog posts"),
        _make_update("henry", "Morning standup complete"),  # should be skipped
    ]

    with patch("gateway.team_chat.load_updates", return_value=sample_updates):
        briefing = await compile_daily_briefing(hours=24)

    assert briefing["total_actions"] == 3  # henry excluded
    assert "alex_outreach" in briefing["by_employee"]
    assert "sarah_content" in briefing["by_employee"]
    assert "henry" not in briefing["by_employee"]
    assert len(briefing["by_employee"]["alex_outreach"]) == 2
    assert "date" in briefing
    assert isinstance(briefing["wins"], list)
    assert isinstance(briefing["blockers"], list)
    assert isinstance(briefing["tomorrow_plan"], list)


@pytest.mark.asyncio
async def test_compile_daily_briefing_empty_updates():
    from harness.henry_voice import compile_daily_briefing

    with patch("gateway.team_chat.load_updates", return_value=[]):
        briefing = await compile_daily_briefing(hours=24)

    assert briefing["total_actions"] == 0
    assert briefing["by_employee"] == {}


# ---------------------------------------------------------------------------
# make_vapi_call
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_make_vapi_call_success(monkeypatch):
    from harness.henry_voice import make_vapi_call

    monkeypatch.setenv("VAPI_API_KEY", "test-key")
    monkeypatch.setenv("VAPI_PHONE_ID", "phone-123")
    monkeypatch.setenv("VAPI_ASSISTANT_ID", "asst-456")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "call-abc", "status": "queued"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    briefing = {
        "date": "Monday April 14",
        "total_actions": 5,
        "by_employee": {"alex_outreach": ["Sent 15 emails"]},
        "wins": [],
        "blockers": [],
        "tomorrow_plan": [],
    }

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await make_vapi_call("+14155552671", briefing)

    assert result["status"] == "initiated"
    assert result["call_id"] == "call-abc"
    assert result["duration_estimate"] > 0


@pytest.mark.asyncio
async def test_make_vapi_call_missing_credentials():
    from harness.henry_voice import make_vapi_call

    # No env vars set — should return error immediately
    with patch.dict("os.environ", {}, clear=True):
        result = await make_vapi_call("+14155552671", {})

    assert result["status"] == "error"
    assert "Missing Vapi credentials" in result["error"]
    assert result["call_id"] is None


@pytest.mark.asyncio
async def test_make_vapi_call_invalid_phone(monkeypatch):
    from harness.henry_voice import make_vapi_call

    monkeypatch.setenv("VAPI_API_KEY", "test-key")
    monkeypatch.setenv("VAPI_PHONE_ID", "phone-123")
    monkeypatch.setenv("VAPI_ASSISTANT_ID", "asst-456")

    result = await make_vapi_call("not-a-phone", {})
    assert result["status"] == "error"
    assert "Invalid phone number" in result["error"]


@pytest.mark.asyncio
async def test_make_vapi_call_normalises_national_number(monkeypatch):
    """A plain US national number should be converted to E.164 and the call attempted."""
    from harness.henry_voice import make_vapi_call
    import httpx

    monkeypatch.setenv("VAPI_API_KEY", "test-key")
    monkeypatch.setenv("VAPI_PHONE_ID", "phone-123")
    monkeypatch.setenv("VAPI_ASSISTANT_ID", "asst-456")

    mock_response = MagicMock()
    mock_response.json.return_value = {"id": "call-xyz", "status": "queued"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    briefing = {
        "date": "Monday April 14",
        "total_actions": 2,
        "by_employee": {},
        "wins": [],
        "blockers": [],
        "tomorrow_plan": [],
    }

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await make_vapi_call("415-555-2671", briefing)

    # Should normalise to +14155552671 and succeed
    assert result["status"] == "initiated"
    _, call_kwargs = mock_client.post.call_args
    customer_number = call_kwargs["json"]["customer"]["number"]
    assert customer_number.startswith("+1")


# ---------------------------------------------------------------------------
# send_telegram_briefing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_telegram_briefing_success(monkeypatch):
    from harness.henry_voice import send_telegram_briefing

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot-token-123")

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    briefing = {
        "date": "Monday April 14",
        "total_actions": 3,
        "by_employee": {"alex_outreach": ["Sent 15 emails"]},
        "wins": ["3 new leads"],
        "blockers": [],
        "tomorrow_plan": [],
    }

    with patch("httpx.AsyncClient", return_value=mock_client):
        ok = await send_telegram_briefing("12345678", briefing)

    assert ok is True
    mock_client.post.assert_called_once()
    _, call_kwargs = mock_client.post.call_args
    assert call_kwargs["json"]["chat_id"] == "12345678"
    assert "parse_mode" in call_kwargs["json"]


@pytest.mark.asyncio
async def test_send_telegram_briefing_no_token():
    from harness.henry_voice import send_telegram_briefing

    with patch.dict("os.environ", {}, clear=True):
        ok = await send_telegram_briefing("12345678", {})

    assert ok is False


# ---------------------------------------------------------------------------
# deliver_evening_report
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deliver_evening_report_vapi_first(monkeypatch):
    from harness.henry_voice import deliver_evening_report

    monkeypatch.setenv("VAPI_API_KEY", "key")
    monkeypatch.setenv("VAPI_PHONE_ID", "phone")
    monkeypatch.setenv("VAPI_ASSISTANT_ID", "asst")

    briefing = {
        "date": "Monday April 14",
        "total_actions": 5,
        "by_employee": {"alex": ["Did stuff"]},
        "wins": [],
        "blockers": [],
        "tomorrow_plan": [],
    }

    vapi_ok = {"status": "initiated", "call_id": "call-1", "duration_estimate": 90}

    with patch("harness.henry_voice.make_vapi_call", new=AsyncMock(return_value=vapi_ok)):
        result = await deliver_evening_report("+14155552671", briefing)

    assert result["method_used"] == "vapi_call"
    assert result["status"] == "delivered"


@pytest.mark.asyncio
async def test_deliver_evening_report_falls_back_to_telegram(monkeypatch, tmp_path):
    from harness.henry_voice import deliver_evening_report

    monkeypatch.setenv("VAPI_API_KEY", "key")
    monkeypatch.setenv("VAPI_PHONE_ID", "phone")
    monkeypatch.setenv("VAPI_ASSISTANT_ID", "asst")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_OWNER_ID", "987654")

    briefing = {
        "date": "Monday April 14",
        "total_actions": 2,
        "by_employee": {},
        "wins": [],
        "blockers": [],
        "tomorrow_plan": [],
    }

    vapi_fail = {"status": "error", "error": "API timeout", "call_id": None, "duration_estimate": 0}

    with (
        patch("harness.henry_voice.make_vapi_call", new=AsyncMock(return_value=vapi_fail)),
        patch("harness.henry_voice.send_telegram_briefing", new=AsyncMock(return_value=True)),
    ):
        result = await deliver_evening_report("+14155552671", briefing)

    assert result["method_used"] == "telegram"
    assert result["status"] == "delivered"


@pytest.mark.asyncio
async def test_deliver_evening_report_file_fallback(monkeypatch, tmp_path):
    from harness.henry_voice import deliver_evening_report

    # Patch _HERMES_HOME to a tmp dir so we don't write to the real home
    with (
        patch.dict("os.environ", {}, clear=True),
        patch("harness.henry_voice._HERMES_HOME", tmp_path),
    ):
        briefing = {
            "date": "Monday April 14",
            "total_actions": 0,
            "by_employee": {},
            "wins": [],
            "blockers": [],
            "tomorrow_plan": [],
        }
        result = await deliver_evening_report("+14155552671", briefing)

    assert result["method_used"] == "file"
    assert result["status"] == "saved"
    assert Path(result["detail"]["path"]).exists()


# ---------------------------------------------------------------------------
# Full evening_report() integration (HenryPM wired up)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_henry_evening_report_integration(tmp_path, monkeypatch):
    """HenryPM.evening_report() should call compile_daily_briefing + deliver + post_update."""
    from harness.henry import HenryPM
    from unittest.mock import AsyncMock, patch

    # Fake business profile
    bp = tmp_path / "business.yaml"
    bp.write_text("name: TestCo\n")

    # Stub out Employee.list_all to return empty
    with (
        patch("harness.employee.Employee.list_all", return_value=[]),
        patch(
            "harness.henry_voice.compile_daily_briefing",
            new=AsyncMock(return_value={
                "date": "Monday April 14",
                "total_actions": 4,
                "by_employee": {"alex": ["Sent emails"]},
                "wins": [],
                "blockers": [],
                "tomorrow_plan": [],
            }),
        ),
        patch(
            "harness.henry_voice.deliver_evening_report",
            new=AsyncMock(return_value={
                "method_used": "telegram",
                "status": "delivered",
                "delivered_at": "2026-04-14T17:00:00+00:00",
                "detail": {},
            }),
        ),
        patch("gateway.team_chat.post_update", return_value={}),
    ):
        henry = HenryPM(business_profile_path=bp, user_contact="+14155552671")
        result = await henry.evening_report()

    assert result["method_used"] == "telegram"
    assert result["status"] == "delivered"
