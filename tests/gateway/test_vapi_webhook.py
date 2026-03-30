"""Tests for Vapi inbound call webhook handler."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


SAMPLE_END_OF_CALL = {
    "message": {
        "type": "end-of-call-report",
        "call": {
            "id": "call_abc123",
            "customer": {"number": "+15105550100"},
            "duration": 90,
            "endedReason": "customer-ended-call",
        },
        "transcript": "AI: Hello, I'm Alex.\nCaller: Hi, I saw your ad. Is this real?",
        "summary": "Prospect interested. Asked about pricing. Follow up needed.",
        "recordingUrl": "",
    }
}


def test_parse_end_of_call_report():
    from gateway.platforms.vapi_webhook import parse_vapi_event
    result = parse_vapi_event(SAMPLE_END_OF_CALL)
    assert result is not None
    assert result["type"] == "end-of-call-report"
    assert result["caller"] == "+15105550100"
    assert result["duration"] == 90
    assert "Alex" in result["transcript"]
    assert "pricing" in result["summary"]


def test_parse_ignores_non_end_events():
    from gateway.platforms.vapi_webhook import parse_vapi_event
    result = parse_vapi_event({"message": {"type": "transcript", "text": "hello"}})
    assert result is None


def test_parse_ignores_missing_message():
    from gateway.platforms.vapi_webhook import parse_vapi_event
    assert parse_vapi_event({}) is None
    assert parse_vapi_event({"message": {}}) is None


def test_format_agent_prompt_contains_caller():
    from gateway.platforms.vapi_webhook import format_agent_prompt
    event = {
        "type": "end-of-call-report",
        "caller": "+15105550100",
        "duration": 90,
        "transcript": "AI: Hi\nCaller: interested in your product",
        "summary": "Caller asked about pricing.",
        "recording_url": "",
        "call_id": "call_abc123",
        "ended_reason": "customer-ended-call",
    }
    prompt = format_agent_prompt(event)
    assert "+15105550100" in prompt
    assert "crm_save" in prompt
    assert "crm_log" in prompt
    assert "send_message" in prompt


def test_format_agent_prompt_hot_lead_flag():
    from gateway.platforms.vapi_webhook import format_agent_prompt
    event = {
        "type": "end-of-call-report",
        "caller": "+15105550100",
        "duration": 90,
        "transcript": "I want to sign up now",
        "summary": "Caller ready to sign up.",
        "recording_url": "",
        "call_id": "call_abc123",
        "ended_reason": "customer-ended-call",
    }
    prompt = format_agent_prompt(event)
    assert "HOT LEAD" in prompt or "hot lead" in prompt.lower()


def test_format_agent_prompt_no_hot_flag_for_cold_call():
    from gateway.platforms.vapi_webhook import format_agent_prompt
    event = {
        "type": "end-of-call-report",
        "caller": "+15105550100",
        "duration": 10,
        "transcript": "AI: Hi. Caller: Wrong number.",
        "summary": "Wrong number call.",
        "recording_url": "",
        "call_id": "call_xyz",
        "ended_reason": "customer-ended-call",
    }
    prompt = format_agent_prompt(event)
    assert "HOT LEAD" not in prompt


def test_validate_secret_no_env(monkeypatch):
    monkeypatch.delenv("VAPI_WEBHOOK_SECRET", raising=False)
    from gateway.platforms import vapi_webhook
    import importlib; importlib.reload(vapi_webhook)
    assert vapi_webhook.validate_secret("anything") is True


def test_validate_secret_matches(monkeypatch):
    monkeypatch.setenv("VAPI_WEBHOOK_SECRET", "mysecret")
    from gateway.platforms import vapi_webhook
    import importlib; importlib.reload(vapi_webhook)
    assert vapi_webhook.validate_secret("mysecret") is True
    assert vapi_webhook.validate_secret("wrongsecret") is False
