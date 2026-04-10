"""Unit tests for agent.lineage — control-plane lineage & cost tracking.

All filesystem I/O uses tmp_path; the in-memory cost register is cleared
between tests; no real HTTP calls or external dependencies.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_lineage_dir(tmp_path):
    """Context-manager: redirect _lineage_dir() to tmp_path/lineage."""
    from agent import lineage as _lin_mod

    def _fake_dir():
        d = tmp_path / "lineage"
        d.mkdir(parents=True, exist_ok=True)
        return d

    return patch.object(_lin_mod, "_lineage_dir", side_effect=_fake_dir)


# ---------------------------------------------------------------------------
# record_write / get_lineage
# ---------------------------------------------------------------------------

class TestRecordWrite:
    def test_creates_jsonl_file(self, tmp_path):
        from agent import lineage
        with _patch_lineage_dir(tmp_path):
            lineage.record_write("/tmp/foo.py", goal="test goal")
        files = list((tmp_path / "lineage").glob("*.jsonl"))
        assert len(files) == 1

    def test_entry_fields(self, tmp_path):
        from agent import lineage
        with _patch_lineage_dir(tmp_path):
            lineage.record_write("/tmp/foo.py", goal="build feature X",
                                 session_id="sess1", model="gpt-4")
            records = lineage.get_lineage("/tmp/foo.py")
        assert len(records) == 1
        r = records[0]
        assert r["goal"] == "build feature X"
        assert r["session_id"] == "sess1"
        assert r["model"] == "gpt-4"

    def test_path_is_resolved(self, tmp_path):
        from agent import lineage
        with _patch_lineage_dir(tmp_path):
            lineage.record_write("relative/path.txt", goal="x")
            records = lineage.get_lineage("relative/path.txt")
        # Resolved paths should match
        assert len(records) == 1

    def test_multiple_writes_same_file(self, tmp_path):
        from agent import lineage
        with _patch_lineage_dir(tmp_path):
            lineage.record_write("/tmp/a.py", goal="goal A")
            lineage.record_write("/tmp/a.py", goal="goal B")
            records = lineage.get_lineage("/tmp/a.py")
        # Most recent first; two entries
        assert len(records) == 2

    def test_different_files_separated(self, tmp_path):
        from agent import lineage
        with _patch_lineage_dir(tmp_path):
            lineage.record_write("/tmp/x.py", goal="goal X")
            lineage.record_write("/tmp/y.py", goal="goal Y")
            rx = lineage.get_lineage("/tmp/x.py")
            ry = lineage.get_lineage("/tmp/y.py")
        assert len(rx) == 1 and rx[0]["goal"] == "goal X"
        assert len(ry) == 1 and ry[0]["goal"] == "goal Y"

    def test_no_error_on_bad_dir(self):
        """record_write must never raise, even if lineage dir is unwritable."""
        from agent import lineage
        with patch.object(lineage, "_lineage_dir", side_effect=PermissionError("no")):
            lineage.record_write("/tmp/z.py", goal="whatever")  # must not raise

    def test_get_lineage_missing_file_returns_empty(self, tmp_path):
        from agent import lineage
        with _patch_lineage_dir(tmp_path):
            records = lineage.get_lineage("/nonexistent/file.py")
        assert records == []


# ---------------------------------------------------------------------------
# set_task_context / get_task_context  →  record_write fallback
# ---------------------------------------------------------------------------

class TestTaskContext:
    def test_set_and_get(self):
        from agent import lineage
        lineage.set_task_context("task-99", "do the thing", session_id="s1", model="m1")
        ctx = lineage.get_task_context("task-99")
        assert ctx["goal"] == "do the thing"
        assert ctx["session_id"] == "s1"
        assert ctx["model"] == "m1"

    def test_unknown_task_returns_empty(self):
        from agent import lineage
        ctx = lineage.get_task_context("no-such-task")
        assert ctx == {}

    def test_record_write_uses_task_context(self, tmp_path):
        from agent import lineage
        lineage.set_task_context("tid-abc", "inferred goal", session_id="s2", model="m2")
        with _patch_lineage_dir(tmp_path):
            lineage.record_write("/tmp/ctx.py", task_id="tid-abc")
            records = lineage.get_lineage("/tmp/ctx.py")
        assert len(records) == 1
        assert records[0]["goal"] == "inferred goal"
        assert records[0]["session_id"] == "s2"

    def test_explicit_goal_overrides_context(self, tmp_path):
        from agent import lineage
        lineage.set_task_context("tid-xyz", "context goal")
        with _patch_lineage_dir(tmp_path):
            lineage.record_write("/tmp/override.py", goal="explicit goal", task_id="tid-xyz")
            records = lineage.get_lineage("/tmp/override.py")
        assert records[0]["goal"] == "explicit goal"


# ---------------------------------------------------------------------------
# record_task_cost / get_session_costs / clear_session_costs
# ---------------------------------------------------------------------------

class TestSessionCosts:
    def setup_method(self):
        from agent import lineage
        lineage.clear_session_costs()

    def test_record_and_retrieve(self):
        from agent import lineage
        lineage.record_task_cost("Build auth", "gpt-4o", 1000, 200)
        costs = lineage.get_session_costs()
        assert len(costs) == 1
        c = costs[0]
        assert c["label"] == "Build auth"
        assert c["model"] == "gpt-4o"
        assert c["input_tokens"] == 1000
        assert c["output_tokens"] == 200

    def test_multiple_entries_accumulated(self):
        from agent import lineage
        lineage.record_task_cost("Task A", "m1", 100, 50)
        lineage.record_task_cost("Task B", "m2", 200, 80)
        costs = lineage.get_session_costs()
        assert len(costs) == 2

    def test_clear_resets_list(self):
        from agent import lineage
        lineage.record_task_cost("T", "m", 1, 1)
        lineage.clear_session_costs()
        assert lineage.get_session_costs() == []

    def test_snapshot_is_copy(self):
        """Mutating the returned list must not affect internal state."""
        from agent import lineage
        lineage.record_task_cost("T", "m", 1, 1)
        snap = lineage.get_session_costs()
        snap.clear()
        assert len(lineage.get_session_costs()) == 1

    def test_cost_field_type(self):
        from agent import lineage
        lineage.record_task_cost("T", "unknown-model-xyz", 10, 10)
        costs = lineage.get_session_costs()
        # cost_usd is either None (unknown model) or a float
        c = costs[0]["cost_usd"]
        assert c is None or isinstance(c, float)

    def test_duration_stored(self):
        from agent import lineage
        lineage.record_task_cost("T", "m", 1, 1, duration_seconds=3.5)
        assert lineage.get_session_costs()[0]["duration_seconds"] == pytest.approx(3.5)

    def test_status_stored(self):
        from agent import lineage
        lineage.record_task_cost("T", "m", 1, 1, status="failed")
        assert lineage.get_session_costs()[0]["status"] == "failed"


# ---------------------------------------------------------------------------
# get_all_lineage
# ---------------------------------------------------------------------------

class TestGetAllLineage:
    def test_returns_entries_from_today(self, tmp_path):
        from agent import lineage
        with _patch_lineage_dir(tmp_path):
            lineage.record_write("/tmp/a.py", goal="A")
            lineage.record_write("/tmp/b.py", goal="B")
            all_recs = lineage.get_all_lineage(days=1)
        assert len(all_recs) == 2

    def test_empty_when_no_writes(self, tmp_path):
        from agent import lineage
        with _patch_lineage_dir(tmp_path):
            all_recs = lineage.get_all_lineage(days=1)
        assert all_recs == []

    def test_corrupt_lines_skipped(self, tmp_path):
        from agent import lineage as lin_mod
        with _patch_lineage_dir(tmp_path):
            # Write a good entry then inject a bad line
            lin_mod.record_write("/tmp/ok.py", goal="ok")
            log = lin_mod._log_path()
            with open(log, "a") as f:
                f.write("NOT JSON\n")
            recs = lin_mod.get_all_lineage(days=1)
        # Only the good entry returned; bad line silently skipped
        assert len(recs) == 1
        assert recs[0]["goal"] == "ok"
