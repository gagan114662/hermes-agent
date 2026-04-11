"""
Optional Sentry error tracking for Hermes Agent.

Off by default.  Activates only when ``SENTRY_DSN`` is set in the environment
(or passed explicitly to ``init_sentry``).

Usage:
    # At startup (call after configure_logging):
    from hermes_cli.sentry import init_sentry
    init_sentry()  # reads SENTRY_DSN from env; no-op if unset

    # In error handlers:
    from hermes_cli.sentry import capture_exception
    try:
        ...
    except Exception as exc:
        capture_exception(exc, tool="terminal", session_id="abc")

    # Breadcrumbs (optional structured trail leading up to an error):
    from hermes_cli.sentry import add_breadcrumb
    add_breadcrumb("tool_dispatched", data={"tool": "terminal", "duration_ms": 42})

sentry-sdk is an optional dependency.  All functions no-op gracefully when the
package is absent or when no DSN is configured — no try/except needed at call sites.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_initialized: bool = False
_sdk_available: bool = False

try:
    import sentry_sdk  # type: ignore
    from sentry_sdk.integrations.logging import LoggingIntegration  # type: ignore
    _sdk_available = True
except ImportError:
    pass


def init_sentry(
    dsn: str | None = None,
    *,
    environment: str | None = None,
    release: str | None = None,
    traces_sample_rate: float = 0.0,
    attach_stacktrace: bool = True,
) -> bool:
    """
    Initialise the Sentry SDK.  No-op when the DSN is absent.

    Args:
        dsn:                 Sentry DSN string.  Falls back to ``SENTRY_DSN``
                             env var if not provided.
        environment:         e.g. ``"production"``, ``"staging"``.  Falls back
                             to ``SENTRY_ENVIRONMENT`` env var, then ``"local"``.
        release:             Release version string.  Falls back to
                             ``SENTRY_RELEASE`` env var, then the package version.
        traces_sample_rate:  0.0–1.0 fraction of transactions to profile.
                             Disabled by default (0.0) to avoid surprises.
        attach_stacktrace:   Attach stack traces to non-exception events.

    Returns:
        ``True`` if Sentry was successfully configured, ``False`` otherwise.
    """
    global _initialized

    effective_dsn = dsn or os.environ.get("SENTRY_DSN", "").strip()
    if not effective_dsn:
        return False  # Opt-out: no DSN → stay quiet

    if not _sdk_available:
        logger.warning(
            "SENTRY_DSN is set but sentry-sdk is not installed. "
            "Install it with: pip install 'hermes-agent[monitoring]'"
        )
        return False

    if _initialized:
        return True

    effective_env = (
        environment
        or os.environ.get("SENTRY_ENVIRONMENT", "").strip()
        or "local"
    )
    effective_release = (
        release
        or os.environ.get("SENTRY_RELEASE", "").strip()
        or _get_version()
    )

    # Forward WARNING+ log records to Sentry as breadcrumbs / events
    sentry_logging = LoggingIntegration(
        level=logging.WARNING,   # breadcrumb level
        event_level=logging.ERROR,  # event level (creates Sentry issues)
    )

    sentry_sdk.init(
        dsn=effective_dsn,
        environment=effective_env,
        release=effective_release,
        traces_sample_rate=traces_sample_rate,
        attach_stacktrace=attach_stacktrace,
        integrations=[sentry_logging],
        # Don't send PII by default
        send_default_pii=False,
        # Suppress noisy SDK breadcrumbs from httpx / urllib3
        default_integrations=True,
    )

    _initialized = True
    logger.info("Sentry error tracking enabled (env=%s, release=%s)", effective_env, effective_release)
    return True


def capture_exception(exc: BaseException, **context: Any) -> str | None:
    """
    Report an exception to Sentry with optional context key-value pairs.

    No-op when Sentry is not initialised.

    Args:
        exc:      The exception to report.
        **context: Extra key-value pairs attached as Sentry tags/extra.

    Returns:
        The Sentry event ID (hex string) if captured, else ``None``.
    """
    if not _initialized or not _sdk_available:
        return None
    try:
        with sentry_sdk.push_scope() as scope:
            for key, value in context.items():
                scope.set_extra(key, value)
            return sentry_sdk.capture_exception(exc)
    except Exception:
        return None


def capture_message(message: str, level: str = "info", **context: Any) -> str | None:
    """
    Send a message event to Sentry.

    No-op when Sentry is not initialised.

    Args:
        message: Human-readable message string.
        level:   Sentry level: ``"debug"``, ``"info"``, ``"warning"``, ``"error"``, ``"fatal"``.
        **context: Extra key-value pairs attached as Sentry extra data.

    Returns:
        The Sentry event ID if captured, else ``None``.
    """
    if not _initialized or not _sdk_available:
        return None
    try:
        with sentry_sdk.push_scope() as scope:
            for key, value in context.items():
                scope.set_extra(key, value)
            return sentry_sdk.capture_message(message, level=level)
    except Exception:
        return None


def add_breadcrumb(
    message: str,
    category: str = "hermes",
    level: str = "info",
    data: dict | None = None,
) -> None:
    """
    Add a breadcrumb to the current Sentry scope.

    Breadcrumbs form a trail of events leading up to an error.  Good candidates:
    tool dispatches, session starts/ends, agent turns.

    No-op when Sentry is not initialised.
    """
    if not _initialized or not _sdk_available:
        return
    try:
        sentry_sdk.add_breadcrumb(
            message=message,
            category=category,
            level=level,
            data=data or {},
        )
    except Exception:
        pass


def set_user(user_id: str | None = None, **attributes: Any) -> None:
    """
    Set the active user context on the current Sentry scope.

    Useful for correlating errors with specific Hermes profiles.
    No-op when Sentry is not initialised.
    """
    if not _initialized or not _sdk_available:
        return
    try:
        sentry_sdk.set_user({"id": user_id, **attributes} if user_id else None)
    except Exception:
        pass


def is_configured() -> bool:
    """Return ``True`` if Sentry has been successfully initialised."""
    return _initialized


# ── internal helpers ──────────────────────────────────────────────────────────

def _get_version() -> str:
    try:
        from importlib.metadata import version
        return version("hermes-agent")
    except Exception:
        return "unknown"
