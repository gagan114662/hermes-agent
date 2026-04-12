"""Guardrails — three protection layers for harness-controlled agent sessions.

CostGuard     — tracks cumulative spend, raises CostLimitExceeded when over budget.
CommandGuard  — blocks dangerous shell commands before they reach the terminal tool.
ApprovalGate  — pauses and requests human approval for high-impact operations.

Integration points
------------------
- CostGuard.record_usage() is called from SessionOrchestrator after each
  AIAgent.run_conversation() using the returned usage dict.
- CommandGuard.check() is wired into AIAgent's tool_start_callback so it runs
  before every terminal tool call.
- ApprovalGate.requires_approval() is consulted by CommandGuard; when True,
  CommandGuard raises CommandBlocked with requires_approval=True so the
  orchestrator can prompt the user and retry.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from tools.approval import detect_dangerous_command

logger = logging.getLogger(__name__)


# ── Exceptions ────────────────────────────────────────────────────────

class CostLimitExceeded(Exception):
    """Raised when cumulative harness spend exceeds max_cost_dollars."""


class CommandBlocked(Exception):
    """Raised by CommandGuard when a command violates guardrail policy.

    Attributes
    ----------
    command           — the blocked command string
    reason            — human-readable explanation
    requires_approval — True if block can be overridden with human approval
    """

    def __init__(self, command: str, reason: str, requires_approval: bool = False) -> None:
        super().__init__(f"Command blocked — {reason}: {command!r}")
        self.command = command
        self.reason = reason
        self.requires_approval = requires_approval


# ── CostGuard ─────────────────────────────────────────────────────────

# Approximate USD pricing per 1M tokens for common models.
# Keyed by model slug fragment; falls back to a conservative default.
_PRICE_TABLE: dict[str, tuple[float, float]] = {
    # (input $/1M, output $/1M)
    "claude-opus":    (15.0,  75.0),
    "claude-sonnet":  (3.0,   15.0),
    "claude-haiku":   (0.25,  1.25),
    "gpt-4o":         (5.0,   15.0),
    "gpt-4":          (30.0,  60.0),
    "gpt-3.5":        (0.5,   1.5),
    "gemini-1.5-pro": (3.5,   10.5),
}
_DEFAULT_PRICE = (3.0, 15.0)   # conservative fallback


def _price_for_model(model: str) -> tuple[float, float]:
    model_lower = model.lower()
    for fragment, prices in _PRICE_TABLE.items():
        if fragment in model_lower:
            return prices
    return _DEFAULT_PRICE


class CostGuard:
    """Tracks token usage and raises CostLimitExceeded when budget is hit."""

    def __init__(self, max_cost_dollars: float) -> None:
        self.max_cost_dollars = max_cost_dollars
        self.cumulative_cost: float = 0.0
        self.session_costs: list[float] = []

    def record_session_cost(self, cost_usd: float) -> None:
        """Add a session cost and raise if limit exceeded."""
        self.cumulative_cost += cost_usd
        self.session_costs.append(cost_usd)
        logger.debug("CostGuard: +$%.4f → total $%.4f / $%.2f",
                     cost_usd, self.cumulative_cost, self.max_cost_dollars)
        if self.cumulative_cost > self.max_cost_dollars:
            raise CostLimitExceeded(
                f"Cumulative cost ${self.cumulative_cost:.2f} exceeds limit "
                f"${self.max_cost_dollars:.2f}"
            )

    def record_usage(self, usage: dict, model: str = "") -> None:
        """Estimate cost from a token usage dict and record it."""
        input_price, output_price = _price_for_model(model)
        input_tok = usage.get("input_tokens", usage.get("prompt_tokens", 0))
        output_tok = usage.get("output_tokens", usage.get("completion_tokens", 0))
        cache_read = usage.get("cache_read_tokens", 0)
        input_tok += cache_read
        cost = (input_tok * input_price + output_tok * output_price) / 1_000_000
        self.record_session_cost(cost)


# ── CommandGuard ──────────────────────────────────────────────────────

_ALWAYS_BLOCKED: list[tuple[str, str]] = [
    (r"rm\s+-rf\s+/", "rm -rf root filesystem"),
    (r"rm\s+-rf\s+~", "rm -rf home directory"),
    (r"chmod\s+777\s+/", "world-writable root"),
    (r"drop\s+database\b", "SQL DROP DATABASE"),
    (r"truncate\s+table\b", "SQL TRUNCATE TABLE"),
    (r"git\s+push\s+--force\b", "force push to git remote"),
    (r"git\s+push\s+-f\b", "force push to git remote"),
    (r">\s*/dev/sd[a-z]", "write to raw block device"),
    (r"mkfs\.", "filesystem format"),
]

_COMPILED_BLOCKED = [(re.compile(p, re.IGNORECASE), desc) for p, desc in _ALWAYS_BLOCKED]


class CommandGuard:
    """Pre-flight check for shell commands before they reach the terminal tool."""

    def __init__(
        self,
        forbidden_paths: Optional[list[str]] = None,
        extra_blocked_patterns: Optional[list[tuple[str, str]]] = None,
    ) -> None:
        self._forbidden_paths = [str(p) for p in (forbidden_paths or [])]
        self._extra = [
            (re.compile(p, re.IGNORECASE), desc)
            for p, desc in (extra_blocked_patterns or [])
        ]

    def check(self, command: str) -> None:
        """Raise CommandBlocked if the command violates policy."""
        # 1. Always-blocked patterns
        for pattern, desc in _COMPILED_BLOCKED:
            if pattern.search(command):
                raise CommandBlocked(command, desc, requires_approval=False)

        # 2. Extra caller-supplied patterns
        for pattern, desc in self._extra:
            if pattern.search(command):
                raise CommandBlocked(command, desc, requires_approval=False)

        # 3. Forbidden path prefixes
        for path in self._forbidden_paths:
            if path and path in command:
                raise CommandBlocked(
                    command,
                    f"touches forbidden path {path!r}",
                    requires_approval=False,
                )

        # 4. Delegate to existing approval system for pattern detection
        is_dangerous, pattern_key, description = detect_dangerous_command(command)
        if is_dangerous:
            raise CommandBlocked(command, description, requires_approval=True)


# ── ApprovalGate ──────────────────────────────────────────────────────

# Commands that require human approval when no explicit list is given
_DEFAULT_APPROVAL_PREFIXES = [
    "git push",
    "npm publish",
    "terraform apply",
    "terraform destroy",
    "kubectl delete",
    "aws s3 rm",
    "gcloud deploy",
]


class ApprovalGate:
    """Determines whether a command needs human sign-off before running.

    When approval_required_commands is None, the default list is used.
    When it is an explicit list (even empty), only that list is used.
    """

    def __init__(self, approval_required_commands: Optional[list[str]] = None) -> None:
        if approval_required_commands is None:
            self._required = list(_DEFAULT_APPROVAL_PREFIXES)
        else:
            self._required = list(approval_required_commands)

    def requires_approval(self, command: str) -> bool:
        cmd_lower = command.strip().lower()
        return any(cmd_lower.startswith(req.lower()) for req in self._required)
