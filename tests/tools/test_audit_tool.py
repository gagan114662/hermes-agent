"""Tests for tools/audit.py — thread-local audit context and record_tool_call."""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from tools.audit import (
    clear_audit_context,
    get_audit_context,
    recent_records,
    record_tool_call,
    set_audit_context,
    _scrub_args,
)


# ── Thread-local context ──────────────────────────────────────────────────────

class TestAuditContext:
    def setup_method(self):
        clear_audit_context()

    def teardown_method(self):
        clear_audit_context()

    def test_default_context_is_empty(self):
        ctx = get_audit_context()
        assert ctx["user_id"] == ""
        assert ctx["platform"] == ""
        assert ctx["session_id"] == ""

    def test_set_and_get_context(self):
        set_audit_context(user_id="alice", platform="telegram", session_id="sess123")
        ctx = get_audit_context()
        assert ctx["user_id"] == "alice"
        assert ctx["platform"] == "telegram"
        assert ctx["session_id"] == "sess123"

    def test_clear_resets_context(self):
        set_audit_context(user_id="alice", platform="telegram", session_id="s")
        clear_audit_context()
        ctx = get_audit_context()
        assert ctx["user_id"] == ""

    def test_context_is_thread_local(self):
        set_audit_context(user_id="main_thread", platform="test", session_id="s1")
        results = {}

        def _other_thread():
            ctx = get_audit_context()
            results["other"] = ctx["user_id"]

        t = threading.Thread(target=_other_thread)
        t.start()
        t.join()

        # Other thread should have empty context
        assert results["other"] == ""
        # Main thread unchanged
        assert get_audit_context()["user_id"] == "main_thread"

    def test_set_context_partial_fields(self):
        set_audit_context(user_id="bob", platform="discord", session_id="")
        ctx = get_audit_context()
        assert ctx["user_id"] == "bob"
        assert ctx["session_id"] == ""


# ── _scrub_args ───────────────────────────────────────────────────────────────

class TestScrubArgs:
    def test_redacts_password_key(self):
        args = {"password": "secret123", "username": "alice"}
        scrubbed = _scrub_args(args)
        assert "secret123" not in str(scrubbed["password"])
        assert scrubbed["username"] == "alice"

    def test_redacts_token_key(self):
        args = {"token": "bearer_abc", "action": "get"}
        scrubbed = _scrub_args(args)
        assert "bearer_abc" not in str(scrubbed["token"])

    def test_redacts_secret_key(self):
        args = {"api_secret": "shh", "model": "gpt-4"}
        scrubbed = _scrub_args(args)
        assert "shh" not in str(scrubbed["api_secret"])

    def test_does_not_redact_normal_keys(self):
        args = {"query": "search term", "limit": 10}
        scrubbed = _scrub_args(args)
        assert scrubbed["query"] == "search term"
        assert scrubbed["limit"] == 10

    def test_truncates_long_strings(self):
        args = {"text": "x" * 1000}
        scrubbed = _scrub_args(args)
        assert len(str(scrubbed["text"])) <= 510  # 500 + some tolerance

    def test_empty_args(self):
        assert _scrub_args({}) == {}

    def test_none_args(self):
        result = _scrub_args(None)
        assert result == {} or result is None

    def test_nested_non_string_values_preserved(self):
        args = {"count": 42, "flag": True}
        scrubbed = _scrub_args(args)
        assert scrubbed["count"] == 42
        assert scrubbed["flag"] is True


# ── record_tool_call ──────────────────────────────────────────────────────────

class TestRecordToolCall:
    def test_writes_to_audit_log(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        import tools.audit as audit_mod
        import importlib
        importlib.reload(audit_mod)

        audit_mod.record_tool_call(
            tool="web_search",
            args={"query": "test"},
            outcome="ok",
            duration_ms=150.0,
        )

        log_file = tmp_path / "logs" / "audit.jsonl"
        assert log_file.exists()
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) >= 1
        record = json.loads(lines[-1])
        assert record["tool"] == "web_search"
        assert record["outcome"] == "ok"

    def test_record_includes_error_field(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        import tools.audit as audit_mod
        import importlib
        importlib.reload(audit_mod)

        audit_mod.record_tool_call(
            tool="failing_tool",
            args={},
            outcome="error",
            duration_ms=5.0,
            error="Connection refused",
        )

        log_file = tmp_path / "logs" / "audit.jsonl"
        record = json.loads(log_file.read_text().strip().split("\n")[-1])
        assert record["error"] == "Connection refused"

    def test_record_includes_timestamp(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        (tmp_path / "logs").mkdir()
        import tools.audit as audit_mod
        import importlib
        importlib.reload(audit_mod)

        audit_mod.record_tool_call(tool="t", args={}, outcome="ok", duration_ms=1.0)

        log_file = tmp_path / "logs" / "audit.jsonl"
        record = json.loads(log_file.read_text().strip())
        assert "ts" in record

    def test_record_includes_duration(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        (tmp_path / "logs").mkdir()
        import tools.audit as audit_mod
        import importlib
        importlib.reload(audit_mod)

        audit_mod.record_tool_call(tool="t", args={}, outcome="ok", duration_ms=42.5)

        log_file = tmp_path / "logs" / "audit.jsonl"
        record = json.loads(log_file.read_text().strip())
        assert abs(record["duration_ms"] - 42.5) < 0.01

    def test_record_scrubs_sensitive_args(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        (tmp_path / "logs").mkdir()
        import tools.audit as audit_mod
        import importlib
        importlib.reload(audit_mod)

        audit_mod.record_tool_call(
            tool="login",
            args={"password": "supersecret", "username": "alice"},
            outcome="ok",
            duration_ms=1.0,
        )

        log_file = tmp_path / "logs" / "audit.jsonl"
        content = log_file.read_text()
        assert "supersecret" not in content


# ── recent_records ────────────────────────────────────────────────────────────

class TestRecentRecords:
    def test_returns_list(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        (tmp_path / "logs").mkdir()
        import tools.audit as audit_mod
        import importlib
        importlib.reload(audit_mod)

        result = audit_mod.recent_records(n=10)
        assert isinstance(result, list)

    def test_returns_empty_when_no_log(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        (tmp_path / "logs").mkdir(exist_ok=True)
        import tools.audit as audit_mod
        import importlib
        importlib.reload(audit_mod)

        result = audit_mod.recent_records(n=10)
        assert result == []

    def test_returns_recent_entries(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        import tools.audit as audit_mod
        import importlib
        importlib.reload(audit_mod)

        for i in range(5):
            audit_mod.record_tool_call(
                tool=f"tool_{i}", args={}, outcome="ok", duration_ms=float(i)
            )

        records = audit_mod.recent_records(n=5)
        assert len(records) == 5

    def test_respects_limit(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        import tools.audit as audit_mod
        import importlib
        importlib.reload(audit_mod)

        for i in range(10):
            audit_mod.record_tool_call(tool=f"t{i}", args={}, outcome="ok", duration_ms=1.0)

        records = audit_mod.recent_records(n=3)
        assert len(records) <= 3
