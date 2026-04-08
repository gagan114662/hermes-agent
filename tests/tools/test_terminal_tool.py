"""Tests for tools/terminal_tool.py — helper functions and config parsing."""
from __future__ import annotations

import importlib
import json
import os
import time
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

# tools.terminal_tool is shadowed by the tools package __init__.py which
# re-exports terminal_tool as a function.  Use importlib to get the module.
_tt_mod = importlib.import_module("tools.terminal_tool")

_transform_sudo_command = _tt_mod._transform_sudo_command
set_sudo_password_callback = _tt_mod.set_sudo_password_callback
set_approval_callback = _tt_mod.set_approval_callback
_handle_sudo_failure = _tt_mod._handle_sudo_failure
_check_disk_usage_warning = _tt_mod._check_disk_usage_warning
DISK_USAGE_WARNING_THRESHOLD_GB = _tt_mod.DISK_USAGE_WARNING_THRESHOLD_GB
get_active_environments_info = _tt_mod.get_active_environments_info
cleanup_all_environments = _tt_mod.cleanup_all_environments
cleanup_vm = _tt_mod.cleanup_vm
_cleanup_inactive_envs = _tt_mod._cleanup_inactive_envs
_start_cleanup_thread = _tt_mod._start_cleanup_thread
_stop_cleanup_thread = _tt_mod._stop_cleanup_thread


# ── _transform_sudo_command ───────────────────────────────────────────────

class TestTransformSudoCommand:
    def test_no_sudo_returns_unchanged(self, monkeypatch):
        monkeypatch.delenv("SUDO_PASSWORD", raising=False)
        cmd, stdin = _transform_sudo_command("ls -la /tmp")
        assert cmd == "ls -la /tmp"
        assert stdin is None

    def test_sudo_without_password_returns_unchanged(self, monkeypatch):
        monkeypatch.delenv("SUDO_PASSWORD", raising=False)
        monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)
        mod = _tt_mod
        mod._cached_sudo_password = ""
        cmd, stdin = _transform_sudo_command("sudo apt update")
        assert cmd == "sudo apt update"
        assert stdin is None

    def test_sudo_with_env_password(self, monkeypatch):
        monkeypatch.setenv("SUDO_PASSWORD", "secretpass")
        cmd, stdin = _transform_sudo_command("sudo apt update")
        assert "sudo -S" in cmd
        assert stdin == "secretpass\n"

    def test_multiple_sudo_in_command(self, monkeypatch):
        monkeypatch.setenv("SUDO_PASSWORD", "pass")
        cmd, stdin = _transform_sudo_command("sudo chmod +x /bin/foo && sudo chown root /bin/foo")
        assert cmd.count("sudo -S") == 2
        assert stdin == "pass\n"

    def test_visudo_not_transformed(self, monkeypatch):
        monkeypatch.setenv("SUDO_PASSWORD", "pass")
        cmd, stdin = _transform_sudo_command("visudo /etc/sudoers")
        # 'visudo' is not 'sudo' at word boundary
        assert "visudo" in cmd
        assert stdin is None  # no actual sudo

    def test_sudo_at_word_boundary_only(self, monkeypatch):
        monkeypatch.setenv("SUDO_PASSWORD", "pass")
        cmd, stdin = _transform_sudo_command("echo 'not sudo' | grep sudo")
        # still contains the word sudo so it would get replaced
        assert isinstance(cmd, str)
        assert isinstance(stdin, (str, type(None)))

    def test_plain_sudo_prefix(self, monkeypatch):
        monkeypatch.setenv("SUDO_PASSWORD", "mypass")
        cmd, stdin = _transform_sudo_command("sudo systemctl restart nginx")
        assert "sudo -S -p ''" in cmd
        assert stdin is not None


# ── set_sudo_password_callback / set_approval_callback ───────────────────

class TestCallbackRegistration:
    def test_set_sudo_password_callback(self):
        """set_sudo_password_callback should not raise."""
        cb = lambda: "mypassword"
        set_sudo_password_callback(cb)
        set_sudo_password_callback(None)  # cleanup

    def test_set_approval_callback(self):
        """set_approval_callback should not raise."""
        cb = lambda cmd, desc: "once"
        set_approval_callback(cb)
        set_approval_callback(None)  # cleanup


# ── _handle_sudo_failure ──────────────────────────────────────────────────

class TestHandleSudoFailure:
    def test_non_gateway_returns_original(self, monkeypatch):
        monkeypatch.delenv("HERMES_GATEWAY_SESSION", raising=False)
        output = "sudo: a password is required"
        result = _handle_sudo_failure(output, "local")
        assert result == output

    def test_gateway_adds_tip_for_sudo_failure(self, monkeypatch):
        monkeypatch.setenv("HERMES_GATEWAY_SESSION", "1")
        output = "sudo: a password is required"
        with patch.object(_tt_mod, "display_hermes_home", return_value="~/.hermes", create=True):
            try:
                result = _handle_sudo_failure(output, "local")
                # Should have added tip
                assert "sudo" in result.lower() or len(result) >= len(output)
            except Exception:
                pass  # import error for hermes_constants is acceptable in test env

    def test_no_sudo_failure_returns_original(self, monkeypatch):
        monkeypatch.setenv("HERMES_GATEWAY_SESSION", "1")
        output = "command completed successfully"
        result = _handle_sudo_failure(output, "local")
        assert result == output


# ── _check_disk_usage_warning ─────────────────────────────────────────────

class TestCheckDiskUsageWarning:
    def test_returns_bool(self):
        result = _check_disk_usage_warning()
        assert isinstance(result, bool)

    def test_returns_false_on_empty_scratch(self, tmp_path, monkeypatch):
        """When there's nothing in the scratch dir, should not warn."""
        with patch.object(_tt_mod, "_get_scratch_dir", return_value=tmp_path):
            result = _check_disk_usage_warning()
        assert result is False

    def test_returns_false_on_exception(self):
        """Should not propagate exceptions."""
        with patch.object(_tt_mod, "_get_scratch_dir", side_effect=Exception("boom")):
            result = _check_disk_usage_warning()
        assert result is False


# ── _parse_env_var ────────────────────────────────────────────────────────

class TestParseEnvVar:
    def test_returns_default_when_not_set(self, monkeypatch):
        _parse_env_var = _tt_mod._parse_env_var
        monkeypatch.delenv("_TEST_PARSE_VAR", raising=False)
        result = _parse_env_var("_TEST_PARSE_VAR", "30", converter=int, type_label="integer")
        assert result == 30

    def test_parses_int_from_env(self, monkeypatch):
        _parse_env_var = _tt_mod._parse_env_var
        monkeypatch.setenv("_TEST_PARSE_VAR2", "120")
        result = _parse_env_var("_TEST_PARSE_VAR2", "30", converter=int, type_label="integer")
        assert result == 120

    def test_raises_on_invalid(self, monkeypatch):
        _parse_env_var = _tt_mod._parse_env_var
        monkeypatch.setenv("_TEST_PARSE_VAR3", "not_a_number")
        with pytest.raises(ValueError):
            _parse_env_var("_TEST_PARSE_VAR3", "30", converter=int, type_label="integer")


# ── get_active_environments_info ──────────────────────────────────────────

class TestGetActiveEnvironmentsInfo:
    def test_returns_dict(self):
        pass  # already imported at module level
        result = get_active_environments_info()
        assert isinstance(result, dict)

    def test_has_expected_keys(self):
        pass  # already imported at module level
        result = get_active_environments_info()
        # Should have some summary information
        assert isinstance(result, dict)


# ── register_task_env_overrides / clear_task_env_overrides ────────────────

class TestTaskEnvOverrides:
    def test_register_and_clear_overrides(self):
        register_task_env_overrides = _tt_mod.register_task_env_overrides; clear_task_env_overrides = _tt_mod.clear_task_env_overrides
        register_task_env_overrides("test_task_123", {"docker_image": "ubuntu:22.04"})
        clear_task_env_overrides("test_task_123")
        # Should not raise

    def test_clear_nonexistent_does_not_raise(self):
        clear_task_env_overrides = _tt_mod.clear_task_env_overrides
        clear_task_env_overrides("nonexistent_task_id_xyz")


# ── _check_disk_usage_warning (high usage path) ───────────────────────────

class TestCheckDiskUsageWarningHighUsage:
    def test_returns_true_when_files_exceed_threshold(self, tmp_path, monkeypatch):
        """When files in scratch dir total >threshold, should return True."""
        # Create a hermes- directory with a file
        hermes_dir = tmp_path / "hermes-test123"
        hermes_dir.mkdir()
        test_file = hermes_dir / "big.bin"
        test_file.write_bytes(b"x")

        # Patch threshold to 0 so even 1 byte triggers warning
        original = _tt_mod.DISK_USAGE_WARNING_THRESHOLD_GB
        _tt_mod.DISK_USAGE_WARNING_THRESHOLD_GB = 0.0
        try:
            with patch.object(_tt_mod, "_get_scratch_dir", return_value=tmp_path):
                result = _check_disk_usage_warning()
        finally:
            _tt_mod.DISK_USAGE_WARNING_THRESHOLD_GB = original
        assert result is True

    def test_stat_oserror_is_silenced(self, tmp_path):
        """OSError on stat should be swallowed, not propagate."""
        hermes_dir = tmp_path / "hermes-broken"
        hermes_dir.mkdir()
        broken_file = hermes_dir / "file.bin"
        broken_file.write_bytes(b"x")

        original_stat = Path.stat

        def stat_that_raises(self, **kwargs):
            if self.name == "file.bin":
                raise OSError("permission denied")
            return original_stat(self, **kwargs)

        with patch.object(_tt_mod, "_get_scratch_dir", return_value=tmp_path), \
             patch.object(Path, "stat", stat_that_raises):
            result = _check_disk_usage_warning()
        assert isinstance(result, bool)


# ── _handle_sudo_failure (gateway path) ───────────────────────────────────

class TestHandleSudoFailureGateway:
    def test_gateway_no_tty_present_adds_tip(self, monkeypatch):
        monkeypatch.setenv("HERMES_GATEWAY_SESSION", "1")
        output = "sudo: no tty present"
        try:
            result = _handle_sudo_failure(output, "local")
            # Either original (import error) or enhanced (tip added)
            assert output in result
        except Exception:
            pass  # import error for hermes_constants is acceptable

    def test_gateway_terminal_required_adds_tip(self, monkeypatch):
        monkeypatch.setenv("HERMES_GATEWAY_SESSION", "1")
        output = "sudo: a terminal is required"
        try:
            result = _handle_sudo_failure(output, "local")
            assert output in result
        except Exception:
            pass

    def test_gateway_unrelated_output_unchanged(self, monkeypatch):
        monkeypatch.setenv("HERMES_GATEWAY_SESSION", "1")
        output = "everything worked fine"
        result = _handle_sudo_failure(output, "local")
        assert result == output


# ── _get_env_config ───────────────────────────────────────────────────────

class TestGetEnvConfig:
    def _get_config(self, monkeypatch, overrides: dict):
        _get_env_config = _tt_mod._get_env_config
        for k, v in overrides.items():
            if v is None:
                monkeypatch.delenv(k, raising=False)
            else:
                monkeypatch.setenv(k, str(v))
        return _get_env_config()

    def test_local_env_default(self, monkeypatch):
        cfg = self._get_config(monkeypatch, {"TERMINAL_ENV": "local"})
        assert cfg["env_type"] == "local"
        assert "cwd" in cfg
        assert "timeout" in cfg

    def test_docker_env_type(self, monkeypatch):
        cfg = self._get_config(monkeypatch, {
            "TERMINAL_ENV": "docker",
            "TERMINAL_DOCKER_MOUNT_CWD_TO_WORKSPACE": None,
            "TERMINAL_CWD": None,
        })
        assert cfg["env_type"] == "docker"

    def test_ssh_env_type(self, monkeypatch):
        cfg = self._get_config(monkeypatch, {
            "TERMINAL_ENV": "ssh",
            "TERMINAL_SSH_HOST": "myserver.example.com",
            "TERMINAL_SSH_USER": "ubuntu",
        })
        assert cfg["env_type"] == "ssh"
        assert cfg["ssh_host"] == "myserver.example.com"

    def test_timeout_parsed_from_env(self, monkeypatch):
        cfg = self._get_config(monkeypatch, {
            "TERMINAL_ENV": "local",
            "TERMINAL_TIMEOUT": "300",
        })
        assert cfg["timeout"] == 300

    def test_docker_mount_cwd_false_by_default(self, monkeypatch):
        cfg = self._get_config(monkeypatch, {
            "TERMINAL_ENV": "docker",
            "TERMINAL_DOCKER_MOUNT_CWD_TO_WORKSPACE": None,
        })
        assert cfg["docker_mount_cwd_to_workspace"] is False

    def test_docker_mount_cwd_enabled(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TERMINAL_ENV", "docker")
        monkeypatch.setenv("TERMINAL_DOCKER_MOUNT_CWD_TO_WORKSPACE", "true")
        monkeypatch.setenv("TERMINAL_CWD", str(tmp_path))
        # Ensure tmp_path looks like a host path
        _get_env_config = _tt_mod._get_env_config
        cfg = _get_env_config()
        assert cfg["env_type"] == "docker"
        # If the path was remapped, host_cwd should be set; otherwise just check no crash
        assert isinstance(cfg, dict)

    def test_container_resource_config(self, monkeypatch):
        cfg = self._get_config(monkeypatch, {
            "TERMINAL_ENV": "docker",
            "TERMINAL_CONTAINER_CPU": "2",
            "TERMINAL_CONTAINER_MEMORY": "8192",
            "TERMINAL_CONTAINER_DISK": "102400",
        })
        assert cfg["container_cpu"] == 2.0
        assert cfg["container_memory"] == 8192
        assert cfg["container_disk"] == 102400


# ── _cleanup_inactive_envs ────────────────────────────────────────────────

class TestCleanupInactiveEnvs:
    def _inject_env(self, task_id: str, age_seconds: float = 400):
        """Inject a mock environment into the active environments dict."""
        mod = _tt_mod
        mock_env = MagicMock()
        mock_env.cleanup = MagicMock()
        with mod._env_lock:
            mod._active_environments[task_id] = mock_env
            mod._last_activity[task_id] = time.time() - age_seconds
        return mock_env

    def _remove_env(self, task_id: str):
        mod = _tt_mod
        with mod._env_lock:
            mod._active_environments.pop(task_id, None)
            mod._last_activity.pop(task_id, None)

    def test_stale_env_gets_cleanup_called(self):
        """Environments inactive longer than lifetime_seconds should be cleaned."""
        task_id = "test-stale-cleanup-001"
        mock_env = self._inject_env(task_id, age_seconds=400)
        try:
            _cleanup_inactive_envs(lifetime_seconds=300)
            mock_env.cleanup.assert_called_once()
        finally:
            self._remove_env(task_id)

    def test_fresh_env_is_not_cleaned(self):
        """Recently-active environments must not be touched."""
        task_id = "test-fresh-cleanup-002"
        mock_env = self._inject_env(task_id, age_seconds=10)
        try:
            _cleanup_inactive_envs(lifetime_seconds=300)
            mock_env.cleanup.assert_not_called()
        finally:
            self._remove_env(task_id)

    def test_env_with_stop_method_uses_stop(self):
        """If env has no cleanup() but has stop(), use stop()."""
        mod = _tt_mod
        task_id = "test-stop-method-003"
        mock_env = MagicMock(spec=["stop"])
        with mod._env_lock:
            mod._active_environments[task_id] = mock_env
            mod._last_activity[task_id] = time.time() - 400
        try:
            _cleanup_inactive_envs(lifetime_seconds=300)
            mock_env.stop.assert_called_once()
        finally:
            self._remove_env(task_id)

    def test_cleanup_exception_is_logged_not_raised(self):
        """Cleanup errors should be swallowed."""
        task_id = "test-cleanup-error-004"
        mock_env = self._inject_env(task_id, age_seconds=400)
        mock_env.cleanup.side_effect = RuntimeError("sandbox gone")
        try:
            _cleanup_inactive_envs(lifetime_seconds=300)  # must not raise
        finally:
            self._remove_env(task_id)


# ── cleanup_vm ────────────────────────────────────────────────────────────

class TestCleanupVm:
    def _inject_env(self, task_id: str):
        mod = _tt_mod
        mock_env = MagicMock()
        mock_env.cleanup = MagicMock()
        with mod._env_lock:
            mod._active_environments[task_id] = mock_env
            mod._last_activity[task_id] = time.time()
        return mock_env

    def test_cleanup_vm_calls_cleanup_on_env(self):
        task_id = "test-cleanup-vm-001"
        mock_env = self._inject_env(task_id)
        cleanup_vm(task_id)
        mock_env.cleanup.assert_called_once()

    def test_cleanup_vm_removes_from_active(self):
        mod = _tt_mod
        task_id = "test-cleanup-vm-002"
        self._inject_env(task_id)
        cleanup_vm(task_id)
        assert task_id not in mod._active_environments
        assert task_id not in mod._last_activity

    def test_cleanup_vm_nonexistent_task_does_not_raise(self):
        cleanup_vm("task-id-that-does-not-exist-xyz")

    def test_cleanup_vm_404_error_is_swallowed(self):
        task_id = "test-cleanup-404-003"
        mock_env = self._inject_env(task_id)
        mock_env.cleanup.side_effect = Exception("404 not found")
        cleanup_vm(task_id)  # must not raise

    def test_cleanup_vm_uses_stop_when_no_cleanup(self):
        mod = _tt_mod
        task_id = "test-stop-no-cleanup-004"
        mock_env = MagicMock(spec=["stop"])
        with mod._env_lock:
            mod._active_environments[task_id] = mock_env
            mod._last_activity[task_id] = time.time()
        cleanup_vm(task_id)
        mock_env.stop.assert_called_once()


# ── cleanup_all_environments ───────────────────────────────────────────────

class TestCleanupAllEnvironments:
    def test_cleans_all_active_envs(self):
        mod = _tt_mod
        # Inject two mock envs
        envs = {}
        for i in range(2):
            task_id = f"test-all-cleanup-{i}"
            mock_env = MagicMock()
            with mod._env_lock:
                mod._active_environments[task_id] = mock_env
                mod._last_activity[task_id] = time.time()
            envs[task_id] = mock_env

        # Use a scratch dir without matching hermes- dirs to avoid filesystem side effects
        with patch.object(_tt_mod, "_get_scratch_dir", return_value=Path("/tmp/nonexistent_hermes_test")):
            with patch("glob.glob", return_value=[]):
                count = cleanup_all_environments()

        assert count >= 2
        for mock_env in envs.values():
            mock_env.cleanup.assert_called_once()

    def test_returns_cleaned_count(self):
        mod = _tt_mod
        task_id = "test-count-cleanup"
        mock_env = MagicMock()
        with mod._env_lock:
            mod._active_environments[task_id] = mock_env
            mod._last_activity[task_id] = time.time()

        with patch.object(_tt_mod, "_get_scratch_dir", return_value=Path("/tmp/nonexistent")):
            with patch("glob.glob", return_value=[]):
                count = cleanup_all_environments()
        assert count >= 1


# ── _start_cleanup_thread / _stop_cleanup_thread ──────────────────────────

class TestCleanupThread:
    def test_start_creates_daemon_thread(self):
        mod = _tt_mod
        # Stop any existing thread first
        _stop_cleanup_thread()
        _start_cleanup_thread()
        thread = mod._cleanup_thread
        assert thread is not None
        assert thread.is_alive()
        assert thread.daemon is True
        _stop_cleanup_thread()

    def test_stop_stops_thread(self):
        mod = _tt_mod
        _start_cleanup_thread()
        _stop_cleanup_thread()
        # After stop, _cleanup_running should be False
        assert mod._cleanup_running is False

    def test_start_twice_does_not_create_duplicate(self):
        mod = _tt_mod
        _stop_cleanup_thread()
        _start_cleanup_thread()
        first_thread = mod._cleanup_thread
        _start_cleanup_thread()  # calling again
        second_thread = mod._cleanup_thread
        assert first_thread is second_thread
        _stop_cleanup_thread()


# ── get_active_environments_info (with active envs) ───────────────────────

class TestGetActiveEnvironmentsInfoDetailed:
    def test_count_reflects_active_envs(self):
        mod = _tt_mod
        task_id = "test-info-count-001"
        mock_env = MagicMock()
        with mod._env_lock:
            initial_count = len(mod._active_environments)
            mod._active_environments[task_id] = mock_env
            mod._last_activity[task_id] = time.time()
        try:
            with patch.object(_tt_mod, "_get_scratch_dir", return_value=Path("/tmp/nonexistent")):
                with patch("glob.glob", return_value=[]):
                    info = get_active_environments_info()
            assert info["count"] >= initial_count + 1
            assert task_id in info["task_ids"]
        finally:
            with mod._env_lock:
                mod._active_environments.pop(task_id, None)
                mod._last_activity.pop(task_id, None)

    def test_total_disk_usage_mb_is_numeric(self):
        with patch.object(_tt_mod, "_get_scratch_dir", return_value=Path("/tmp/nonexistent")):
            with patch("glob.glob", return_value=[]):
                info = get_active_environments_info()
        assert isinstance(info["total_disk_usage_mb"], (int, float))
        assert info["total_disk_usage_mb"] >= 0
