"""Tests for agent/skill_quality.py — the skill quality engine."""

import pytest
from agent.skill_quality import (
    QualityIssue,
    SkillQualityReport,
    generate_skill_template,
    validate_skill,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PERFECT_SKILL = """---
name: proposal-generator
description: >
  Generates professional business proposals from basic project details.
  Use this skill when the user says 'write a proposal', 'draft a proposal',
  'create a proposal', 'I need a proposal for', 'proposal for [client]',
  'generate a proposal', or 'client proposal'. Also activate when user
  provides project scope and asks for a client-ready document.
  Do NOT use for internal project plans, SOWs, or technical specifications.
---

## Overview

This skill generates professional business proposals from basic project
details. When activated it collects scope, client info, timeline, and pricing
then produces a complete client-ready proposal.

## Workflow

1. Collect the following from the user (ask if not provided):
   - Client name and company
   - Project description
   - Timeline
   - Budget (optional)

2. Read references/proposal-template.md

3. Generate proposal with these sections:
   - Executive Summary (3 sentences max)
   - Understanding of the Problem
   - Proposed Solution
   - Deliverables
   - Timeline
   - Investment

4. Apply the Output Format spec exactly.

5. Review against quality checklist before delivering.

## Output Format

- Format: Markdown, ready to convert to PDF
- Total length: 500-800 words
- Headings: H2 for main sections
- Tone: professional, confident, direct — not salesy
- Do NOT include: filler phrases, unnecessary caveats, template language

## Examples

### Happy Path Example

**Input:** "Proposal for Acme Corp, website redesign, 3 months, $15,000"

**Output:**
## Executive Summary
We will redesign Acme Corp's website over 12 weeks, delivering a modern,
conversion-optimised site that reduces bounce rate by 30%.

### Edge Case Example

**Input:** "Proposal for a client, not sure about pricing yet"

**Expected behavior:** Generate the proposal with all sections EXCEPT pricing.
Add a placeholder: "[Pricing to be discussed — remove before sending]".
Do NOT invent a price.
"""

MINIMAL_SKILL = """# My Skill
This skill does stuff.
"""

NO_EXAMPLES_SKILL = """---
name: no-examples
description: >
  Does something when you ask it to do something, like when you say 'do it'
  or 'please do it' or 'do the thing' or 'run it' or 'execute the task'.
  Do NOT use for unrelated tasks.
---

## Overview
Does something.

## Workflow

1. Read the input.
2. Process it.
3. Return the result.

## Output Format

- Format: plain text
- Length: 1-3 sentences
- Tone: concise
"""

VAGUE_SKILL = """---
name: vague-skill
description: >
  Handles things appropriately.
---

## Overview
Handles stuff.

## Workflow

1. Handle the request appropriately.
2. Deal with edge cases properly.
3. Format nicely if necessary.

## Output Format
Format as needed.

## Examples

**Input:** "Do something"
**Output:** "Done"
"""


# ---------------------------------------------------------------------------
# validate_skill tests
# ---------------------------------------------------------------------------

class TestValidateSkill:
    def test_perfect_skill_scores_high(self):
        report = validate_skill(PERFECT_SKILL)
        assert report.score >= 85, f"Expected score >=85, got {report.score}"
        assert report.grade in ("A", "B")
        assert report.skill_name == "proposal-generator"

    def test_minimal_skill_fails(self):
        report = validate_skill(MINIMAL_SKILL)
        # No frontmatter = catastrophic failure
        assert report.score < 50
        assert report.grade == "F"
        # Should have error about missing frontmatter
        error_msgs = [i.message for i in report.errors]
        assert any("frontmatter" in m.lower() or "yaml" in m.lower() for m in error_msgs)

    def test_skill_with_no_examples_loses_points(self):
        full = validate_skill(PERFECT_SKILL)
        no_ex = validate_skill(NO_EXAMPLES_SKILL)
        assert full.score > no_ex.score

    def test_vague_verbs_flagged(self):
        report = validate_skill(VAGUE_SKILL)
        warning_msgs = " ".join(i.message for i in report.warnings)
        # Should flag vague verbs
        assert any(
            "vague" in i.message.lower() or "appropriately" in i.message.lower()
            for i in report.issues
        )

    def test_missing_negative_boundary_flagged(self):
        skill_no_boundary = PERFECT_SKILL.replace(
            "  Do NOT use for internal project plans, SOWs, or technical specifications.",
            "",
        )
        report = validate_skill(skill_no_boundary)
        # Should have a warning about missing negative boundary
        assert any("negative boundary" in i.message.lower() or "do not" in i.message.lower()
                   for i in report.warnings)

    def test_report_has_passed_checks(self):
        report = validate_skill(PERFECT_SKILL)
        assert len(report.passed_checks) > 0

    def test_score_clamped_0_100(self):
        # Even the worst possible skill shouldn't go negative
        report = validate_skill("")
        assert 0 <= report.score <= 100

    def test_grade_mapping(self):
        report = validate_skill(PERFECT_SKILL)
        assert report.grade in ("A", "B", "C", "D", "F")

    def test_full_report_is_string(self):
        report = validate_skill(PERFECT_SKILL)
        output = report.full_report()
        assert isinstance(output, str)
        assert len(output) > 50

    def test_summary_contains_skill_name(self):
        report = validate_skill(PERFECT_SKILL)
        assert "proposal-generator" in report.summary()


# ---------------------------------------------------------------------------
# generate_skill_template tests
# ---------------------------------------------------------------------------

class TestGenerateSkillTemplate:
    def test_generates_valid_markdown(self):
        template = generate_skill_template(
            "email-writer",
            "Writes professional email drafts from bullet points",
        )
        assert "---" in template
        assert "name: email-writer" in template
        assert "## Workflow" in template
        assert "## Output Format" in template
        assert "## Examples" in template

    def test_slug_sanitized(self):
        template = generate_skill_template(
            "My Crazy Skill Name!!!",
            "Does something",
        )
        # Name should be sanitized to hyphen slug
        assert "my-crazy-skill-name" in template

    def test_custom_trigger_phrases_included(self):
        template = generate_skill_template(
            "invoice-gen",
            "Generates invoices",
            trigger_phrases=["create an invoice", "make an invoice", "invoice for client"],
        )
        assert "create an invoice" in template

    def test_custom_negative_boundaries_included(self):
        template = generate_skill_template(
            "invoice-gen",
            "Generates invoices",
            negative_boundaries=["receipts", "purchase orders"],
        )
        assert "receipts" in template

    def test_generated_template_is_parseable(self):
        from agent.skill_utils import parse_frontmatter
        template = generate_skill_template("test-skill", "Does a test thing")
        frontmatter, body = parse_frontmatter(template)
        assert frontmatter.get("name") == "test-skill"
        assert "description" in frontmatter

    def test_generated_template_validates_above_threshold(self):
        """Template skeleton should score at least C — it has the structure, just needs content."""
        template = generate_skill_template(
            "review-writer",
            "Writes product reviews from feature lists",
            trigger_phrases=[
                "write a review", "create a review", "product review",
                "draft a review", "generate a review", "review for product",
            ],
            negative_boundaries=["testimonials", "press releases", "social posts"],
            output_format_hint="Markdown, 200-400 words, balanced professional tone",
        )
        report = validate_skill(template)
        assert report.score >= 60, f"Template scored too low: {report.score}\n{report.full_report()}"


# ---------------------------------------------------------------------------
# SkillQualityReport helpers
# ---------------------------------------------------------------------------

class TestSkillQualityReport:
    def test_errors_property(self):
        report = SkillQualityReport(
            skill_name="test",
            skill_path=None,
            score=50,
            grade="D",
            issues=[
                QualityIssue("error", "silent-skill", "msg", "fix"),
                QualityIssue("warning", "hijacker", "msg2", "fix2"),
            ],
        )
        assert len(report.errors) == 1
        assert len(report.warnings) == 1

    def test_grade_f_on_empty(self):
        report = validate_skill("")
        assert report.grade == "F"
