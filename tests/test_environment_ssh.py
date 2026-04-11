"""Tests for tools/environments/ssh.py — SSHEnvironment and helpers."""
from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.environments.ssh import SSHEnvironment, _ensure_ssh_available


# ── _ensure_ssh_available ─────────────────────────────────────────────────────

class TestEnsureSshAvailable:
    def test_raises_when_ssh_not_found(self):
        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="SSH is not installed"):
                _ensure_ssh_available()

    def test_passes_when_ssh_found(self):
        with patch("shutil.which", return_value="/usr/bin/ssh"):
            _ensure_ssh_available()  # no exception


# ── SSHEnvironment ────────────────────────────────────────────────────────────

def _make_ssh_env(host="remote.example.com", user="testuser", **kwargs):
    """Create an SSHEnvironment with mocked SSH setup."""
    mock_run_result = MagicMock()
    mock_run_result.returncode = 0
    mock_run_result.stdout = "/home/testuser\n"
    mock_run_result.stderr = ""

    with patch("shutil.which", return_value="/usr/bin/ssh"), \
         patch("subprocess.run", return_value=mock_run_result), \
         patch.object(SSHEnvironment, "_establish_connection", return_value=None), \
         patch.object(SSHEnvironment, "_detect_remote_home", return_value="/home/testuser"), \
         patch.object(SSHEnvironment, "_sync_skills_and_credentials", return_value=None):
        return SSHEnvironment(host=host, user=user, **kwargs)


class TestSSHEnvironmentInit:
    def test_stores_host_and_user(self):
        env = _make_ssh_env()
        assert env.host == "remote.example.com"
        assert env.user == "testuser"

    def test_default_port(self):
        env = _make_ssh_env()
        assert env.port == 22

    def test_custom_port(self):
        env = _make_ssh_env(port=2222)
        assert env.port == 2222

    def test_default_cwd(self):
        env = _make_ssh_env()
        assert env.cwd == "~"

    def test_control_socket_path(self):
        env = _make_ssh_env(host="srv", user="alice", port=22)
        assert "alice@srv:22" in str(env.control_socket)

    def test_persistent_default_false(self):
        env = _make_ssh_env()
        assert env.persistent is False

    def test_raises_when_ssh_not_found(self):
        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="SSH is not installed"):
                SSHEnvironment("host", "user")


class TestSSHBuildCommand:
    def test_command_includes_host(self):
        env = _make_ssh_env(host="myhost", user="alice")
        cmd = env._build_ssh_command()
        assert "alice@myhost" in cmd

    def test_command_includes_custom_port(self):
        env = _make_ssh_env(port=2222)
        cmd = env._build_ssh_command()
        assert "-p" in cmd
        assert "2222" in cmd

    def test_command_no_port_flag_for_22(self):
        env = _make_ssh_env(port=22)
        cmd = env._build_ssh_command()
        assert "-p" not in cmd

    def test_command_includes_key_path(self):
        env = _make_ssh_env(key_path="/tmp/id_rsa")
        cmd = env._build_ssh_command()
        assert "-i" in cmd
        assert "/tmp/id_rsa" in cmd

    def test_extra_args_included(self):
        env = _make_ssh_env()
        cmd = env._build_ssh_command(extra_args=["-v"])
        assert "-v" in cmd

    def test_control_master_auto(self):
        env = _make_ssh_env()
        cmd = env._build_ssh_command()
        # ControlMaster=auto should be present
        cmd_str = " ".join(cmd)
        assert "ControlMaster=auto" in cmd_str

    def test_batch_mode(self):
        env = _make_ssh_env()
        cmd = env._build_ssh_command()
        cmd_str = " ".join(cmd)
        assert "BatchMode=yes" in cmd_str


class TestSSHCleanup:
    def test_cleanup_does_not_raise(self):
        env = _make_ssh_env()
        with patch("subprocess.run", return_value=MagicMock(returncode=0)):
            env.cleanup()  # should not raise

    def test_stop_calls_cleanup(self):
        env = _make_ssh_env()
        with patch.object(env, "cleanup") as mock_cleanup, \
             patch("subprocess.run", return_value=MagicMock(returncode=0)):
            env.stop()
            mock_cleanup.assert_called_once()
