import json
import pytest
from datetime import datetime, timezone, timedelta
from scripts.morning_digest import (
    load_last_24h_actions,
    format_digest,
    send_digest,
)

@pytest.fixture
def sample_log(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    hermes_dir = tmp_path / ".hermes"
    hermes_dir.mkdir()
    now = datetime.now(timezone.utc)
    log = [
        {"action": "Replied to email from Maria G.", "timestamp": now.isoformat()},
        {"action": "Followed up with Jake Miller", "timestamp": now.isoformat()},
        {"action": "Added Reddit prospect from r/smallbusiness", "timestamp": (now - timedelta(hours=25)).isoformat()},
    ]
    (hermes_dir / "action_log.json").write_text(json.dumps(log))
    return log

def test_load_last_24h_filters_old(sample_log, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    recent = load_last_24h_actions()
    assert len(recent) == 2

def test_format_digest_has_summary(sample_log, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    actions = load_last_24h_actions()
    text = format_digest(actions)
    assert "✅" in text
    assert "Maria G." in text

def test_format_digest_empty():
    text = format_digest([])
    assert "quiet" in text.lower() or "nothing" in text.lower() or "all clear" in text.lower() or "watching" in text.lower()

def test_send_digest_calls_telegram(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_OWNER_ID", "12345")
    sent = []
    monkeypatch.setattr("scripts.morning_digest._telegram_send", lambda token, chat, text: sent.append(text))
    send_digest()
    assert len(sent) == 1
