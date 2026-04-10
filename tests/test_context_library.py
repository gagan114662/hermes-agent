"""Tests for agent/context_library.py — Context Library loader."""
from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")


# ---------------------------------------------------------------------------
# _parse_frontmatter_agents
# ---------------------------------------------------------------------------

class TestParseFrontmatterAgents:
    def test_inline_list(self):
        from agent.context_library import _parse_frontmatter_agents
        content = "---\nagents: [verify, spec-test-writer]\n---\nsome content"
        assert _parse_frontmatter_agents(content) == ["verify", "spec-test-writer"]

    def test_block_list(self):
        from agent.context_library import _parse_frontmatter_agents
        content = "---\nagents:\n  - verify\n  - plan\n---\nsome content"
        assert _parse_frontmatter_agents(content) == ["verify", "plan"]

    def test_no_frontmatter_returns_none(self):
        from agent.context_library import _parse_frontmatter_agents
        assert _parse_frontmatter_agents("# Just a heading\n\nsome content") is None

    def test_frontmatter_without_agents_returns_none(self):
        from agent.context_library import _parse_frontmatter_agents
        content = "---\ntitle: foo\nauthor: bar\n---\nsome content"
        assert _parse_frontmatter_agents(content) is None

    def test_quoted_agent_names_stripped(self):
        from agent.context_library import _parse_frontmatter_agents
        content = '---\nagents: ["verify", \'plan\']\n---\ncontent'
        result = _parse_frontmatter_agents(content)
        assert result == ["verify", "plan"]


# ---------------------------------------------------------------------------
# _strip_frontmatter
# ---------------------------------------------------------------------------

class TestStripFrontmatter:
    def test_removes_frontmatter(self):
        from agent.context_library import _strip_frontmatter
        content = "---\nagents: [verify]\n---\n# Real Content\n\nBody here."
        result = _strip_frontmatter(content)
        assert "---" not in result
        assert "Real Content" in result

    def test_no_frontmatter_unchanged(self):
        from agent.context_library import _strip_frontmatter
        content = "# Just content\n\nNo frontmatter."
        assert _strip_frontmatter(content) == content


# ---------------------------------------------------------------------------
# ensure_context_dir
# ---------------------------------------------------------------------------

class TestEnsureContextDir:
    def test_creates_directory_and_seeds_files(self, tmp_path):
        from agent.context_library import ensure_context_dir, STARTER_FILES
        fake_home = tmp_path / "hermes"
        with patch("agent.context_library.get_hermes_home", return_value=fake_home):
            ctx_dir = ensure_context_dir()

        assert ctx_dir.exists()
        for filename in STARTER_FILES:
            assert (ctx_dir / filename).exists(), f"{filename} was not seeded"

    def test_does_not_overwrite_existing_files(self, tmp_path):
        from agent.context_library import ensure_context_dir
        fake_home = tmp_path / "hermes"
        ctx_dir = fake_home / "context"
        ctx_dir.mkdir(parents=True)
        existing = ctx_dir / "coding-standards.md"
        existing.write_text("my custom content", encoding="utf-8")

        with patch("agent.context_library.get_hermes_home", return_value=fake_home):
            ensure_context_dir()

        # Custom content must survive
        assert existing.read_text(encoding="utf-8") == "my custom content"

    def test_idempotent_second_call(self, tmp_path):
        from agent.context_library import ensure_context_dir
        fake_home = tmp_path / "hermes"
        with patch("agent.context_library.get_hermes_home", return_value=fake_home):
            ensure_context_dir()
            ensure_context_dir()  # Must not raise


# ---------------------------------------------------------------------------
# load_context_library
# ---------------------------------------------------------------------------

class TestLoadContextLibrary:
    def test_returns_empty_when_dir_missing(self, tmp_path):
        from agent.context_library import load_context_library
        with patch("agent.context_library.get_hermes_home", return_value=tmp_path / "nonexistent"):
            result = load_context_library()
        assert result == ""

    def test_includes_all_files_when_no_agent_type(self, tmp_path):
        from agent.context_library import load_context_library
        ctx_dir = tmp_path / "hermes" / "context"
        ctx_dir.mkdir(parents=True)
        _write(ctx_dir / "a.md", "# Alpha\n\nalpha content")
        _write(ctx_dir / "b.md", "# Beta\n\nbeta content")

        with patch("agent.context_library.get_context_dir", return_value=ctx_dir):
            result = load_context_library()

        assert "alpha content" in result
        assert "beta content" in result
        assert "## Context Library" in result

    def test_agent_filtered_file_excluded_when_type_does_not_match(self, tmp_path):
        from agent.context_library import load_context_library
        ctx_dir = tmp_path / "hermes" / "context"
        ctx_dir.mkdir(parents=True)

        _write(ctx_dir / "verify-only.md", "---\nagents: [verify]\n---\n# Verify Only\n\nsecret verify content")
        _write(ctx_dir / "global.md", "# Global\n\nglobal content")

        with patch("agent.context_library.get_context_dir", return_value=ctx_dir):
            result_plan = load_context_library(agent_type="plan")

        assert "secret verify content" not in result_plan
        assert "global content" in result_plan

    def test_agent_filtered_file_included_when_type_matches(self, tmp_path):
        from agent.context_library import load_context_library
        ctx_dir = tmp_path / "hermes" / "context"
        ctx_dir.mkdir(parents=True)

        _write(ctx_dir / "verify-only.md", "---\nagents: [verify]\n---\n# Verify Only\n\nsecret verify content")

        with patch("agent.context_library.get_context_dir", return_value=ctx_dir):
            result = load_context_library(agent_type="verify")

        assert "secret verify content" in result

    def test_content_truncated_at_limit(self, tmp_path):
        from agent.context_library import load_context_library, CONTEXT_FILE_MAX_CHARS
        ctx_dir = tmp_path / "hermes" / "context"
        ctx_dir.mkdir(parents=True)

        long_content = "x" * (CONTEXT_FILE_MAX_CHARS + 2000)
        (ctx_dir / "big.md").write_text(long_content, encoding="utf-8")

        with patch("agent.context_library.get_context_dir", return_value=ctx_dir):
            result = load_context_library()

        assert "truncated" in result.lower() or len(result) < len(long_content) + 500

    def test_files_sorted_alphabetically(self, tmp_path):
        from agent.context_library import load_context_library
        ctx_dir = tmp_path / "hermes" / "context"
        ctx_dir.mkdir(parents=True)

        _write(ctx_dir / "zzz.md", "# ZZZ\n\nzz content")
        _write(ctx_dir / "aaa.md", "# AAA\n\naa content")

        with patch("agent.context_library.get_context_dir", return_value=ctx_dir):
            result = load_context_library()

        assert result.index("aa content") < result.index("zz content")

    def test_empty_files_skipped(self, tmp_path):
        from agent.context_library import load_context_library
        ctx_dir = tmp_path / "hermes" / "context"
        ctx_dir.mkdir(parents=True)

        (ctx_dir / "empty.md").write_text("", encoding="utf-8")
        _write(ctx_dir / "real.md", "# Real\n\nsome content")

        with patch("agent.context_library.get_context_dir", return_value=ctx_dir):
            result = load_context_library()

        assert "some content" in result
        # empty.md stem should not appear as an orphaned header
        assert result.count("### empty") == 0


# ---------------------------------------------------------------------------
# list_context_files
# ---------------------------------------------------------------------------

class TestListContextFiles:
    def test_returns_empty_when_no_dir(self, tmp_path):
        from agent.context_library import list_context_files
        with patch("agent.context_library.get_context_dir", return_value=tmp_path / "no"):
            result = list_context_files()
        assert result == []

    def test_metadata_structure(self, tmp_path):
        from agent.context_library import list_context_files
        ctx_dir = tmp_path / "context"
        ctx_dir.mkdir()
        _write(ctx_dir / "standards.md", "---\nagents: [verify]\n---\n# Standards\n\ncontent")

        with patch("agent.context_library.get_context_dir", return_value=ctx_dir):
            files = list_context_files()

        assert len(files) == 1
        entry = files[0]
        assert entry["name"] == "standards"
        assert entry["agents_filter"] == ["verify"]
        assert entry["size_chars"] > 0
        assert "path" in entry
