"""Tests for tools/environments/base.py — BaseEnvironment ABC and helpers."""
from __future__ import annotations

import os
import subprocess
from unittest.mock import patch

import pytest

from tools.environments.base import BaseEnvironment, get_sandbox_dir


# ── Concrete stub for testing abstract class ──────────────────────────────────

class _ConcreteEnv(BaseEnvironment):
    """Minimal concrete subclass for testing shared helpers."""

    def __init__(self, cwd="", timeout=60, env=None):
        super().__init__(cwd=cwd, timeout=timeout, env=env)
        self.cleaned_up = False

    def execute(self, command, cwd="", *, timeout=None, stdin_data=None):
        return {"output": "ok", "returncode": 0}

    def cleanup(self):
        self.cleaned_up = True


# ── get_sandbox_dir ───────────────────────────────────────────────────────────

class TestGetSandboxDir:
    def test_returns_path_object(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        monkeypatch.delenv("TERMINAL_SANDBOX_DIR", raising=False)
        p = get_sandbox_dir()
        assert p.is_dir()

    def test_custom_via_env_var(self, tmp_path, monkeypatch):
        custom = tmp_path / "sandboxes_custom"
        monkeypatch.setenv("TERMINAL_SANDBOX_DIR", str(custom))
        p = get_sandbox_dir()
        assert p == custom
        assert p.is_dir()

    def test_creates_directory_if_missing(self, tmp_path, monkeypatch):
        target = tmp_path / "new_sandbox"
        monkeypatch.setenv("TERMINAL_SANDBOX_DIR", str(target))
        assert not target.exists()
        get_sandbox_dir()
        assert target.is_dir()


# ── BaseEnvironment construction ──────────────────────────────────────────────

class TestBaseEnvironmentInit:
    def test_stores_cwd(self):
        env = _ConcreteEnv(cwd="/tmp/test")
        assert env.cwd == "/tmp/test"

    def test_stores_timeout(self):
        env = _ConcreteEnv(timeout=42)
        assert env.timeout == 42

    def test_env_defaults_to_empty_dict(self):
        env = _ConcreteEnv()
        assert env.env == {}

    def test_env_stores_provided_dict(self):
        env = _ConcreteEnv(env={"FOO": "bar"})
        assert env.env == {"FOO": "bar"}


# ── stop / cleanup ────────────────────────────────────────────────────────────

class TestStopAndCleanup:
    def test_stop_calls_cleanup(self):
        env = _ConcreteEnv()
        env.stop()
        assert env.cleaned_up

    def test_cleanup_directly(self):
        env = _ConcreteEnv()
        env.cleanup()
        assert env.cleaned_up

    def test_del_calls_cleanup_silently(self):
        env = _ConcreteEnv()
        # __del__ should not raise even if cleanup raises
        env.cleaned_up = True
        env.__del__()  # no exception


# ── _build_run_kwargs ─────────────────────────────────────────────────────────

class TestBuildRunKwargs:
    def setup_method(self):
        self.env = _ConcreteEnv(timeout=30)

    def test_basic_kwargs(self):
        kw = self.env._build_run_kwargs(None)
        assert kw["text"] is True
        assert kw["timeout"] == 30
        assert kw["stdout"] == subprocess.PIPE
        assert kw["stderr"] == subprocess.STDOUT

    def test_timeout_override(self):
        kw = self.env._build_run_kwargs(99)
        assert kw["timeout"] == 99

    def test_stdin_data_sets_input(self):
        kw = self.env._build_run_kwargs(None, stdin_data="hello")
        assert kw["input"] == "hello"
        assert "stdin" not in kw

    def test_no_stdin_data_sets_devnull(self):
        kw = self.env._build_run_kwargs(None)
        assert kw["stdin"] == subprocess.DEVNULL
        assert "input" not in kw

    def test_encoding_is_utf8(self):
        kw = self.env._build_run_kwargs(None)
        assert kw["encoding"] == "utf-8"

    def test_errors_mode(self):
        kw = self.env._build_run_kwargs(None)
        assert kw["errors"] == "replace"


# ── _timeout_result ───────────────────────────────────────────────────────────

class TestTimeoutResult:
    def test_returns_returncode_124(self):
        env = _ConcreteEnv(timeout=5)
        result = env._timeout_result(5)
        assert result["returncode"] == 124

    def test_message_includes_timeout(self):
        env = _ConcreteEnv(timeout=10)
        result = env._timeout_result(10)
        assert "10" in result["output"]

    def test_uses_instance_timeout_when_none(self):
        env = _ConcreteEnv(timeout=7)
        result = env._timeout_result(None)
        assert "7" in result["output"]


# ── _prepare_command (sudo transform) ────────────────────────────────────────

class TestPrepareCommand:
    def test_passthrough_without_sudo(self):
        env = _ConcreteEnv()
        with patch("tools.terminal_tool._transform_sudo_command") as mock_t:
            mock_t.return_value = ("ls -la", None)
            cmd, stdin = env._prepare_command("ls -la")
        assert cmd == "ls -la"
        assert stdin is None

    def test_sudo_command_gets_transformed(self):
        env = _ConcreteEnv()
        with patch("tools.terminal_tool._transform_sudo_command") as mock_t:
            mock_t.return_value = ("echo password | sudo -S ls", "password\n")
            cmd, stdin = env._prepare_command("sudo ls")
        assert stdin == "password\n"
