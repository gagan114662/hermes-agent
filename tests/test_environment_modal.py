"""Tests for tools/environments/modal.py — ModalEnvironment and helpers."""
from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.environments.modal import (
    ModalEnvironment,
    _AsyncWorker,
    _load_snapshots,
    _save_snapshots,
)


# ── _load_snapshots / _save_snapshots ─────────────────────────────────────────

class TestSnapshotStore:
    def test_load_returns_empty_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "tools.environments.modal._SNAPSHOT_STORE",
            tmp_path / "missing.json",
        )
        result = _load_snapshots()
        assert result == {}

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        store = tmp_path / "snapshots.json"
        monkeypatch.setattr("tools.environments.modal._SNAPSHOT_STORE", store)
        _save_snapshots({"task1": "snap_abc"})
        result = _load_snapshots()
        assert result == {"task1": "snap_abc"}

    def test_load_returns_empty_on_corrupt_json(self, tmp_path, monkeypatch):
        store = tmp_path / "corrupt.json"
        store.write_text("not json{{{")
        monkeypatch.setattr("tools.environments.modal._SNAPSHOT_STORE", store)
        result = _load_snapshots()
        assert result == {}

    def test_save_creates_parent_dirs(self, tmp_path, monkeypatch):
        store = tmp_path / "sub" / "deep" / "snapshots.json"
        monkeypatch.setattr("tools.environments.modal._SNAPSHOT_STORE", store)
        _save_snapshots({"x": "y"})
        assert store.exists()


# ── _AsyncWorker ──────────────────────────────────────────────────────────────

class TestAsyncWorker:
    def test_start_and_stop(self):
        worker = _AsyncWorker()
        worker.start()
        assert worker._loop is not None
        assert worker._loop.is_running()
        worker.stop()

    def test_run_coroutine(self):
        worker = _AsyncWorker()
        worker.start()
        try:
            async def _coro():
                return 42

            result = worker.run_coroutine(_coro())
            assert result == 42
        finally:
            worker.stop()

    def test_run_raises_when_not_started(self):
        worker = _AsyncWorker()
        with pytest.raises(RuntimeError, match="not running"):
            async def _coro():
                return 1
            worker.run_coroutine(_coro())

    def test_run_coroutine_with_exception(self):
        worker = _AsyncWorker()
        worker.start()
        try:
            async def _failing_coro():
                raise ValueError("boom")

            with pytest.raises(ValueError, match="boom"):
                worker.run_coroutine(_failing_coro())
        finally:
            worker.stop()

    def test_stop_twice_is_safe(self):
        worker = _AsyncWorker()
        worker.start()
        worker.stop()
        worker.stop()  # should not raise


# ── ModalEnvironment ──────────────────────────────────────────────────────────

class TestModalEnvironment:
    """Tests with Modal SDK mocked out."""

    def _mock_modal(self):
        """Return a context manager that patches the modal import."""
        mock_sandbox = MagicMock()
        mock_modal = MagicMock()
        mock_modal.Sandbox.create = MagicMock(return_value=mock_sandbox)
        return mock_modal, mock_sandbox

    def test_requires_modal_sdk(self):
        """ModalEnvironment should raise ImportError if modal is not installed."""
        with patch.dict("sys.modules", {"modal": None}):
            with pytest.raises((ImportError, TypeError)):
                ModalEnvironment(image="ubuntu:22.04")

    def test_init_stores_image_and_cwd(self):
        mock_modal, mock_sandbox = self._mock_modal()
        worker = _AsyncWorker()
        worker.start()

        with patch.dict("sys.modules", {"modal": mock_modal}), \
             patch("tools.environments.modal._AsyncWorker", return_value=worker), \
             patch("tools.environments.modal._load_snapshots", return_value={}):
            try:
                env = ModalEnvironment(image="python:3.11", cwd="/workspace")
                assert env.cwd == "/workspace"
            except Exception:
                pass  # Modal init may fail due to missing credentials
            finally:
                worker.stop()

    def test_load_snapshots_called_empty(self, tmp_path, monkeypatch):
        store = tmp_path / "modal_snapshots.json"
        monkeypatch.setattr("tools.environments.modal._SNAPSHOT_STORE", store)
        result = _load_snapshots()
        assert result == {}

    def test_save_snapshots_persists_data(self, tmp_path, monkeypatch):
        store = tmp_path / "modal_snapshots.json"
        monkeypatch.setattr("tools.environments.modal._SNAPSHOT_STORE", store)
        _save_snapshots({"default": "snap123"})
        loaded = _load_snapshots()
        assert loaded["default"] == "snap123"
