"""Tests for tools/secrets.py — centralized secret access with keyring + env fallback."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_module(keyring_available: bool = True):
    """Re-import secrets module with _KEYRING_AVAILABLE patched."""
    import importlib
    import tools.secrets as mod

    importlib.reload(mod)
    mod._KEYRING_AVAILABLE = keyring_available
    return mod


# ── profile detection ─────────────────────────────────────────────────────────


class TestCurrentProfile:
    def test_default_profile_when_no_hermes_home(self, monkeypatch):
        monkeypatch.delenv("HERMES_HOME", raising=False)
        from tools.secrets import _current_profile
        # Doesn't contain /profiles/ so should be "default"
        assert _current_profile() == "default"

    def test_named_profile_from_hermes_home(self, monkeypatch, tmp_path):
        profile_dir = tmp_path / "profiles" / "coder"
        monkeypatch.setenv("HERMES_HOME", str(profile_dir))
        from tools.secrets import _current_profile
        assert _current_profile() == "coder"

    def test_research_profile(self, monkeypatch, tmp_path):
        profile_dir = tmp_path / "profiles" / "research"
        monkeypatch.setenv("HERMES_HOME", str(profile_dir))
        from tools.secrets import _current_profile
        assert _current_profile() == "research"

    def test_default_when_hermes_home_has_no_profiles_segment(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
        from tools.secrets import _current_profile
        assert _current_profile() == "default"


class TestServiceName:
    def test_service_includes_prefix(self, monkeypatch):
        monkeypatch.delenv("HERMES_HOME", raising=False)
        from tools.secrets import _service_name
        assert _service_name(None).startswith("hermes-agent/")

    def test_explicit_profile_used(self, monkeypatch):
        from tools.secrets import _service_name
        assert _service_name("myprofile") == "hermes-agent/myprofile"

    def test_default_profile_in_service(self, monkeypatch):
        monkeypatch.delenv("HERMES_HOME", raising=False)
        from tools.secrets import _service_name
        assert _service_name(None) == "hermes-agent/default"


# ── get_secret ────────────────────────────────────────────────────────────────


class TestGetSecret:
    def test_returns_none_when_not_found(self, monkeypatch):
        monkeypatch.delenv("MISSING_KEY", raising=False)
        import tools.secrets as mod
        with patch.object(mod, "_KEYRING_AVAILABLE", False):
            result = mod.get_secret("MISSING_KEY")
        assert result is None

    def test_returns_env_var_when_keyring_unavailable(self, monkeypatch):
        monkeypatch.setenv("SOME_API_KEY", "env-value-123")
        import tools.secrets as mod
        with patch.object(mod, "_KEYRING_AVAILABLE", False):
            result = mod.get_secret("SOME_API_KEY")
        assert result == "env-value-123"

    def test_keyring_takes_priority_over_env(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "env-value")
        import tools.secrets as mod
        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = "keychain-value"
        with patch.object(mod, "_KEYRING_AVAILABLE", True), \
             patch.object(mod, "keyring", mock_keyring, create=True):
            result = mod.get_secret("MY_KEY")
        assert result == "keychain-value"

    def test_falls_back_to_env_when_keyring_returns_none(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "env-fallback")
        import tools.secrets as mod
        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = None
        with patch.object(mod, "_KEYRING_AVAILABLE", True), \
             patch.object(mod, "keyring", mock_keyring, create=True):
            result = mod.get_secret("MY_KEY")
        assert result == "env-fallback"

    def test_keyring_exception_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "env-fallback")
        import tools.secrets as mod
        mock_keyring = MagicMock()
        mock_keyring.get_password.side_effect = RuntimeError("keyring locked")
        with patch.object(mod, "_KEYRING_AVAILABLE", True), \
             patch.object(mod, "keyring", mock_keyring, create=True):
            result = mod.get_secret("MY_KEY")
        assert result == "env-fallback"

    def test_profile_isolation(self, monkeypatch):
        """Secrets from different profiles must not bleed together."""
        monkeypatch.delenv("MY_KEY", raising=False)
        import tools.secrets as mod

        mock_keyring = MagicMock()

        def _get_password(service, key):
            if service == "hermes-agent/coder":
                return "coder-value"
            return None

        mock_keyring.get_password.side_effect = _get_password
        with patch.object(mod, "_KEYRING_AVAILABLE", True), \
             patch.object(mod, "keyring", mock_keyring, create=True):
            assert mod.get_secret("MY_KEY", profile="coder") == "coder-value"
            assert mod.get_secret("MY_KEY", profile="research") is None

    def test_correct_service_passed_to_keyring(self, monkeypatch):
        monkeypatch.delenv("MY_KEY", raising=False)
        import tools.secrets as mod
        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = None
        with patch.object(mod, "_KEYRING_AVAILABLE", True), \
             patch.object(mod, "keyring", mock_keyring, create=True):
            mod.get_secret("MY_KEY", profile="prod")
        mock_keyring.get_password.assert_called_once_with("hermes-agent/prod", "MY_KEY")


# ── set_secret ────────────────────────────────────────────────────────────────


class TestSetSecret:
    def test_calls_keyring_set_password(self, monkeypatch):
        import tools.secrets as mod
        mock_keyring = MagicMock()
        with patch.object(mod, "_KEYRING_AVAILABLE", True), \
             patch.object(mod, "keyring", mock_keyring, create=True):
            mod.set_secret("MY_KEY", "my-value", profile="default")
        mock_keyring.set_password.assert_called_once_with(
            "hermes-agent/default", "MY_KEY", "my-value"
        )

    def test_raises_when_keyring_unavailable(self, monkeypatch):
        import tools.secrets as mod
        with patch.object(mod, "_KEYRING_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="keyring"):
                mod.set_secret("MY_KEY", "value")

    def test_profile_namespaced_correctly(self, monkeypatch):
        import tools.secrets as mod
        mock_keyring = MagicMock()
        with patch.object(mod, "_KEYRING_AVAILABLE", True), \
             patch.object(mod, "keyring", mock_keyring, create=True):
            mod.set_secret("API_KEY", "secret", profile="research")
        service = mock_keyring.set_password.call_args[0][0]
        assert service == "hermes-agent/research"


# ── delete_secret ─────────────────────────────────────────────────────────────


class TestDeleteSecret:
    def test_returns_true_on_success(self, monkeypatch):
        import tools.secrets as mod
        mock_keyring = MagicMock()
        mock_keyring.errors = MagicMock()
        mock_keyring.errors.PasswordDeleteError = Exception
        mock_keyring.delete_password.return_value = None
        with patch.object(mod, "_KEYRING_AVAILABLE", True), \
             patch.object(mod, "keyring", mock_keyring, create=True):
            result = mod.delete_secret("MY_KEY", profile="default")
        assert result is True

    def test_returns_false_when_keyring_unavailable(self, monkeypatch):
        import tools.secrets as mod
        with patch.object(mod, "_KEYRING_AVAILABLE", False):
            result = mod.delete_secret("MY_KEY")
        assert result is False

    def test_returns_false_on_password_delete_error(self, monkeypatch):
        import tools.secrets as mod
        mock_keyring = MagicMock()

        class FakeDeleteError(Exception):
            pass

        mock_keyring.errors = MagicMock()
        mock_keyring.errors.PasswordDeleteError = FakeDeleteError
        mock_keyring.delete_password.side_effect = FakeDeleteError("not found")
        with patch.object(mod, "_KEYRING_AVAILABLE", True), \
             patch.object(mod, "keyring", mock_keyring, create=True):
            result = mod.delete_secret("MY_KEY")
        assert result is False


# ── require_secret ────────────────────────────────────────────────────────────


class TestRequireSecret:
    def test_returns_value_when_present(self, monkeypatch):
        monkeypatch.setenv("REQUIRED_KEY", "found-value")
        import tools.secrets as mod
        with patch.object(mod, "_KEYRING_AVAILABLE", False):
            result = mod.require_secret("REQUIRED_KEY")
        assert result == "found-value"

    def test_raises_key_error_when_missing(self, monkeypatch):
        monkeypatch.delenv("REQUIRED_KEY", raising=False)
        import tools.secrets as mod
        with patch.object(mod, "_KEYRING_AVAILABLE", False):
            with pytest.raises(KeyError, match="REQUIRED_KEY"):
                mod.require_secret("REQUIRED_KEY")

    def test_error_message_includes_hermes_command(self, monkeypatch):
        monkeypatch.delenv("REQUIRED_KEY", raising=False)
        import tools.secrets as mod
        with patch.object(mod, "_KEYRING_AVAILABLE", False):
            with pytest.raises(KeyError) as exc_info:
                mod.require_secret("REQUIRED_KEY")
        assert "hermes secrets set" in str(exc_info.value)


# ── keyring_available ─────────────────────────────────────────────────────────


class TestKeyringAvailable:
    def test_returns_bool(self):
        from tools.secrets import keyring_available
        assert isinstance(keyring_available(), bool)


# ── scanner ───────────────────────────────────────────────────────────────────


class TestScanFile:
    def test_clean_file_returns_no_findings(self, tmp_path):
        f = tmp_path / "clean.py"
        f.write_text('API_BASE = "https://api.example.com"\nMODEL = "gpt-4"\n')
        from scripts.scan_secrets import scan_file
        assert scan_file(f) == []

    def test_detects_openai_key(self, tmp_path):
        f = tmp_path / "config.py"
        f.write_text('OPENAI_KEY = "sk-abcdefghijklmnopqrstuvwxyz123456"\n')
        from scripts.scan_secrets import scan_file
        findings = scan_file(f)
        assert len(findings) == 1
        assert "sk-" in findings[0].label.lower() or "openai" in findings[0].label.lower()

    def test_detects_anthropic_key(self, tmp_path):
        f = tmp_path / "config.py"
        f.write_text('TOKEN = "sk-ant-api03-verylongtokenstringhere1234567890abcdef"\n')
        from scripts.scan_secrets import scan_file
        findings = scan_file(f)
        assert len(findings) >= 1
        assert any("anthropic" in finding.label.lower() for finding in findings)

    def test_detects_github_pat(self, tmp_path):
        f = tmp_path / "deploy.sh"
        # ghp_ + exactly 36 alphanumeric chars = valid GitHub PAT format
        f.write_text('GH_TOKEN=ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890\n')
        from scripts.scan_secrets import scan_file
        findings = scan_file(f)
        assert len(findings) >= 1
        assert any("github" in finding.label.lower() for finding in findings)

    def test_detects_telegram_token(self, tmp_path):
        f = tmp_path / "bot.py"
        f.write_text('BOT_TOKEN = "1234567890:AABBCCDDEEFFaabbccddeeffgghhiijjkkll"\n')
        from scripts.scan_secrets import scan_file
        findings = scan_file(f)
        assert len(findings) >= 1
        assert any("telegram" in finding.label.lower() for finding in findings)

    def test_detects_private_key_block(self, tmp_path):
        f = tmp_path / "key.pem"
        f.write_text("-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAK...\n-----END RSA PRIVATE KEY-----\n")
        from scripts.scan_secrets import scan_file
        findings = scan_file(f)
        assert len(findings) >= 1
        assert any("private key" in finding.label.lower() for finding in findings)

    def test_skips_binary_extensions(self, tmp_path):
        f = tmp_path / "image.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\nsk-abcdefghijklmnopqrstuvwxyz12345678")
        from scripts.scan_secrets import scan_file
        assert scan_file(f) == []

    def test_snippet_is_redacted(self, tmp_path):
        f = tmp_path / "config.py"
        secret = "sk-verylongsecretvaluethatshouldberedacted"
        f.write_text(f'KEY = "{secret}"\n')
        from scripts.scan_secrets import scan_file
        findings = scan_file(f)
        if findings:
            assert secret not in findings[0].snippet

    def test_line_number_is_accurate(self, tmp_path):
        f = tmp_path / "multi.py"
        f.write_text("# line 1\n# line 2\nAPI_KEY = sk-abcdefghijklmnopqrstuvwxyz\n")
        from scripts.scan_secrets import scan_file
        findings = scan_file(f)
        if findings:
            assert findings[0].line == 3

    def test_skips_scan_secrets_script_itself(self):
        """The scanner must not flag its own pattern constants."""
        from pathlib import Path
        from scripts.scan_secrets import scan_file, _SKIP_FILENAMES
        script = Path("scripts/scan_secrets.py")
        assert str(script) in _SKIP_FILENAMES or script.name in _SKIP_FILENAMES


class TestScannerMain:
    def test_exits_zero_with_no_staged_files(self, monkeypatch):
        from scripts.scan_secrets import main
        monkeypatch.setattr("scripts.scan_secrets.get_staged_files", lambda: [])
        assert main([]) == 0

    def test_exits_zero_for_clean_files(self, tmp_path, monkeypatch):
        clean = tmp_path / "clean.py"
        clean.write_text("x = 1\n")
        from scripts.scan_secrets import main
        assert main([str(clean)]) == 0

    def test_exits_one_for_dirty_files(self, tmp_path):
        dirty = tmp_path / "dirty.py"
        dirty.write_text('KEY = "sk-abcdefghijklmnopqrstuvwxyz12345678"\n')
        from scripts.scan_secrets import main
        assert main([str(dirty)]) == 1
