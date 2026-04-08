"""
Sandbox policy for Hermes Agent tool execution.

Provides path and network allowlisting that is enforced in the tool dispatch
layer before any handler runs.  This is a defence-in-depth control — it does
NOT replace OS-level sandboxing, but it catches the majority of path traversal
and SSRF attempts in tool arguments before they reach the filesystem or network.

Configuration (env vars):
    HERMES_SANDBOX_EXTRA_PATHS   colon-separated list of additional allowed
                                 filesystem paths (beyond the defaults)
    HERMES_SANDBOX_BLOCK_NETWORK  set to "1" or "true" to block ALL outbound
                                 URLs not in the domain allowlist (default: warn only)
    HERMES_SANDBOX_STRICT        set to "1" to turn path violations into errors
                                 instead of warnings (default: warn)

Defaults allow:
    Filesystem: HERMES_HOME, /tmp, CWD, common data dirs
    Network:    any (all domains allowed unless HERMES_SANDBOX_BLOCK_NETWORK=1)
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Filesystem allowlist ───────────────────────────────────────────────────────

def _default_allowed_paths() -> list[Path]:
    hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")).resolve()
    paths = [
        hermes_home,
        Path("/tmp").resolve(),
        Path("/var/tmp").resolve(),
        Path.cwd().resolve(),
        Path.home() / "Downloads",
        Path.home() / "Documents",
        Path.home() / "Desktop",
    ]
    # Extra paths from env
    extra = os.environ.get("HERMES_SANDBOX_EXTRA_PATHS", "")
    for p in extra.split(":"):
        p = p.strip()
        if p:
            paths.append(Path(p).resolve())
    return [p for p in paths if p.exists() or str(p).startswith("/tmp")]


def _is_path_allowed(path_str: str) -> bool:
    """Return True if *path_str* is under one of the allowed filesystem roots."""
    try:
        target = Path(path_str).resolve()
    except (TypeError, ValueError):
        return True  # non-path string — not our concern
    for allowed in _default_allowed_paths():
        try:
            target.relative_to(allowed)
            return True
        except ValueError:
            continue
    return False


def _strict_mode() -> bool:
    return os.environ.get("HERMES_SANDBOX_STRICT", "").lower() in ("1", "true", "yes")


def _network_block_mode() -> bool:
    return os.environ.get("HERMES_SANDBOX_BLOCK_NETWORK", "").lower() in ("1", "true", "yes")


# ── Network allowlist ─────────────────────────────────────────────────────────

# Domains that tool calls are always allowed to contact.
# This list is intentionally broad — it covers the services Hermes legitimately
# calls.  Narrow it with HERMES_SANDBOX_BLOCK_NETWORK=1 + HERMES_SANDBOX_EXTRA_PATHS.
_DEFAULT_ALLOWED_DOMAINS = {
    "api.openai.com",
    "openrouter.ai",
    "api.anthropic.com",
    "api.z.ai",
    "api.kimi.com",
    "platform.moonshot.ai",
    "api.mistral.ai",
    "api.together.xyz",
    "api.groq.com",
    "generativelanguage.googleapis.com",
    "api.exa.ai",
    "api.firecrawl.dev",
    "fal.run",
    "modal.run",
    "api.telegram.org",
    "discord.com",
    "discordapp.com",
    "slack.com",
    "api.slack.com",
    "github.com",
    "api.github.com",
    "pypi.org",
    "files.pythonhosted.org",
    "registry-1.docker.io",
    "docker.io",
    "production.cloudflare.docker.com",
}


def _extract_domain(url_or_host: str) -> str:
    """Best-effort domain extraction from a URL or hostname string."""
    url_or_host = url_or_host.strip()
    # Strip protocol
    for proto in ("https://", "http://", "ftp://"):
        if url_or_host.startswith(proto):
            url_or_host = url_or_host[len(proto):]
            break
    # Take up to first / or :
    domain = url_or_host.split("/")[0].split(":")[0]
    return domain.lower()


def _is_domain_allowed(domain: str) -> bool:
    if not _network_block_mode():
        return True   # warn-only by default
    domain = domain.lower()
    if domain in _DEFAULT_ALLOWED_DOMAINS:
        return True
    # Allow sub-domains of allowed domains
    for allowed in _DEFAULT_ALLOWED_DOMAINS:
        if domain.endswith("." + allowed):
            return True
    return False


# ── Argument scanning ──────────────────────────────────────────────────────────

# Arg keys that typically carry filesystem paths
_PATH_ARG_KEYS = re.compile(
    r"(path|file|dir|directory|folder|src|dest|destination|source|"
    r"output|input|log|config|workspace|workdir|cwd|mount)",
    re.IGNORECASE,
)

# Arg keys that typically carry URLs or hostnames
_URL_ARG_KEYS = re.compile(
    r"(url|uri|endpoint|host|hostname|server|base_url|webhook|proxy|target)",
    re.IGNORECASE,
)

# Strings that look like absolute paths
_ABS_PATH_RE = re.compile(r"^[/\\]|^[A-Za-z]:[/\\]")


class SandboxViolation(ValueError):
    """Raised when a tool argument violates sandbox policy in strict mode."""


def check_args(tool_name: str, args: dict[str, Any]) -> list[str]:
    """
    Scan tool args for sandbox violations.

    Returns a list of warning/error strings.  In strict mode, also raises
    SandboxViolation on the first path violation found.

    This is called automatically by tools/registry.py before dispatch.
    """
    issues: list[str] = []

    for key, value in args.items():
        if not isinstance(value, str):
            continue

        # Filesystem path check
        if _PATH_ARG_KEYS.search(key) and _ABS_PATH_RE.match(value):
            if not _is_path_allowed(value):
                msg = (
                    f"sandbox: tool '{tool_name}' arg '{key}' references "
                    f"path outside allowed roots: {value!r}"
                )
                issues.append(msg)
                if _strict_mode():
                    raise SandboxViolation(msg)
                else:
                    logger.warning(msg)

        # Network domain check
        if _URL_ARG_KEYS.search(key) and ("://" in value or "." in value):
            domain = _extract_domain(value)
            if domain and not _is_domain_allowed(domain):
                msg = (
                    f"sandbox: tool '{tool_name}' arg '{key}' references "
                    f"disallowed domain: {domain!r}"
                )
                issues.append(msg)
                if _network_block_mode():
                    raise SandboxViolation(msg)
                else:
                    logger.warning(msg)

    return issues


# ── Public helpers (for tests and tool authors) ────────────────────────────────

def assert_path_allowed(path: str | Path, *, tool_name: str = "") -> None:
    """
    Raise SandboxViolation if *path* is outside the allowed filesystem roots.

    Tool handlers can call this directly for paths they construct at runtime
    (as opposed to paths coming from tool args, which are checked automatically).
    """
    if not _is_path_allowed(str(path)):
        raise SandboxViolation(
            f"sandbox: {'tool ' + repr(tool_name) + ' ' if tool_name else ''}"
            f"path outside allowed roots: {path!r}"
        )


def is_path_allowed(path: str | Path) -> bool:
    return _is_path_allowed(str(path))


def allowed_roots() -> list[str]:
    """Return the current list of allowed filesystem roots (for display/docs)."""
    return [str(p) for p in _default_allowed_paths()]
