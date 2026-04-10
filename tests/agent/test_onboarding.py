"""Unit tests for agent.onboarding — 3-3-3 journey-stage tracker.

All filesystem I/O redirected to tmp_path via monkeypatching.
No real ~/.hermes writes; no external dependencies.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_state_path(tmp_path):
    """Redirect _state_path() to tmp_path/onboarding.json."""
    from agent import onboarding as _ob

    return patch.object(
        _ob, "_state_path",
        return_value=tmp_path / "onboarding.json",
    )


# ---------------------------------------------------------------------------
# record_session
# ---------------------------------------------------------------------------

class TestRecordSession:
    def test_first_session_returns_stage1(self, tmp_path):
        from agent import onboarding
        with _patch_state_path(tmp_path):
            s = onboarding.record_session()
        assert s.stage == 1
        assert s.session_count == 1
        assert s.label == "day-1"

    def test_increments_on_repeated_calls(self, tmp_path):
        from agent import onboarding
        with _patch_state_path(tmp_path):
            for _ in range(5):
                s = onboarding.record_session()
        assert s.session_count == 5

    def test_session3_still_stage1(self, tmp_path):
        from agent import onboarding
        with _patch_state_path(tmp_path):
            for _ in range(3):
                s = onboarding.record_session()
        assert s.stage == 1

    def test_session4_becomes_stage2(self, tmp_path):
        from agent import onboarding
        with _patch_state_path(tmp_path):
            for _ in range(4):
                s = onboarding.record_session()
        assert s.stage == 2
        assert s.label == "week-2"

    def test_session14_still_stage2(self, tmp_path):
        from agent import onboarding
        with _patch_state_path(tmp_path):
            for _ in range(14):
                s = onboarding.record_session()
        assert s.stage == 2

    def test_session15_becomes_stage3(self, tmp_path):
        from agent import onboarding
        with _patch_state_path(tmp_path):
            for _ in range(15):
                s = onboarding.record_session()
        assert s.stage == 3
        assert s.label == "month-2+"

    def test_persists_between_calls(self, tmp_path):
        """Counter survives across separate record_session calls (no in-memory state)."""
        from agent import onboarding
        with _patch_state_path(tmp_path):
            onboarding.record_session()
            onboarding.record_session()
            s = onboarding.record_session()
        assert s.session_count == 3

    def test_creates_json_file(self, tmp_path):
        from agent import onboarding
        with _patch_state_path(tmp_path):
            onboarding.record_session()
        assert (tmp_path / "onboarding.json").exists()

    def test_first_session_ts_set(self, tmp_path):
        from agent import onboarding
        with _patch_state_path(tmp_path):
            onboarding.record_session()
            state = onboarding.get_onboarding_state()
        assert state["first_session_ts"] is not None

    def test_first_session_ts_not_overwritten(self, tmp_path):
        from agent import onboarding
        with _patch_state_path(tmp_path):
            onboarding.record_session()
            first = onboarding.get_onboarding_state()["first_session_ts"]
            onboarding.record_session()
            onboarding.record_session()
            later = onboarding.get_onboarding_state()["first_session_ts"]
        assert first == later


# ---------------------------------------------------------------------------
# get_journey_stage
# ---------------------------------------------------------------------------

class TestGetJourneyStage:
    def test_no_sessions_returns_stage1(self, tmp_path):
        from agent import onboarding
        with _patch_state_path(tmp_path):
            s = onboarding.get_journey_stage()
        assert s.stage == 1
        assert s.session_count == 0

    def test_stage_fields_populated(self, tmp_path):
        from agent import onboarding
        with _patch_state_path(tmp_path):
            for _ in range(6):
                onboarding.record_session()
            s = onboarding.get_journey_stage()
        assert s.stage == 2
        assert s.next_command == "/skillnew"
        assert s.headline
        assert s.tip

    def test_stage3_next_command_is_costmap(self, tmp_path):
        from agent import onboarding
        with _patch_state_path(tmp_path):
            for _ in range(15):
                onboarding.record_session()
            s = onboarding.get_journey_stage()
        assert s.next_command == "/costmap"

    def test_stage1_next_command_is_specnew(self, tmp_path):
        from agent import onboarding
        with _patch_state_path(tmp_path):
            s = onboarding.get_journey_stage()
        assert s.next_command == "/specnew"


# ---------------------------------------------------------------------------
# reset_onboarding
# ---------------------------------------------------------------------------

class TestResetOnboarding:
    def test_reset_clears_counter(self, tmp_path):
        from agent import onboarding
        with _patch_state_path(tmp_path):
            for _ in range(10):
                onboarding.record_session()
            onboarding.reset_onboarding()
            s = onboarding.get_journey_stage()
        assert s.session_count == 0

    def test_reset_removes_file(self, tmp_path):
        from agent import onboarding
        with _patch_state_path(tmp_path):
            onboarding.record_session()
            onboarding.reset_onboarding()
        assert not (tmp_path / "onboarding.json").exists()

    def test_reset_on_fresh_state_no_error(self, tmp_path):
        from agent import onboarding
        with _patch_state_path(tmp_path):
            onboarding.reset_onboarding()  # should not raise


# ---------------------------------------------------------------------------
# get_onboarding_state
# ---------------------------------------------------------------------------

class TestGetOnboardingState:
    def test_returns_dict(self, tmp_path):
        from agent import onboarding
        with _patch_state_path(tmp_path):
            state = onboarding.get_onboarding_state()
        assert isinstance(state, dict)
        assert "session_count" in state

    def test_snapshot_is_copy(self, tmp_path):
        from agent import onboarding
        with _patch_state_path(tmp_path):
            onboarding.record_session()
            s1 = onboarding.get_onboarding_state()
            s1["session_count"] = 9999
            s2 = onboarding.get_onboarding_state()
        assert s2["session_count"] == 1


# ---------------------------------------------------------------------------
# Corrupt state file resilience
# ---------------------------------------------------------------------------

class TestCorruptState:
    def test_corrupt_json_falls_back_to_zero(self, tmp_path):
        from agent import onboarding
        (tmp_path / "onboarding.json").write_text("NOT JSON", encoding="utf-8")
        with _patch_state_path(tmp_path):
            s = onboarding.get_journey_stage()
        assert s.session_count == 0
