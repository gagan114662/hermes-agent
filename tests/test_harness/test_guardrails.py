# tests/test_harness/test_guardrails.py
import pytest
from unittest.mock import MagicMock, patch
from harness.guardrails import (
    CostGuard, CommandGuard, ApprovalGate,
    CostLimitExceeded, CommandBlocked,
)


# ── CostGuard ─────────────────────────────────────────────────────────

def test_cost_guard_allows_within_limit():
    guard = CostGuard(max_cost_dollars=10.0)
    guard.record_session_cost(3.0)
    guard.record_session_cost(3.0)
    # 6.0 < 10.0 → no raise


def test_cost_guard_raises_when_exceeded():
    guard = CostGuard(max_cost_dollars=5.0)
    guard.record_session_cost(3.0)
    with pytest.raises(CostLimitExceeded) as exc_info:
        guard.record_session_cost(3.0)
    assert "6.0" in str(exc_info.value) or "5.0" in str(exc_info.value)


def test_cost_guard_tracks_cumulative():
    guard = CostGuard(max_cost_dollars=100.0)
    guard.record_session_cost(10.0)
    guard.record_session_cost(20.0)
    assert guard.cumulative_cost == 30.0


def test_cost_guard_from_usage_dict():
    guard = CostGuard(max_cost_dollars=50.0)
    usage = {"input_tokens": 10_000, "output_tokens": 1_000}
    guard.record_usage(usage, model="anthropic/claude-sonnet-4-6")
    assert guard.cumulative_cost > 0


# ── CommandGuard ──────────────────────────────────────────────────────

def test_command_guard_blocks_rm_rf():
    guard = CommandGuard(forbidden_paths=[])
    with pytest.raises(CommandBlocked, match="rm -rf"):
        guard.check("rm -rf /")


def test_command_guard_blocks_forbidden_path(tmp_path):
    guard = CommandGuard(forbidden_paths=[str(tmp_path)])
    with pytest.raises(CommandBlocked):
        guard.check(f"echo hello > {tmp_path}/secret.txt")


def test_command_guard_allows_safe_command():
    guard = CommandGuard(forbidden_paths=[])
    guard.check("ls -la /tmp")  # Should not raise


def test_command_guard_blocks_force_push():
    guard = CommandGuard(forbidden_paths=[])
    with pytest.raises(CommandBlocked):
        guard.check("git push --force origin main")


def test_command_guard_blocks_drop_database():
    guard = CommandGuard(forbidden_paths=[])
    with pytest.raises(CommandBlocked):
        guard.check("DROP DATABASE production;")


# ── ApprovalGate ──────────────────────────────────────────────────────

def test_approval_gate_no_required_commands():
    gate = ApprovalGate(approval_required_commands=[])
    assert gate.requires_approval("git push origin main") is False


def test_approval_gate_flags_matching_command():
    gate = ApprovalGate(approval_required_commands=["git push", "npm publish"])
    assert gate.requires_approval("git push origin main") is True
    assert gate.requires_approval("npm publish --dry-run") is True
    assert gate.requires_approval("ls -la") is False


def test_approval_gate_default_commands():
    """terraform apply, git push, npm publish always require approval."""
    gate = ApprovalGate(approval_required_commands=None)
    assert gate.requires_approval("terraform apply") is True
    assert gate.requires_approval("git push origin") is True
    assert gate.requires_approval("npm publish") is True
