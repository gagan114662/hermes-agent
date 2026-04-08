"""Tests for tools/environments/singularity.py — SingularityEnvironment helpers."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from tools.environments.singularity import (
    _ensure_singularity_available,
    _find_singularity_executable,
    _load_snapshots,
    _save_snapshots,
)


# ── _find_singularity_executable ──────────────────────────────────────────────

class TestFindSingularityExecutable:
    def test_prefers_apptainer(self):
        with patch("shutil.which", side_effect=lambda x: "/usr/bin/apptainer" if x == "apptainer" else None):
            result = _find_singularity_executable()
        assert result == "apptainer"

    def test_falls_back_to_singularity(self):
        with patch("shutil.which", side_effect=lambda x: "/usr/bin/singularity" if x == "singularity" else None):
            result = _find_singularity_executable()
        assert result == "singularity"

    def test_raises_when_neither_found(self):
        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="apptainer"):
                _find_singularity_executable()


# ── _ensure_singularity_available ─────────────────────────────────────────────

class TestEnsureSingularityAvailable:
    def test_returns_executable_on_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        with patch("tools.environments.singularity._find_singularity_executable", return_value="apptainer"), \
             patch("subprocess.run", return_value=mock_result):
            result = _ensure_singularity_available()
        assert result == "apptainer"

    def test_raises_on_nonzero_returncode(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error"
        with patch("tools.environments.singularity._find_singularity_executable", return_value="apptainer"), \
             patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="failed"):
                _ensure_singularity_available()

    def test_raises_on_timeout(self):
        with patch("tools.environments.singularity._find_singularity_executable", return_value="apptainer"), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired("apptainer", 10)):
            with pytest.raises(RuntimeError, match="timed out"):
                _ensure_singularity_available()

    def test_raises_on_file_not_found(self):
        with patch("tools.environments.singularity._find_singularity_executable", return_value="apptainer"), \
             patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="could not be executed"):
                _ensure_singularity_available()

    def test_raises_when_not_installed(self):
        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError):
                _ensure_singularity_available()


# ── snapshot helpers ──────────────────────────────────────────────────────────

class TestSingularitySnapshots:
    def test_load_returns_empty_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "tools.environments.singularity._SNAPSHOT_STORE",
            tmp_path / "missing.json",
        )
        assert _load_snapshots() == {}

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        store = tmp_path / "snaps.json"
        monkeypatch.setattr("tools.environments.singularity._SNAPSHOT_STORE", store)
        _save_snapshots({"task1": "overlay_path"})
        assert _load_snapshots() == {"task1": "overlay_path"}

    def test_load_returns_empty_on_corrupt_json(self, tmp_path, monkeypatch):
        store = tmp_path / "corrupt.json"
        store.write_text("{bad}")
        monkeypatch.setattr("tools.environments.singularity._SNAPSHOT_STORE", store)
        assert _load_snapshots() == {}
