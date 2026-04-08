"""
Centralized secret access for Hermes Agent.

Lookup priority (first non-None value wins):
  1. OS keychain  — python-keyring, isolated per profile
  2. Environment  — os.environ (populated by ~/.hermes/.env via env_loader)

Each profile gets its own keychain namespace so credentials never bleed between
profiles even on the same machine.

Usage:
    from tools.secrets import get_secret, set_secret, delete_secret

    # Read (keychain → env fallback)
    api_key = get_secret("OPENAI_API_KEY")

    # Store in OS keychain (local dev)
    set_secret("OPENAI_API_KEY", "sk-...")

    # Remove from keychain
    delete_secret("OPENAI_API_KEY")

    # Explicit profile override
    key = get_secret("OPENAI_API_KEY", profile="research")

Production (CI/servers): set env vars as normal — keyring is not required.
Keyring gracefully degrades to env-only when the package is absent.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

try:
    import keyring
    import keyring.errors

    _KEYRING_AVAILABLE = True
except ImportError:  # pragma: no cover
    _KEYRING_AVAILABLE = False

# Keychain service namespace.  One service per profile so vaults are isolated.
_SERVICE_PREFIX = "hermes-agent"


# ── profile detection ─────────────────────────────────────────────────────────


def _current_profile() -> str:
    """
    Derive the active profile name from HERMES_HOME.

    ~/.hermes/                       → "default"
    ~/.hermes/profiles/coder/        → "coder"
    ~/.hermes/profiles/research/     → "research"
    """
    hermes_home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
    parts = Path(hermes_home).parts
    try:
        idx = list(parts).index("profiles")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    except ValueError:
        pass
    return "default"


def _service_name(profile: Optional[str]) -> str:
    """Return the keychain service string for the given profile."""
    return f"{_SERVICE_PREFIX}/{profile or _current_profile()}"


# ── public API ────────────────────────────────────────────────────────────────


def get_secret(key: str, profile: Optional[str] = None) -> Optional[str]:
    """
    Retrieve a secret.  Checks the OS keychain first, then environment variables.

    Args:
        key:     Secret name, e.g. ``"OPENAI_API_KEY"``.
        profile: Profile override.  Defaults to the active profile derived from
                 ``HERMES_HOME``.

    Returns:
        The secret value, or ``None`` if not found in either source.
    """
    if _KEYRING_AVAILABLE:
        try:
            value = keyring.get_password(_service_name(profile), key)
            if value is not None:
                return value
        except Exception:
            # Keyring backend errors (locked screen, no backend, etc.) fall
            # through silently so the env-var fallback always works.
            pass

    return os.environ.get(key)


def set_secret(key: str, value: str, profile: Optional[str] = None) -> None:
    """
    Store a secret in the OS keychain under the profile's namespace.

    Args:
        key:     Secret name, e.g. ``"OPENAI_API_KEY"``.
        value:   The secret value to store.
        profile: Profile override.  Defaults to the active profile.

    Raises:
        RuntimeError: If ``python-keyring`` is not installed.
    """
    if not _KEYRING_AVAILABLE:
        raise RuntimeError(
            "python-keyring is not installed. "
            "Install it with: pip install keyring"
        )
    keyring.set_password(_service_name(profile), key, value)


def delete_secret(key: str, profile: Optional[str] = None) -> bool:
    """
    Remove a secret from the OS keychain.

    Args:
        key:     Secret name to remove.
        profile: Profile override.  Defaults to the active profile.

    Returns:
        ``True`` if deleted, ``False`` if the key did not exist or keyring
        is unavailable.
    """
    if not _KEYRING_AVAILABLE:
        return False
    try:
        keyring.delete_password(_service_name(profile), key)
        return True
    except keyring.errors.PasswordDeleteError:
        return False


def require_secret(key: str, profile: Optional[str] = None) -> str:
    """
    Like :func:`get_secret` but raises ``KeyError`` instead of returning ``None``.

    Useful at startup time to fail fast when a required credential is absent.

    Raises:
        KeyError: If the secret is not found in either keychain or environment.
    """
    value = get_secret(key, profile=profile)
    if value is None:
        raise KeyError(
            f"Required secret '{key}' not found in OS keychain or environment. "
            f"Set it with: hermes secrets set {key} <value>"
        )
    return value


def keyring_available() -> bool:
    """Return True if the python-keyring package is installed and functional."""
    return _KEYRING_AVAILABLE
