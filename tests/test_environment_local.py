"""Tests for tools/environments/local.py — LocalEnvironment and helpers."""
from __future__ import annotations

import os

import pytest

from tools.environments.local import (
    LocalEnvironment,
    _build_provider_env_blocklist,
    _clean_shell_noise,
    _extract_fenced_output,
    _find_bash,
    _make_run_env,
    _sanitize_subprocess_env,
    _OUTPUT_FENCE,
)


# ── _build_provider_env_blocklist ─────────────────────────────────────────────

class TestBuildProviderEnvBlocklist:
    def test_returns_frozenset(self):
        bl = _build_provider_env_blocklist()
        assert isinstance(bl, frozenset)

    def test_contains_openai_key(self):
        bl = _build_provider_env_blocklist()
        assert "OPENAI_API_KEY" in bl

    def test_contains_openrouter_key(self):
        bl = _build_provider_env_blocklist()
        assert "OPENROUTER_API_KEY" in bl

    def test_contains_modal_token(self):
        bl = _build_provider_env_blocklist()
        assert "MODAL_TOKEN_ID" in bl

    def test_contains_telegram_home_channel(self):
        bl = _build_provider_env_blocklist()
        assert "TELEGRAM_HOME_CHANNEL" in bl

    def test_contains_anthropic_base_url(self):
        bl = _build_provider_env_blocklist()
        assert "ANTHROPIC_BASE_URL" in bl


# ── _sanitize_subprocess_env ──────────────────────────────────────────────────

class TestSanitizeSubprocessEnv:
    def test_removes_blocked_var(self):
        env = {"OPENAI_API_KEY": "secret", "HOME": "/home/user"}
        result = _sanitize_subprocess_env(env)
        assert "OPENAI_API_KEY" not in result
        assert result["HOME"] == "/home/user"

    def test_passes_unblocked_var(self):
        env = {"MY_APP_KEY": "value", "PATH": "/usr/bin"}
        result = _sanitize_subprocess_env(env)
        assert result["MY_APP_KEY"] == "value"

    def test_force_prefix_restores_blocked_var(self):
        base = {"OPENAI_API_KEY": "secret"}
        extra = {"_HERMES_FORCE_OPENAI_API_KEY": "override"}
        result = _sanitize_subprocess_env(base, extra)
        assert result.get("OPENAI_API_KEY") == "override"

    def test_force_prefix_entries_removed(self):
        extra = {"_HERMES_FORCE_SOME_KEY": "val"}
        result = _sanitize_subprocess_env({}, extra)
        assert "_HERMES_FORCE_SOME_KEY" not in result

    def test_none_base_env_handled(self):
        result = _sanitize_subprocess_env(None)
        assert isinstance(result, dict)

    def test_none_extra_env_handled(self):
        result = _sanitize_subprocess_env({"FOO": "bar"}, None)
        assert result["FOO"] == "bar"

    def test_empty_dicts(self):
        result = _sanitize_subprocess_env({}, {})
        assert result == {}


# ── _find_bash ────────────────────────────────────────────────────────────────

class TestFindBash:
    def test_returns_string(self):
        bash = _find_bash()
        assert isinstance(bash, str)
        assert len(bash) > 0

    def test_path_exists_or_is_sh_fallback(self):
        bash = _find_bash()
        assert os.path.exists(bash) or bash.endswith("sh")


# ── _clean_shell_noise ────────────────────────────────────────────────────────

class TestCleanShellNoise:
    def test_passes_through_clean_output(self):
        output = "hello world\nfoo bar\n"
        assert _clean_shell_noise(output) == output

    def test_strips_bash_tty_noise_at_start(self):
        output = "bash: cannot set terminal process group (-1): Inappropriate ioctl for device\nhello\n"
        result = _clean_shell_noise(output)
        assert "bash: cannot set terminal process group" not in result
        assert "hello" in result

    def test_strips_no_job_control_at_start(self):
        output = "bash: no job control in this shell\nresult\n"
        result = _clean_shell_noise(output)
        assert "no job control" not in result

    def test_strips_last_login_at_start(self):
        output = "Last login: Mon Jan  1 00:00:00 2024\noutput"
        result = _clean_shell_noise(output)
        assert "Last login" not in result

    def test_preserves_trailing_newline(self):
        output = "output\n"
        assert _clean_shell_noise(output).endswith("\n")

    def test_empty_string(self):
        assert _clean_shell_noise("") == ""

    def test_all_noise_returns_empty(self):
        output = "bash: no job control in this shell\n"
        result = _clean_shell_noise(output)
        assert result == ""


# ── _extract_fenced_output ────────────────────────────────────────────────────

class TestExtractFencedOutput:
    def test_extracts_content_between_fences(self):
        raw = f"{_OUTPUT_FENCE}hello world{_OUTPUT_FENCE}"
        assert _extract_fenced_output(raw) == "hello world"

    def test_multiline_content(self):
        raw = f"{_OUTPUT_FENCE}line1\nline2\n{_OUTPUT_FENCE}"
        assert _extract_fenced_output(raw) == "line1\nline2\n"

    def test_no_fence_falls_back_to_noise_clean(self):
        raw = "Last login: Mon Jan  1\nhello"
        result = _extract_fenced_output(raw)
        assert "Last login" not in result

    def test_only_start_fence(self):
        raw = f"{_OUTPUT_FENCE}partial output"
        result = _extract_fenced_output(raw)
        # Should not crash, returns cleaned partial output
        assert isinstance(result, str)

    def test_empty_content_between_fences(self):
        raw = f"{_OUTPUT_FENCE}{_OUTPUT_FENCE}"
        assert _extract_fenced_output(raw) == ""


# ── _make_run_env ─────────────────────────────────────────────────────────────

class TestMakeRunEnv:
    def test_returns_dict(self):
        result = _make_run_env({})
        assert isinstance(result, dict)

    def test_removes_blocked_vars(self):
        env = {"OPENAI_API_KEY": "secret"}
        result = _make_run_env(env)
        assert "OPENAI_API_KEY" not in result

    def test_passes_regular_vars(self):
        env = {"MY_CUSTOM_VAR": "hello"}
        result = _make_run_env(env)
        assert result.get("MY_CUSTOM_VAR") == "hello"

    def test_path_includes_usr_bin(self):
        # PATH should always have /usr/bin
        result = _make_run_env({})
        path = result.get("PATH", "")
        assert "/usr/bin" in path

    def test_force_prefix_restores_key(self):
        env = {"_HERMES_FORCE_OPENAI_API_KEY": "override"}
        result = _make_run_env(env)
        assert result.get("OPENAI_API_KEY") == "override"
        assert "_HERMES_FORCE_OPENAI_API_KEY" not in result


# ── LocalEnvironment ──────────────────────────────────────────────────────────

class TestLocalEnvironment:
    def test_init_defaults(self):
        env = LocalEnvironment()
        assert env.timeout == 60
        assert env.persistent is False
        assert isinstance(env.cwd, str)

    def test_execute_simple_command(self):
        env = LocalEnvironment(timeout=10)
        result = env.execute("echo hello")
        assert result["returncode"] == 0
        assert "hello" in result["output"]

    def test_execute_with_cwd(self, tmp_path):
        env = LocalEnvironment(timeout=10)
        result = env.execute("pwd", cwd=str(tmp_path))
        assert result["returncode"] == 0
        # tmp_path might be symlinked (/var vs /private/var on macOS)
        assert tmp_path.name in result["output"]

    def test_execute_returns_nonzero_rc(self):
        env = LocalEnvironment(timeout=10)
        result = env.execute("exit 42")
        assert result["returncode"] == 42

    def test_execute_with_stdin_data(self):
        env = LocalEnvironment(timeout=10)
        result = env.execute("cat", stdin_data="from stdin")
        assert result["returncode"] == 0
        assert "from stdin" in result["output"]

    def test_execute_captures_stderr_in_output(self):
        env = LocalEnvironment(timeout=10)
        result = env.execute("echo err >&2")
        assert result["returncode"] == 0
        assert "err" in result["output"]

    def test_execute_timeout(self):
        env = LocalEnvironment(timeout=1)
        result = env.execute("sleep 10", timeout=1)
        assert result["returncode"] == 124
        assert "timed out" in result["output"].lower()

    def test_cleanup_is_safe(self):
        env = LocalEnvironment()
        env.cleanup()  # should not raise

    def test_stop_is_alias_for_cleanup(self):
        env = LocalEnvironment()
        env.stop()  # should not raise

    def test_multiline_output(self):
        env = LocalEnvironment(timeout=10)
        result = env.execute("echo line1; echo line2")
        assert "line1" in result["output"]
        assert "line2" in result["output"]

    def test_env_vars_passed_to_command(self):
        env = LocalEnvironment(env={"MY_TEST_VAR": "42"}, timeout=10)
        result = env.execute("echo $MY_TEST_VAR")
        assert "42" in result["output"]

    def test_blocked_env_vars_not_leaked(self):
        # OPENAI_API_KEY should be filtered from subprocess environment
        env = LocalEnvironment(env={"OPENAI_API_KEY": "leaksecret"}, timeout=10)
        result = env.execute("echo ${OPENAI_API_KEY:-empty}")
        assert "leaksecret" not in result["output"]
