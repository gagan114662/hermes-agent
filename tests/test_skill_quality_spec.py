"""Tests for extract_skill_spec() and find_skill_path() in agent/skill_quality.py."""
from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

MINIMAL_SKILL = textwrap.dedent("""\
    ---
    name: test-skill
    description: |
      Use when user says "test me", "run test", "check skill".
      Do NOT use for: anything else.
    ---

    ## Overview

    This skill tests things. It activates when the user says test-related phrases.

    ## Workflow

    1. Read the input.
    2. Run the test.
    3. Return results.

    ## Output Format

    Return a JSON object with keys: status, message.
    Total length: 50-100 words.

    ## Examples

    **Input:** test me
    **Output:** {"status": "ok", "message": "All tests passed."}
""")

SKILL_WITHOUT_FRONTMATTER = textwrap.dedent("""\
    ## Overview

    A skill without frontmatter.

    ## Output Format

    Plain text. One sentence.

    ## Workflow

    1. Do something.
""")

SKILL_ALTERNATE_SECTION_NAMES = textwrap.dedent("""\
    ---
    name: alt-skill
    description: fires on "alt"
    ---

    ## Overview

    Alternative section names.

    ## Steps

    1. Step one.
    2. Step two.

    ## Output_Format

    Returns a markdown table.

    ## When to use

    Use this when the user says "alt" or "alternative mode".
""")


# ---------------------------------------------------------------------------
# extract_skill_spec
# ---------------------------------------------------------------------------

class TestExtractSkillSpec:
    def test_includes_frontmatter(self):
        from agent.skill_quality import extract_skill_spec
        result = extract_skill_spec(MINIMAL_SKILL)
        assert "---" in result
        assert "test-skill" in result

    def test_includes_overview(self):
        from agent.skill_quality import extract_skill_spec
        result = extract_skill_spec(MINIMAL_SKILL)
        assert "Overview" in result
        assert "activates when" in result

    def test_includes_output_format(self):
        from agent.skill_quality import extract_skill_spec
        result = extract_skill_spec(MINIMAL_SKILL)
        assert "Output Format" in result
        assert "JSON object" in result

    def test_excludes_workflow(self):
        """Workflow steps must NOT appear — tests should not be anchored to implementation."""
        from agent.skill_quality import extract_skill_spec
        result = extract_skill_spec(MINIMAL_SKILL)
        assert "Read the input" not in result
        assert "Run the test" not in result

    def test_excludes_examples(self):
        """Examples must NOT appear — test writer must derive expected outputs from spec only."""
        from agent.skill_quality import extract_skill_spec
        result = extract_skill_spec(MINIMAL_SKILL)
        assert '{"status": "ok"' not in result
        assert "All tests passed" not in result

    def test_appends_exclusion_note(self):
        from agent.skill_quality import extract_skill_spec
        result = extract_skill_spec(MINIMAL_SKILL)
        assert "intentionally excluded" in result.lower() or "deliberately" in result.lower() \
               or "Workflow steps" in result

    def test_handles_skill_without_frontmatter(self):
        from agent.skill_quality import extract_skill_spec
        result = extract_skill_spec(SKILL_WITHOUT_FRONTMATTER)
        assert "Overview" in result
        assert "Output Format" in result
        assert "Do something" not in result  # Workflow excluded

    def test_recognises_output_format_with_underscore(self):
        from agent.skill_quality import extract_skill_spec
        result = extract_skill_spec(SKILL_ALTERNATE_SECTION_NAMES)
        assert "markdown table" in result

    def test_recognises_when_to_use_section(self):
        from agent.skill_quality import extract_skill_spec
        result = extract_skill_spec(SKILL_ALTERNATE_SECTION_NAMES)
        assert "When to use" in result or "alternative mode" in result

    def test_excludes_steps_section(self):
        from agent.skill_quality import extract_skill_spec
        result = extract_skill_spec(SKILL_ALTERNATE_SECTION_NAMES)
        assert "Step one" not in result
        assert "Step two" not in result

    def test_fallback_on_empty_content(self):
        from agent.skill_quality import extract_skill_spec
        result = extract_skill_spec("")
        # Should return something (even empty string) — must not raise
        assert isinstance(result, str)

    def test_fallback_on_unrecognised_structure(self):
        from agent.skill_quality import extract_skill_spec
        # No recognised sections at all — fallback to first 600 chars
        content = "Just plain text with no headings.\n" * 30
        result = extract_skill_spec(content)
        assert len(result) <= 700  # 600 + note
        assert isinstance(result, str)

    def test_result_is_shorter_than_full_content(self):
        """Spec view should not include workflow + examples content.

        Because the note appended to the spec can offset the stripped content,
        we check that the Workflow and Examples sections are gone rather than
        doing a raw length comparison.
        """
        from agent.skill_quality import extract_skill_spec
        result = extract_skill_spec(MINIMAL_SKILL)
        # Workflow and Examples are the two sections that must be stripped
        assert "## Workflow" not in result
        assert "## Examples" not in result
        # Contract sections must survive
        assert "## Overview" in result
        assert "## Output Format" in result


# ---------------------------------------------------------------------------
# find_skill_path
# ---------------------------------------------------------------------------

class TestFindSkillPath:
    def _make_fake_skills_dir(self, tmp_path: Path, skill_name: str) -> Path:
        skill_dir = tmp_path / skill_name
        skill_dir.mkdir(parents=True)
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(f"# {skill_name}", encoding="utf-8")
        return tmp_path

    def _patch_skills(self, skills_dirs, hermes_home):
        """Context manager that patches both lazy imports used inside find_skill_path."""
        from unittest.mock import patch
        return (
            patch("agent.skill_utils.get_all_skills_dirs", return_value=skills_dirs),
            patch("hermes_constants.get_hermes_home", return_value=hermes_home),
        )

    def test_finds_existing_skill(self, tmp_path):
        from agent.skill_quality import find_skill_path
        from unittest.mock import patch
        skills_dir = self._make_fake_skills_dir(tmp_path, "my-skill")

        with patch("agent.skill_utils.get_all_skills_dirs", return_value=[skills_dir]):
            result = find_skill_path("my-skill")

        assert result is not None
        assert result.name == "SKILL.md"
        assert result.parent.name == "my-skill"

    def test_returns_none_for_missing_skill(self, tmp_path):
        from agent.skill_quality import find_skill_path
        from unittest.mock import patch

        with patch("agent.skill_utils.get_all_skills_dirs", return_value=[tmp_path]):
            result = find_skill_path("no-such-skill")

        assert result is None

    def test_returns_first_match_when_multiple_dirs(self, tmp_path):
        from agent.skill_quality import find_skill_path
        from unittest.mock import patch

        dir_a = tmp_path / "dir_a"
        dir_b = tmp_path / "dir_b"
        self._make_fake_skills_dir(dir_a, "shared-skill")
        self._make_fake_skills_dir(dir_b, "shared-skill")

        with patch("agent.skill_utils.get_all_skills_dirs", return_value=[dir_a, dir_b]):
            result = find_skill_path("shared-skill")

        assert result is not None
        assert str(dir_a) in str(result)  # First directory wins

    def test_handles_empty_skills_dirs_list(self, tmp_path):
        from agent.skill_quality import find_skill_path
        from unittest.mock import patch

        with patch("agent.skill_utils.get_all_skills_dirs", return_value=[]):
            result = find_skill_path("any-skill")

        assert result is None

    def test_finds_flat_md_file(self, tmp_path):
        """Skills laid out as skills_dir/skill-name.md (flat, no subdirectory)."""
        from agent.skill_quality import find_skill_path
        from unittest.mock import patch

        flat_file = tmp_path / "flat-skill.md"
        flat_file.write_text("# Flat Skill", encoding="utf-8")

        with patch("agent.skill_utils.get_all_skills_dirs", return_value=[tmp_path]):
            result = find_skill_path("flat-skill")

        assert result is not None
        assert result == flat_file
