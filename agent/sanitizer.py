"""
Input sanitization for user messages entering Hermes Agent.

Applied at the gateway message-ingress boundary (before the agent turn runs)
and at the CLI ingress point.

What it does:
  1. Strip null bytes and dangerous control characters
  2. Enforce a maximum message length (configurable via HERMES_MAX_MESSAGE_LEN)
  3. Detect prompt-injection patterns and log a warning
  4. Normalize unicode (NFC) to avoid homoglyph tricks

What it does NOT do:
  - Remove all special characters — messages may contain code, URLs, JSON, etc.
  - Modify the semantic content of messages
  - Block messages (it sanitizes and warns; blocking is a policy decision for
    the gateway's rate-limiter or authorization layer)

Usage:
    from agent.sanitizer import sanitize_message
    clean = sanitize_message(raw_text, source_id="telegram:u123")
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_MAX_LEN = 32_000   # characters — well above any legitimate message
MAX_LEN = int(os.environ.get("HERMES_MAX_MESSAGE_LEN", DEFAULT_MAX_LEN))

# ── Block mode ────────────────────────────────────────────────────────────────

# When HERMES_SANITIZER_BLOCK_INJECTION=1, detected injection patterns cause
# sanitize_message() to raise InjectionBlockedError instead of passing through.
# Default is 0 (warn-only) for backwards compatibility.
BLOCK_INJECTION = os.environ.get("HERMES_SANITIZER_BLOCK_INJECTION", "0") == "1"


class InjectionBlockedError(ValueError):
    """Raised by sanitize_message() when HERMES_SANITIZER_BLOCK_INJECTION=1
    and a prompt-injection pattern is detected in the input message."""

    def __init__(self, pattern_name: str, source_id: str = "") -> None:
        self.pattern_name = pattern_name
        self.source_id = source_id
        super().__init__(
            f"Message blocked: prompt injection pattern '{pattern_name}' "
            f"detected (source: {source_id!r})"
        )

# ── Prompt injection detection ─────────────────────────────────────────────────

# These patterns are heuristic indicators of prompt-injection attempts.
# Detection does NOT block the message — it emits a warning so operators can
# monitor for abuse. Extend this list as new patterns emerge.
_INJECTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("system-override",    re.compile(r"\bsystem\s*:\s*(you are|ignore|disregard)", re.IGNORECASE)),
    ("role-reset",         re.compile(r"\b(ignore|disregard|forget)\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|context)", re.IGNORECASE)),
    ("jailbreak-marker",   re.compile(r"\[/?INST\]|<\|im_start\|>|<\|im_end\|>|<\|system\|>", re.IGNORECASE)),
    ("repeat-override",    re.compile(r"repeat\s+(after\s+me|the\s+following)\s*:", re.IGNORECASE)),
    ("act-as",             re.compile(r"\bact\s+as\s+(if\s+you\s+are|a\s+|an\s+)(DAN|jailbreak|unrestricted|uncensored|evil)", re.IGNORECASE)),
    ("do-anything-now",    re.compile(r"\bDAN\b.*\bdo\s+anything\s+now\b", re.IGNORECASE)),
    ("token-smuggling",    re.compile(r"(\u200b|\u200c|\u200d|\ufeff|\u00ad){3,}")),  # invisible chars in bulk
    ("base64-instruction", re.compile(r"decode\s+this\s+(base64|b64)\s*:?\s*[A-Za-z0-9+/=]{20,}", re.IGNORECASE)),
]

# ── Control character filter ──────────────────────────────────────────────────

# Allow: printable ASCII, tabs, newlines, carriage returns.
# Strip: null bytes (0x00), DEL (0x7F), and C0/C1 control codes except \t\n\r.
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]")

# ── Public API ────────────────────────────────────────────────────────────────


def sanitize_message(text: str, *, source_id: str = "") -> str:
    """
    Sanitize a user message before it enters the agent loop.

    Args:
        text:      Raw user message text.
        source_id: Optional identifier for logging (e.g. "telegram:u123").

    Returns:
        Sanitized message text.  May be shorter than the input but the semantic
        content is preserved as much as possible.
    """
    if not isinstance(text, str):
        text = str(text)

    original_len = len(text)

    # 1. Unicode normalisation (NFC) — prevents homoglyph / decomposition tricks
    text = unicodedata.normalize("NFC", text)

    # 2. Strip dangerous control characters
    text = _CONTROL_CHAR_RE.sub("", text)

    # 3. Enforce maximum length
    if len(text) > MAX_LEN:
        logger.warning(
            "sanitizer: message from %r truncated %d → %d chars",
            source_id, len(text), MAX_LEN,
        )
        text = text[:MAX_LEN]

    # 4. Detect prompt injection patterns (warn in default mode; raise in block mode)
    _detect_injection(text, source_id=source_id, block=BLOCK_INJECTION)

    if len(text) != original_len:
        logger.debug(
            "sanitizer: message from %r changed length %d → %d",
            source_id, original_len, len(text),
        )

    return text


def _detect_injection(text: str, *, source_id: str, block: bool = False) -> None:
    """Log a warning for each injection pattern found in *text*.

    If *block* is True (HERMES_SANITIZER_BLOCK_INJECTION=1), raises
    InjectionBlockedError on the first matched pattern instead of continuing.
    """
    for name, pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            logger.warning(
                "sanitizer: possible prompt injection detected in message from %r "
                "(pattern: %s). %s",
                source_id,
                name,
                "Message BLOCKED." if block else "Message will still be processed.",
            )
            if block:
                raise InjectionBlockedError(name, source_id=source_id)
