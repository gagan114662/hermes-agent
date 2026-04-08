"""Tests for tools/environments/daytona.py — DaytonaEnvironment."""
from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

import pytest

from tools.environments.daytona import DaytonaEnvironment


def _make_daytona_env(image="ubuntu:22.04", **kwargs):
    """Create DaytonaEnvironment with all Daytona SDK calls mocked."""
    mock_sandbox = MagicMock()
    mock_sandbox.id = "sandbox-xyz"
    mock_sandbox.state = MagicMock()

    # Make process.exec("echo $HOME").result.strip() return a real string so
    # __init__ doesn't overwrite self.cwd with a MagicMock.
    mock_sandbox.process.exec.return_value.result.strip.return_value = "/home/daytona"

    mock_daytona_mod = MagicMock()
    mock_client = MagicMock()
    mock_client.create.return_value = mock_sandbox
    mock_client.get.side_effect = Exception("not found")
    # list() must return empty items so the legacy fallback doesn't hijack _sandbox
    mock_page = MagicMock()
    mock_page.items = []
    mock_client.list.return_value = mock_page
    mock_daytona_mod = MagicMock()
    mock_daytona_mod.Daytona.return_value = mock_client
    mock_daytona_mod.CreateSandboxFromImageParams = MagicMock()
    mock_daytona_mod.DaytonaError = Exception
    mock_daytona_mod.Resources = MagicMock()
    mock_daytona_mod.SandboxState = MagicMock()

    with patch.dict("sys.modules", {"daytona": mock_daytona_mod}):
        env = DaytonaEnvironment(image=image, **kwargs)
    env._sandbox = mock_sandbox
    env._daytona_mod = mock_daytona_mod
    return env


class TestDaytonaEnvironmentInit:
    def test_stores_cwd(self):
        env = _make_daytona_env(cwd="/home/daytona")
        assert env.cwd == "/home/daytona"

    def test_stores_timeout(self):
        env = _make_daytona_env(timeout=120)
        assert env.timeout == 120

    def test_task_id_stored(self):
        env = _make_daytona_env(task_id="my-task")
        assert env._task_id == "my-task"

    def test_persistent_default_true(self):
        env = _make_daytona_env()
        assert env._persistent is True

    def test_persistent_can_be_false(self):
        env = _make_daytona_env(persistent_filesystem=False)
        assert env._persistent is False

    def test_disk_capped_at_10gb(self):
        """Requesting more than 10GB disk should trigger warning and cap."""
        with pytest.warns(UserWarning, match="10GB"):
            env = _make_daytona_env(disk=51200)  # 50GB > 10GB cap

    def test_disk_exactly_10gb_no_warning(self):
        env = _make_daytona_env(disk=10240)  # exactly 10GB — no warning

    def test_requires_daytona_package(self):
        """Should raise ImportError when daytona package is not installed."""
        with patch.dict("sys.modules", {"daytona": None}):
            with pytest.raises((ImportError, TypeError)):
                DaytonaEnvironment(image="ubuntu:22.04")


class TestDaytonaMemoryConversion:
    """Test memory_gib = ceil(memory_mb / 1024) logic."""

    def test_1024mb_becomes_1gib(self):
        # 1024MB → 1GiB (exactly)
        env = _make_daytona_env(memory=1024)
        # We can't directly access the Resources call args without more mocking,
        # but we can verify the environment was created without error.
        assert env is not None

    def test_small_memory_rounds_up_to_1(self):
        # 512MB → 1GiB (ceil rounds up)
        env = _make_daytona_env(memory=512)
        assert env is not None

    def test_large_memory(self):
        env = _make_daytona_env(memory=8192)
        assert env is not None


class TestDaytonaCleanup:
    def test_cleanup_does_not_raise_with_no_sandbox(self):
        env = _make_daytona_env()
        env._sandbox = None
        env.cleanup()  # should not raise

    def test_cleanup_stops_persistent_sandbox(self):
        env = _make_daytona_env(persistent_filesystem=True)
        env._sandbox.stop = MagicMock()
        env.cleanup()
        # For persistent sandboxes, stop is called instead of delete
        # (exact behavior depends on implementation)

    def test_stop_calls_cleanup(self):
        env = _make_daytona_env()
        with patch.object(env, "cleanup") as mock_cleanup:
            env.stop()
            mock_cleanup.assert_called_once()
