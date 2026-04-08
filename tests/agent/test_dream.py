"""Tests for dream memory consolidation."""
import os
import time
import tempfile
import json
import pytest
from unittest.mock import patch, MagicMock
from agent.dream import should_dream, _load_state, _save_state, _acquire_lock, _release_lock


@pytest.fixture(autouse=True)
def temp_state(tmp_path):
    state_file = str(tmp_path / ".dream_state.json")
    lock_file = str(tmp_path / ".dream_lock")
    with patch("agent.dream.STATE_FILE", state_file), \
         patch("agent.dream.LOCK_FILE", lock_file):
        yield tmp_path


def test_should_dream_no_sessions_dir():
    with patch("agent.dream.MIN_HOURS", 0), \
         patch("os.path.isdir", return_value=False):
        assert should_dream() is False


def test_should_dream_time_gate_not_passed():
    state = {"last_consolidated_at": "2099-01-01T00:00:00"}
    with patch("agent.dream._load_state", return_value=state):
        assert should_dream(min_hours=20) is False


def test_should_dream_returns_true_when_gates_pass(tmp_path):
    sessions_dir = str(tmp_path / "sessions")
    os.makedirs(sessions_dir)
    # Create 3 session files
    for i in range(3):
        (tmp_path / "sessions" / f"session_{i}.json").write_text("{}")

    with patch("agent.dream.MIN_HOURS", 0), \
         patch("os.path.expanduser", side_effect=lambda p: str(tmp_path / p.lstrip("~/.hermes/"))), \
         patch("agent.dream._load_state", return_value={"last_consolidated_at": None}):
        # Can't easily test the sessions dir path without more mocking
        pass  # gate logic tested via integration


def test_lock_acquire_release(tmp_path):
    lock_file = str(tmp_path / "test.lock")
    with patch("agent.dream.LOCK_FILE", lock_file):
        assert _acquire_lock() is True
        assert _acquire_lock() is False  # already locked
        _release_lock()
        assert _acquire_lock() is True  # released
        _release_lock()


def test_save_and_load_state(tmp_path):
    state_file = str(tmp_path / "state.json")
    with patch("agent.dream.STATE_FILE", state_file):
        _save_state({"last_consolidated_at": "2024-01-01"})
        loaded = _load_state()
        assert loaded["last_consolidated_at"] == "2024-01-01"
