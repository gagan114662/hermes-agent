#!/usr/bin/env python3
"""
Pre-commit secret scanner for Hermes Agent.

Scans git-staged files (or given paths) for patterns that look like leaked
credentials.  Returns exit code 1 if any findings are detected so the commit
is blocked.

Usage:
    # As a pre-commit hook (scans staged files automatically):
    python scripts/scan_secrets.py

    # Scan specific files manually:
    python scripts/scan_secrets.py path/to/file.py path/to/config.yaml

    # Scan all tracked files (audit mode):
    python scripts/scan_secrets.py --all

Install as a git hook (one-time):
    bash scripts/install_hooks.sh
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

# ── patterns ──────────────────────────────────────────────────────────────────
# Each entry: (compiled_regex, human_label)
# Ordered most-specific first to avoid duplicate reports.

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Provider-prefixed keys
    (re.compile(r"sk-ant-(?:oat|api)[A-Za-z0-9\-_]{20,}"), "Anthropic key"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "OpenAI/generic sk- key"),
    (re.compile(r"ghp_[A-Za-z0-9]{36,}"), "GitHub personal access token"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "GitHub fine-grained PAT"),
    (re.compile(r"hf_[A-Za-z0-9]{34,}"), "Hugging Face token"),
    (re.compile(r"xox[baprs]-[0-9A-Za-z\-]{10,}"), "Slack token"),
    (re.compile(r"fal_[A-Za-z0-9_\-]{20,}"), "fal.ai key"),
    (re.compile(r"[0-9]{8,12}:[A-Za-z0-9_\-]{32,}"), "Telegram bot token"),
    (re.compile(r"AIza[A-Za-z0-9_\-]{35}"), "Google API key"),
    (re.compile(r"ya29\.[A-Za-z0-9_\-]{50,}"), "Google OAuth token"),
    # Private key blocks
    (
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
        "PEM private key",
    ),
    # Generic high-entropy assignments in .env / config style
    (
        re.compile(
            r'(?i)(?:api[_-]?key|apikey|auth[_-]?token|access[_-]?token'
            r'|secret[_-]?key|private[_-]?key|client[_-]?secret'
            r'|bot[_-]?token)\s*[=:]\s*["\']?([A-Za-z0-9+/=_\-]{20,})',
        ),
        "generic credential assignment",
    ),
    # Authorization headers in code / test fixtures
    (
        re.compile(r'(?i)Authorization\s*:\s*(?:Bearer|Basic|Token)\s+[A-Za-z0-9+/=_\-]{16,}'),
        "hardcoded Authorization header",
    ),
]

# Files that should never be scanned (binary, generated, etc.)
_SKIP_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg",
        ".pdf", ".zip", ".tar", ".gz", ".bz2", ".whl", ".egg",
        ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe",
        ".lock",  # lock files contain hashes, not secrets
    }
)

# Files whose names often look like secrets but aren't
_SKIP_FILENAMES: frozenset[str] = frozenset(
    {
        ".env.example",
        "agent/redact.py",    # intentionally contains patterns for scanning
        "scripts/scan_secrets.py",  # this file — patterns in docstrings/comments
    }
)


# ── result type ───────────────────────────────────────────────────────────────


class Finding(NamedTuple):
    file: str
    line: int
    label: str
    snippet: str  # redacted for safety


def _redact(match: str) -> str:
    """Show first 6 and last 4 chars, mask the middle."""
    if len(match) <= 12:
        return "***"
    return match[:6] + "..." + match[-4:]


# ── scanner ───────────────────────────────────────────────────────────────────


def scan_file(path: Path) -> list[Finding]:
    """Scan a single file and return all findings."""
    if path.suffix.lower() in _SKIP_EXTENSIONS:
        return []

    # Normalise to repo-relative for skip checks
    try:
        rel = str(path.relative_to(Path.cwd()))
    except ValueError:
        rel = str(path)

    if rel in _SKIP_FILENAMES or path.name in _SKIP_FILENAMES:
        return []

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    findings: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for pattern, label in _PATTERNS:
            m = pattern.search(line)
            if m:
                # Use the first captured group if present, else the whole match
                raw = m.group(1) if m.lastindex else m.group(0)
                findings.append(Finding(rel, lineno, label, _redact(raw)))
                break  # one finding per line per file

    return findings


def get_staged_files() -> list[Path]:
    """Return paths of files staged for commit."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    return [Path(p) for p in result.stdout.splitlines() if p]


def get_all_tracked_files() -> list[Path]:
    """Return all files tracked by git (for full-repo audit)."""
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    return [Path(p) for p in result.stdout.splitlines() if p]


# ── main ──────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    if "--all" in args:
        files = get_all_tracked_files()
        mode = "full repo audit"
    elif args:
        files = [Path(a) for a in args if not a.startswith("--")]
        mode = "manual"
    else:
        files = get_staged_files()
        mode = "staged files"

    if not files:
        print(f"scan_secrets: no files to scan ({mode})")
        return 0

    all_findings: list[Finding] = []
    for f in files:
        all_findings.extend(scan_file(f))

    if not all_findings:
        print(f"scan_secrets: ✓ no secrets detected ({len(files)} files, {mode})")
        return 0

    # Report findings
    print(f"\n⚠️  scan_secrets: SECRETS DETECTED in {mode}\n")
    for finding in all_findings:
        print(f"  {finding.file}:{finding.line}  [{finding.label}]  value={finding.snippet}")

    print(
        f"\n  {len(all_findings)} finding(s) across "
        f"{len({f.file for f in all_findings})} file(s)."
    )
    print("  Move secrets to ~/.hermes/.env or use: hermes secrets set KEY VALUE")
    print("  To skip (if this is a false positive): git commit --no-verify\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
