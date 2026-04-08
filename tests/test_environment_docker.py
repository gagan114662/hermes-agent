"""Tests for tools/environments/docker.py — DockerEnvironment and helpers."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from tools.environments.docker import (
    DockerEnvironment,
    _ensure_docker_available,
    _load_hermes_env_vars,
    _normalize_forward_env_names,
    find_docker,
)


# ── _normalize_forward_env_names ──────────────────────────────────────────────

class TestNormalizeForwardEnvNames:
    def test_empty_list(self):
        assert _normalize_forward_env_names([]) == []

    def test_none_input(self):
        assert _normalize_forward_env_names(None) == []

    def test_valid_names(self):
        result = _normalize_forward_env_names(["FOO", "BAR_BAZ"])
        assert result == ["FOO", "BAR_BAZ"]

    def test_deduplicates(self):
        result = _normalize_forward_env_names(["FOO", "FOO", "BAR"])
        assert result == ["FOO", "BAR"]

    def test_strips_whitespace(self):
        result = _normalize_forward_env_names(["  FOO  "])
        assert result == ["FOO"]

    def test_rejects_invalid_names(self):
        result = _normalize_forward_env_names(["123invalid", "valid_one"])
        assert "123invalid" not in result
        assert "valid_one" in result

    def test_rejects_empty_string(self):
        result = _normalize_forward_env_names(["", "  "])
        assert result == []

    def test_rejects_non_string(self):
        result = _normalize_forward_env_names([42, "VALID"])
        assert result == ["VALID"]

    def test_underscore_prefix_valid(self):
        result = _normalize_forward_env_names(["_PRIVATE"])
        assert "_PRIVATE" in result


# ── _load_hermes_env_vars ─────────────────────────────────────────────────────

class TestLoadHermesEnvVars:
    def test_returns_dict(self):
        with patch("hermes_cli.config.load_env", return_value={"FOO": "bar"}):
            result = _load_hermes_env_vars()
        assert result == {"FOO": "bar"}

    def test_returns_empty_on_import_error(self):
        with patch("hermes_cli.config.load_env", side_effect=ImportError):
            result = _load_hermes_env_vars()
        assert result == {}

    def test_returns_empty_on_any_exception(self):
        with patch("hermes_cli.config.load_env", side_effect=RuntimeError("fail")):
            result = _load_hermes_env_vars()
        assert result == {}


# ── find_docker ───────────────────────────────────────────────────────────────

class TestFindDocker:
    def test_returns_string_or_none(self):
        result = find_docker()
        assert result is None or isinstance(result, str)

    def test_returns_which_when_available(self):
        import tools.environments.docker as docker_mod
        docker_mod._docker_executable = None  # reset cache
        with patch("shutil.which", return_value="/usr/bin/docker"):
            result = find_docker()
        assert result == "/usr/bin/docker"

    def test_returns_none_when_not_found(self):
        import tools.environments.docker as docker_mod
        docker_mod._docker_executable = None
        with patch("shutil.which", return_value=None), \
             patch("os.path.isfile", return_value=False):
            result = find_docker()
        assert result is None

    def test_caches_result(self):
        import tools.environments.docker as docker_mod
        docker_mod._docker_executable = "/cached/docker"
        result = find_docker()
        assert result == "/cached/docker"
        docker_mod._docker_executable = None  # reset


# ── _ensure_docker_available ──────────────────────────────────────────────────

class TestEnsureDockerAvailable:
    def test_raises_when_docker_not_found(self):
        with patch("tools.environments.docker.find_docker", return_value=None):
            with pytest.raises(RuntimeError, match="Docker executable not found"):
                _ensure_docker_available()

    def test_raises_when_version_times_out(self):
        with patch("tools.environments.docker.find_docker", return_value="/usr/bin/docker"), \
             patch("subprocess.run", side_effect=subprocess.TimeoutExpired("docker", 5)):
            with pytest.raises(RuntimeError, match="not responding"):
                _ensure_docker_available()

    def test_raises_when_version_fails(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "error"
        with patch("tools.environments.docker.find_docker", return_value="/usr/bin/docker"), \
             patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="docker version.*failed"):
                _ensure_docker_available()

    def test_raises_when_file_not_found(self):
        with patch("tools.environments.docker.find_docker", return_value="/usr/bin/docker"), \
             patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="could not be executed"):
                _ensure_docker_available()

    def test_passes_when_version_succeeds(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("tools.environments.docker.find_docker", return_value="/usr/bin/docker"), \
             patch("subprocess.run", return_value=mock_result):
            _ensure_docker_available()  # should not raise


# ── DockerEnvironment ─────────────────────────────────────────────────────────

class TestDockerEnvironment:
    """Tests that mock Docker calls so they run without Docker installed."""

    def _make_env(self, image="ubuntu:22.04", **kwargs):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "container123\n"
        mock_result.stderr = ""

        with patch("tools.environments.docker._ensure_docker_available"), \
             patch("tools.environments.docker.find_docker", return_value="/usr/bin/docker"), \
             patch("subprocess.run", return_value=mock_result):
            return DockerEnvironment(image=image, **kwargs)

    def test_init_sets_image(self):
        env = self._make_env()
        assert env._base_image == "ubuntu:22.04"

    def test_tilde_cwd_converted_to_root(self):
        env = self._make_env(cwd="~")
        assert env.cwd == "/root"

    def test_forward_env_normalized(self):
        env = self._make_env(forward_env=["MY_KEY", "MY_KEY", "123bad"])
        assert "MY_KEY" in env._forward_env
        assert "123bad" not in env._forward_env
        assert env._forward_env.count("MY_KEY") == 1

    def test_cleanup_stops_container(self):
        env = self._make_env()
        env._container_id = "abc123"
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            env.cleanup()
        # Should have called docker rm
        calls = [str(c) for c in mock_run.call_args_list]
        assert any("abc123" in str(c) for c in calls)

    def test_cleanup_when_no_container(self):
        env = self._make_env()
        env._container_id = None
        env.cleanup()  # should not raise

    def test_execute_runs_docker_exec(self):
        env = self._make_env()
        env._container_id = "abc123"

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "hello\n"

        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout.__iter__ = lambda _: iter(["hello\n"])
            mock_proc.stdout.close = MagicMock()
            mock_proc.stdin = MagicMock()
            mock_proc.poll.return_value = 0
            mock_popen.return_value = mock_proc

            from tools.interrupt import is_interrupted
            with patch("tools.interrupt.is_interrupted", return_value=False):
                result = env.execute("echo hello", timeout=5)

        assert isinstance(result, dict)
        assert "output" in result
        assert "returncode" in result
