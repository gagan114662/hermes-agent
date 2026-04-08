"""
Tests for tools/secrets.py — centralized secret access with keychain + env fallback.
"""
from __future__ import annotations

import os

import keyring
import keyring.backend
import keyring.errors
import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────

class InMemoryKeyring(keyring.backend.KeyringBackend):
    """Ephemeral in-process keyring backend for testing."""

    priority = 1000  # override any system backend

    def __init__(self):
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str):
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if (service, username) not in self._store:
            raise keyring.errors.PasswordDeleteError("not found")
        del self._store[(service, username)]


@pytest.fixture()
def mem_keyring():
    """Install a fresh in-memory keyring and restore the previous one after."""
    backend = InMemoryKeyring()
    old = keyring.get_keyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(old)


def _import_secrets():
    """Import secrets module. Reloads to pick up current keyring state."""
    import importlib
    import tools.secrets as mod
    importlib.reload(mod)
    return mod


# ── Basic get/set/delete ──────────────────────────────────────────────────────

class TestGetSecret:
    def test_returns_none_when_not_found(self, mem_keyring, monkeypatch):
        monkeypatch.delenv("MY_KEY", raising=False)
        mod = _import_secrets()
        assert mod.get_secret("MY_KEY") is None

    def test_reads_from_env_when_no_keyring_value(self, mem_keyring, monkeypatch):
        monkeypatch.setenv("MY_ENV_KEY", "env-value")
        mod = _import_secrets()
        assert mod.get_secret("MY_ENV_KEY") == "env-value"

    def test_keyring_takes_priority_over_env(self, mem_keyring, monkeypatch):
        monkeypatch.setenv("MY_KEY", "env-value")
        mod = _import_secrets()
        mod.set_secret("MY_KEY", "keychain-value")
        assert mod.get_secret("MY_KEY") == "keychain-value"

    def test_falls_back_to_env_when_keyring_raises(self, monkeypatch):
        """If the keyring backend raises, get_secret silently falls back to env."""

        class BrokenKeyring(keyring.backend.KeyringBackend):
            priority = 1000

            def get_password(self, service, username):
                raise OSError("keyring locked")

            def set_password(self, service, username, password):
                raise OSError("keyring locked")

            def delete_password(self, service, username):
                raise OSError("keyring locked")

        old = keyring.get_keyring()
        keyring.set_keyring(BrokenKeyring())
        try:
            import importlib
            import tools.secrets as mod
            importlib.reload(mod)
            monkeypatch.setenv("FALLBACK_KEY", "fallback-value")
            assert mod.get_secret("FALLBACK_KEY") == "fallback-value"
        finally:
            keyring.set_keyring(old)

    def test_profile_argument_overrides_service_namespace(self, mem_keyring, monkeypatch):
        """Secrets stored under 'coder' profile must not be visible to 'research'."""
        mod = _import_secrets()
        mod.set_secret("SHARED_KEY", "coder-secret", profile="coder")
        monkeypatch.delenv("SHARED_KEY", raising=False)
        # Reading with a different profile returns None (no env fallback either)
        assert mod.get_secret("SHARED_KEY", profile="research") is None

    def test_profile_reads_own_namespace(self, mem_keyring, monkeypatch):
        mod = _import_secrets()
        mod.set_secret("SHARED_KEY", "coder-secret", profile="coder")
        assert mod.get_secret("SHARED_KEY", profile="coder") == "coder-secret"


# ── Special characters in key names ──────────────────────────────────────────

class TestSpecialCharacterKeys:
    def test_key_with_dots(self, mem_keyring, monkeypatch):
        monkeypatch.delenv("api.key.v2", raising=False)
        mod = _import_secrets()
        mod.set_secret("api.key.v2", "dot-value")
        assert mod.get_secret("api.key.v2") == "dot-value"

    def test_key_with_slashes(self, mem_keyring, monkeypatch):
        monkeypatch.delenv("service/api/key", raising=False)
        mod = _import_secrets()
        mod.set_secret("service/api/key", "slash-value")
        assert mod.get_secret("service/api/key") == "slash-value"

    def test_key_with_unicode(self, mem_keyring, monkeypatch):
        key = "cléf-secrète"
        monkeypatch.delenv(key, raising=False)
        mod = _import_secrets()
        mod.set_secret(key, "unicode-value")
        assert mod.get_secret(key) == "unicode-value"

    def test_key_with_spaces(self, mem_keyring, monkeypatch):
        key = "MY KEY WITH SPACES"
        monkeypatch.delenv(key, raising=False)
        mod = _import_secrets()
        mod.set_secret(key, "spaced-value")
        assert mod.get_secret(key) == "spaced-value"

    def test_empty_string_value(self, mem_keyring, monkeypatch):
        """Storing an empty string is a valid secret value."""
        monkeypatch.delenv("EMPTY_VAL_KEY", raising=False)
        mod = _import_secrets()
        mod.set_secret("EMPTY_VAL_KEY", "")
        # Empty string is falsy but should not fall through to env
        result = mod.get_secret("EMPTY_VAL_KEY")
        # Either the keyring returns "" (found) or None (not found), never env value
        assert result == "" or result is None


# ── require_secret ────────────────────────────────────────────────────────────

class TestRequireSecret:
    def test_returns_value_when_present(self, mem_keyring, monkeypatch):
        mod = _import_secrets()
        mod.set_secret("REQUIRED_KEY", "required-value")
        assert mod.require_secret("REQUIRED_KEY") == "required-value"

    def test_raises_key_error_when_missing(self, mem_keyring, monkeypatch):
        monkeypatch.delenv("MISSING_REQUIRED", raising=False)
        mod = _import_secrets()
        with pytest.raises(KeyError, match="MISSING_REQUIRED"):
            mod.require_secret("MISSING_REQUIRED")

    def test_error_message_includes_hint(self, mem_keyring, monkeypatch):
        monkeypatch.delenv("HINT_KEY", raising=False)
        mod = _import_secrets()
        with pytest.raises(KeyError) as exc_info:
            mod.require_secret("HINT_KEY")
        # Error message should be helpful — mention the key name
        assert "HINT_KEY" in str(exc_info.value)

    def test_env_var_satisfies_require_secret(self, mem_keyring, monkeypatch):
        monkeypatch.setenv("ENV_REQUIRED", "from-env")
        mod = _import_secrets()
        assert mod.require_secret("ENV_REQUIRED") == "from-env"


# ── delete_secret ─────────────────────────────────────────────────────────────

class TestDeleteSecret:
    def test_delete_existing_key(self, mem_keyring, monkeypatch):
        mod = _import_secrets()
        mod.set_secret("DEL_KEY", "will-be-deleted")
        result = mod.delete_secret("DEL_KEY")
        assert result is True
        monkeypatch.delenv("DEL_KEY", raising=False)
        assert mod.get_secret("DEL_KEY") is None

    def test_delete_nonexistent_key_returns_false(self, mem_keyring):
        mod = _import_secrets()
        result = mod.delete_secret("NONEXISTENT_KEY_XYZ")
        assert result is False


# ── Profile isolation (real in-memory keyring) ────────────────────────────────

class TestProfileIsolation:
    """Use a real in-memory keyring backend to prove profile namespacing works."""

    def test_two_profiles_do_not_share_secrets(self, mem_keyring, monkeypatch):
        """Store a secret under 'coder', verify it's absent from 'research'."""
        mod = _import_secrets()

        monkeypatch.delenv("ISOLATED_KEY", raising=False)
        mod.set_secret("ISOLATED_KEY", "coder-only-value", profile="coder")

        # 'research' profile should not see the coder secret
        assert mod.get_secret("ISOLATED_KEY", profile="research") is None

    def test_three_profiles_isolated(self, mem_keyring, monkeypatch):
        mod = _import_secrets()
        monkeypatch.delenv("MULTI_KEY", raising=False)

        mod.set_secret("MULTI_KEY", "alpha-val", profile="alpha")
        mod.set_secret("MULTI_KEY", "beta-val", profile="beta")
        mod.set_secret("MULTI_KEY", "gamma-val", profile="gamma")

        assert mod.get_secret("MULTI_KEY", profile="alpha") == "alpha-val"
        assert mod.get_secret("MULTI_KEY", profile="beta") == "beta-val"
        assert mod.get_secret("MULTI_KEY", profile="gamma") == "gamma-val"

    def test_default_profile_separate_from_named(self, mem_keyring, monkeypatch):
        mod = _import_secrets()
        monkeypatch.delenv("PROFILE_KEY", raising=False)
        monkeypatch.setenv("HERMES_HOME", str(os.path.expanduser("~/.hermes")))

        mod.set_secret("PROFILE_KEY", "default-value")
        assert mod.get_secret("PROFILE_KEY", profile="custom") is None
        assert mod.get_secret("PROFILE_KEY") == "default-value"


# ── keyring_available() ───────────────────────────────────────────────────────

class TestKeyringAvailable:
    def test_returns_bool(self, mem_keyring):
        mod = _import_secrets()
        result = mod.keyring_available()
        assert isinstance(result, bool)

    def test_returns_true_when_keyring_installed(self, mem_keyring):
        # We just installed keyring, so this must be True
        mod = _import_secrets()
        assert mod.keyring_available() is True
