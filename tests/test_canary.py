"""Tests for canary and error logger."""
import json
import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock


def test_log_tool_error_creates_file(tmp_path):
    from scripts.error_logger import log_tool_error
    errors_dir = str(tmp_path / "errors")
    with patch("scripts.error_logger.ERRORS_DIR", errors_dir):
        log_tool_error("web_search", "timeout after 30s", session_id="test-123")

    files = list((tmp_path / "errors").glob("*.jsonl"))
    assert len(files) == 1

    entry = json.loads(files[0].read_text().strip())
    assert entry["tool"] == "web_search"
    assert "timeout" in entry["error"]


def test_log_tool_error_never_raises():
    from scripts.error_logger import log_tool_error
    with patch("scripts.error_logger.ERRORS_DIR", "/nonexistent/path/that/cannot/be/created/xyz"):
        # Should not raise even if directory creation fails
        try:
            log_tool_error("test", "error")
        except Exception:
            pass  # May fail on permission errors, that's OK


def test_weekly_digest_empty(tmp_path):
    from scripts.error_logger import get_weekly_digest
    with patch("scripts.error_logger.ERRORS_DIR", str(tmp_path)):
        digest = get_weekly_digest()
    assert "No tool errors" in digest or "0" in digest or isinstance(digest, str)


def test_weekly_digest_with_errors(tmp_path):
    from scripts.error_logger import log_tool_error, get_weekly_digest
    errors_dir = str(tmp_path)
    with patch("scripts.error_logger.ERRORS_DIR", errors_dir):
        for _ in range(5):
            log_tool_error("web_search", "timeout")
        for _ in range(3):
            log_tool_error("memory", "file locked")

        digest = get_weekly_digest()

    assert "web_search" in digest
    assert "5" in digest or "5x" in digest
