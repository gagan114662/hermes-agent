"""Tests for agent/spec_engine.py — HermesSpec parsing, task extraction, file ops."""
from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FULL_SPEC = textwrap.dedent("""\
    ---
    hermes_spec: "1.0"
    name: crm-tool
    slug: crm-tool
    status: draft
    created: 2026-04-10
    owner: gagan114662
    tech_stack: [python, sqlite]
    tags: [crm, sales]
    ---

    ## Overview

    ### What
    A CRM tool for tracking sales prospects.

    ### Why
    Replace manual spreadsheets with automated follow-ups.

    ### Success Metrics
    - Under 5 seconds to log a prospect
    - Daily digest of follow-ups

    ## Architecture

    ### Components
    - `tools/crm_tool.py` — CRUD operations for prospects

    ### Data Flow
    User → crm_save → JSON store → crm_find → Display

    ## Data Models

    Prospect: id, name, company, status, next_action, notes

    ## Workflows

    ### Log New Prospect
    1. User says "add prospect"
    2. Tool extracts fields
    3. Saves and confirms

    ## Security

    - Local storage only
    - No PII leaves the machine

    ## Tasks

    ```yaml
    tasks:
      - id: t1
        title: "Create crm_tool.py with CRUD"
        agent_type: general
        goal: "Create tools/crm_tool.py implementing crm_save, crm_find, crm_log, crm_deal."
        files: ["tools/crm_tool.py"]
        depends_on: []
        status: pending

      - id: t2
        title: "Write tests for CRM tool"
        agent_type: spec-test-writer
        goal: "Write discriminating tests for the CRM spec contract."
        files: ["tests/test_crm.py"]
        depends_on: [t1]
        status: pending

      - id: t3
        title: "Already done task"
        agent_type: general
        goal: "This was already done."
        files: []
        depends_on: []
        status: complete
    ```
""")

MINIMAL_SPEC = textwrap.dedent("""\
    ---
    hermes_spec: "1.0"
    name: simple
    slug: simple
    status: draft
    created: 2026-01-01
    ---

    ## Overview

    Simple overview.

    ## Tasks

    ```yaml
    tasks:
      - id: t1
        title: "Do the thing"
        agent_type: general
        goal: "Do the thing."
        files: []
        depends_on: []
        status: pending
    ```
""")

NO_TASKS_SPEC = textwrap.dedent("""\
    ---
    hermes_spec: "1.0"
    name: no-tasks
    slug: no-tasks
    status: draft
    created: 2026-01-01
    ---

    ## Overview

    A spec with no tasks section yet.
""")


# ---------------------------------------------------------------------------
# parse_spec
# ---------------------------------------------------------------------------

class TestParseSpec:
    def test_parses_frontmatter_name(self):
        from agent.spec_engine import parse_spec
        spec = parse_spec(FULL_SPEC)
        assert spec.name == "crm-tool"

    def test_parses_frontmatter_status(self):
        from agent.spec_engine import parse_spec
        spec = parse_spec(FULL_SPEC)
        assert spec.status == "draft"

    def test_parses_tech_stack(self):
        from agent.spec_engine import parse_spec
        spec = parse_spec(FULL_SPEC)
        assert "python" in spec.tech_stack
        assert "sqlite" in spec.tech_stack

    def test_parses_tags(self):
        from agent.spec_engine import parse_spec
        spec = parse_spec(FULL_SPEC)
        assert "crm" in spec.tags

    def test_parses_overview_section(self):
        from agent.spec_engine import parse_spec
        spec = parse_spec(FULL_SPEC)
        assert "A CRM tool" in spec.overview

    def test_parses_architecture_section(self):
        from agent.spec_engine import parse_spec
        spec = parse_spec(FULL_SPEC)
        assert "architecture" in spec.sections

    def test_spec_with_no_frontmatter(self):
        from agent.spec_engine import parse_spec
        content = "## Overview\n\nJust overview.\n"
        spec = parse_spec(content)
        assert spec.status == "draft"  # default
        assert "overview" in spec.sections

    def test_spec_path_stored(self):
        from agent.spec_engine import parse_spec
        path = Path("/fake/crm-tool.md")
        spec = parse_spec(FULL_SPEC, path=path)
        assert spec.path == path


# ---------------------------------------------------------------------------
# extract_tasks
# ---------------------------------------------------------------------------

class TestExtractTasks:
    def test_extracts_task_count(self):
        from agent.spec_engine import extract_tasks
        tasks = extract_tasks(FULL_SPEC)
        assert len(tasks) == 3

    def test_task_has_required_fields(self):
        from agent.spec_engine import extract_tasks
        tasks = extract_tasks(FULL_SPEC)
        t1 = tasks[0]
        assert t1["id"] == "t1"
        assert t1["title"] == "Create crm_tool.py with CRUD"
        assert t1["agent_type"] == "general"
        assert "crm_save" in t1["goal"]

    def test_task_depends_on_preserved(self):
        from agent.spec_engine import extract_tasks
        tasks = extract_tasks(FULL_SPEC)
        t2 = tasks[1]
        assert "t1" in t2["depends_on"]

    def test_task_status_preserved(self):
        from agent.spec_engine import extract_tasks
        tasks = extract_tasks(FULL_SPEC)
        assert tasks[2]["status"] == "complete"

    def test_returns_empty_for_no_tasks_section(self):
        from agent.spec_engine import extract_tasks
        tasks = extract_tasks(NO_TASKS_SPEC)
        assert tasks == []

    def test_returns_empty_for_empty_string(self):
        from agent.spec_engine import extract_tasks
        assert extract_tasks("") == []


# ---------------------------------------------------------------------------
# HermesSpec.tasks / pending_tasks / completed_tasks
# ---------------------------------------------------------------------------

class TestHermesSpecTaskProperties:
    def test_tasks_property(self):
        from agent.spec_engine import parse_spec
        spec = parse_spec(FULL_SPEC)
        assert len(spec.tasks) == 3

    def test_pending_tasks_excludes_complete(self):
        from agent.spec_engine import parse_spec
        spec = parse_spec(FULL_SPEC)
        pending = spec.pending_tasks
        assert len(pending) == 2
        assert all(t["status"] == "pending" for t in pending)

    def test_completed_tasks(self):
        from agent.spec_engine import parse_spec
        spec = parse_spec(FULL_SPEC)
        done = spec.completed_tasks
        assert len(done) == 1
        assert done[0]["id"] == "t3"

    def test_no_tasks_spec(self):
        from agent.spec_engine import parse_spec
        spec = parse_spec(NO_TASKS_SPEC)
        assert spec.tasks == []
        assert spec.pending_tasks == []


# ---------------------------------------------------------------------------
# find_spec
# ---------------------------------------------------------------------------

class TestFindSpec:
    def test_finds_by_exact_name(self, tmp_path):
        from agent.spec_engine import find_spec
        f = tmp_path / "crm-tool.md"
        f.write_text(FULL_SPEC, encoding="utf-8")

        with patch("agent.spec_engine.get_specs_dir", return_value=tmp_path):
            result = find_spec("crm-tool")

        assert result == f

    def test_returns_none_when_missing(self, tmp_path):
        from agent.spec_engine import find_spec
        with patch("agent.spec_engine.get_specs_dir", return_value=tmp_path):
            result = find_spec("nonexistent")
        assert result is None

    def test_finds_with_underscore_slug(self, tmp_path):
        from agent.spec_engine import find_spec
        f = tmp_path / "crm-tool.md"
        f.write_text(FULL_SPEC, encoding="utf-8")

        with patch("agent.spec_engine.get_specs_dir", return_value=tmp_path):
            result = find_spec("crm_tool")  # underscore should match dash

        assert result == f

    def test_returns_none_when_dir_missing(self, tmp_path):
        from agent.spec_engine import find_spec
        with patch("agent.spec_engine.get_specs_dir", return_value=tmp_path / "nonexistent"):
            result = find_spec("anything")
        assert result is None


# ---------------------------------------------------------------------------
# list_specs
# ---------------------------------------------------------------------------

class TestListSpecs:
    def test_lists_all_specs(self, tmp_path):
        from agent.spec_engine import list_specs
        (tmp_path / "crm-tool.md").write_text(FULL_SPEC, encoding="utf-8")
        (tmp_path / "simple.md").write_text(MINIMAL_SPEC, encoding="utf-8")

        with patch("agent.spec_engine.get_specs_dir", return_value=tmp_path):
            specs = list_specs()

        assert len(specs) == 2
        names = [s.name for s in specs]
        assert "crm-tool" in names
        assert "simple" in names

    def test_returns_empty_when_dir_missing(self, tmp_path):
        from agent.spec_engine import list_specs
        with patch("agent.spec_engine.get_specs_dir", return_value=tmp_path / "no"):
            specs = list_specs()
        assert specs == []

    def test_sorted_alphabetically(self, tmp_path):
        from agent.spec_engine import list_specs
        (tmp_path / "zzz.md").write_text(MINIMAL_SPEC.replace("simple", "zzz"), encoding="utf-8")
        (tmp_path / "aaa.md").write_text(MINIMAL_SPEC.replace("simple", "aaa"), encoding="utf-8")

        with patch("agent.spec_engine.get_specs_dir", return_value=tmp_path):
            specs = list_specs()

        assert specs[0].name == "aaa"
        assert specs[1].name == "zzz"


# ---------------------------------------------------------------------------
# save_spec
# ---------------------------------------------------------------------------

class TestSaveSpec:
    def test_saves_file(self, tmp_path):
        from agent.spec_engine import save_spec
        with patch("agent.spec_engine.ensure_specs_dir", return_value=tmp_path):
            path = save_spec(FULL_SPEC, "crm-tool")

        assert path.exists()
        assert path.read_text(encoding="utf-8") == FULL_SPEC

    def test_slug_normalised(self, tmp_path):
        from agent.spec_engine import save_spec
        with patch("agent.spec_engine.ensure_specs_dir", return_value=tmp_path):
            path = save_spec(FULL_SPEC, "My New Feature")

        assert path.name == "my-new-feature.md"

    def test_overwrites_existing(self, tmp_path):
        from agent.spec_engine import save_spec
        with patch("agent.spec_engine.ensure_specs_dir", return_value=tmp_path):
            save_spec("first version", "test")
            save_spec("second version", "test")
            path = tmp_path / "test.md"

        assert path.read_text(encoding="utf-8") == "second version"


# ---------------------------------------------------------------------------
# mark_task_complete
# ---------------------------------------------------------------------------

class TestMarkTaskComplete:
    def test_marks_pending_as_complete(self, tmp_path):
        from agent.spec_engine import mark_task_complete
        f = tmp_path / "spec.md"
        f.write_text(FULL_SPEC, encoding="utf-8")

        result = mark_task_complete(f, "t1")

        assert result is True
        content = f.read_text(encoding="utf-8")
        # t1 should now be complete
        assert "status: complete" in content

    def test_returns_false_for_missing_task_id(self, tmp_path):
        from agent.spec_engine import mark_task_complete
        f = tmp_path / "spec.md"
        f.write_text(FULL_SPEC, encoding="utf-8")

        result = mark_task_complete(f, "t999")

        assert result is False

    def test_does_not_corrupt_other_tasks(self, tmp_path):
        from agent.spec_engine import mark_task_complete
        from agent.spec_engine import extract_tasks
        f = tmp_path / "spec.md"
        f.write_text(FULL_SPEC, encoding="utf-8")

        mark_task_complete(f, "t1")
        tasks = extract_tasks(f.read_text(encoding="utf-8"))

        # t2 should still be pending
        t2 = next(t for t in tasks if t["id"] == "t2")
        assert t2["status"] == "pending"


# ---------------------------------------------------------------------------
# make_blank_spec
# ---------------------------------------------------------------------------

class TestMakeBlankSpec:
    def test_includes_name(self):
        from agent.spec_engine import make_blank_spec
        result = make_blank_spec("My Feature")
        assert "My Feature" in result

    def test_slug_is_kebab_case(self):
        from agent.spec_engine import make_blank_spec
        result = make_blank_spec("My Cool Feature")
        assert "my-cool-feature" in result

    def test_includes_all_required_sections(self):
        from agent.spec_engine import make_blank_spec
        result = make_blank_spec("test")
        for section in ["Overview", "Architecture", "Data Models", "Workflows", "Security", "Tasks"]:
            assert section in result

    def test_includes_today_date(self):
        from agent.spec_engine import make_blank_spec
        from datetime import date
        result = make_blank_spec("test")
        assert str(date.today()) in result
