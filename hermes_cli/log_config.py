"""
Structured logging configuration for Hermes Agent.

Two output modes:
  - JSON (production / machine-parseable):  one JSON object per line via
    python-json-logger.  Every record includes timestamp, level, logger,
    message plus any bound context (session_id, profile, …).
  - Text (development / interactive):  standard human-readable format.

Usage:
    from hermes_cli.log_config import configure_logging, bind_log_context

    # At startup — call once before other modules log anything
    configure_logging(level="INFO", json_logs=True)

    # Bind per-session context (all subsequent log records include these fields)
    bind_log_context(session_id="abc123", profile="default")

    # All existing logging.getLogger() calls continue to work unchanged
    import logging
    log = logging.getLogger(__name__)
    log.info("Tool dispatched", extra={"tool": "terminal", "duration_ms": 42})
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import threading
from pathlib import Path
from typing import Any

# python-json-logger is an optional dependency — graceful fallback to text.
try:
    from pythonjsonlogger import jsonlogger as _jsonlogger  # type: ignore
    _JSON_LOGGER_AVAILABLE = True
except ImportError:
    _JSON_LOGGER_AVAILABLE = False

# ── thread-local context ──────────────────────────────────────────────────────

_ctx = threading.local()


def bind_log_context(**kwargs: Any) -> None:
    """
    Bind key-value pairs to the current thread's log context.

    Every log record emitted from this thread will include these fields
    until :func:`clear_log_context` is called.

    Example::

        bind_log_context(session_id="abc123", profile="coder")
    """
    if not hasattr(_ctx, "fields"):
        _ctx.fields = {}
    _ctx.fields.update(kwargs)


def clear_log_context() -> None:
    """Remove all thread-local log context fields."""
    _ctx.fields = {}


def get_log_context() -> dict:
    """Return a copy of the current thread-local context."""
    return dict(getattr(_ctx, "fields", {}))


# ── context-injecting filter ──────────────────────────────────────────────────

class _ContextFilter(logging.Filter):
    """Injects thread-local context fields into every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = getattr(_ctx, "fields", {})
        for key, value in ctx.items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True


# ── JSON formatter ────────────────────────────────────────────────────────────

def _make_json_formatter() -> logging.Formatter:
    """Build a JSON log formatter that includes standard + context fields."""
    if not _JSON_LOGGER_AVAILABLE:
        # Fallback: structured-ish text when package absent
        return logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        )

    class _HermesJsonFormatter(_jsonlogger.JsonFormatter):
        def add_fields(self, log_record: dict, record: logging.LogRecord, message_dict: dict) -> None:  # type: ignore[override]
            super().add_fields(log_record, record, message_dict)
            # Rename/normalise standard fields
            log_record["level"] = log_record.pop("levelname", record.levelname)
            log_record["logger"] = log_record.pop("name", record.name)
            log_record.setdefault("timestamp", log_record.pop("asctime", ""))
            # Inject any thread-local context that wasn't already set
            ctx = getattr(_ctx, "fields", {})
            for k, v in ctx.items():
                log_record.setdefault(k, v)

    return _HermesJsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        rename_fields={"levelname": "level", "name": "logger"},
    )


def _make_text_formatter() -> logging.Formatter:
    return logging.Formatter(
        fmt="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


# ── public configure function ─────────────────────────────────────────────────

def configure_logging(
    level: str | int = "INFO",
    *,
    json_logs: bool | None = None,
    log_file: str | Path | None = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
) -> None:
    """
    Configure Hermes structured logging.  Call once at process startup.

    Args:
        level:        Root log level string or int (``"DEBUG"``, ``"INFO"``, …).
        json_logs:    Emit JSON lines.  Defaults to ``True`` when
                      ``HERMES_JSON_LOGS=1`` is set, else ``False``.
        log_file:     Optional path for a rotating file handler.  Defaults to
                      ``~/.hermes/logs/hermes.log`` when ``None`` and the
                      directory already exists.
        max_bytes:    Rotating file max size in bytes.
        backup_count: Number of rotated log files to keep.
    """
    if json_logs is None:
        json_logs = os.environ.get("HERMES_JSON_LOGS", "0").strip() in ("1", "true", "yes")

    numeric_level = (
        level if isinstance(level, int) else getattr(logging, level.upper(), logging.INFO)
    )

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Remove stale handlers so re-configuration is idempotent
    for h in root.handlers[:]:
        root.removeHandler(h)

    formatter = _make_json_formatter() if json_logs else _make_text_formatter()
    ctx_filter = _ContextFilter()

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.addFilter(ctx_filter)
    root.addHandler(console)

    # Optional rotating file handler
    if log_file is None:
        default_log_dir = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "logs"
        if default_log_dir.exists():
            log_file = default_log_dir / "hermes.log"

    if log_file is not None:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            str(log_file),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(ctx_filter)
        root.addHandler(file_handler)

    # Quiet noisy third-party libraries (same as current cli.py behaviour)
    _suppress = ["openai", "httpx", "httpcore", "anthropic", "urllib3", "modal"]
    for name in _suppress:
        logging.getLogger(name).setLevel(logging.WARNING)
