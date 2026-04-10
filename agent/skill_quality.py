"""Skill quality engine for Hermes.

Provides three capabilities:
  1. validate_skill()        — score a SKILL.md against the 5-component structure
  2. generate_skill_template() — produce a production-ready SKILL.md skeleton
  3. SkillQualityReport      — structured result for both CLI display and Sentry

Design principles from the "80,000+ Skills" guide:
  - YAML trigger must have 5+ explicit phrases AND negative boundaries
  - Workflow steps must be imperative & testable (no vague verbs)
  - Output format must specify length, tone, structure
  - At least 1 happy-path + 1 edge-case example
  - No ambiguous instructions that Claude will interpret differently every run
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from agent.skill_utils import parse_frontmatter


# ---------------------------------------------------------------------------
# Quality scoring constants
# ---------------------------------------------------------------------------

# Minimum trigger phrases for a "strong" trigger
MIN_TRIGGER_PHRASES = 5

# Vague verbs that indicate untestable instructions
VAGUE_VERBS = frozenset({
    "handle", "deal with", "appropriately", "properly", "nicely",
    "format nicely", "work with", "as needed", "if necessary",
    "as appropriate", "as required", "feel free", "consider",
    "make sure", "ensure that", "handle appropriately",
})

# Required structural sections (case-insensitive heading scan)
REQUIRED_SECTIONS = {
    "overview": re.compile(r"^#+\s*overview", re.MULTILINE | re.IGNORECASE),
    "workflow": re.compile(r"^#+\s*workflow", re.MULTILINE | re.IGNORECASE),
    "output_format": re.compile(r"^#+\s*output.format", re.MULTILINE | re.IGNORECASE),
    "examples": re.compile(r"^#+\s*examples?", re.MULTILINE | re.IGNORECASE),
}


# ---------------------------------------------------------------------------
# Report dataclass
# ---------------------------------------------------------------------------

@dataclass
class QualityIssue:
    """A single quality problem found in a skill."""
    severity: str          # "error" | "warning" | "info"
    failure_mode: str      # one of the 5 failure modes, or "structure"
    message: str
    fix: str               # concrete fix suggestion


@dataclass
class SkillQualityReport:
    """Comprehensive quality assessment for one SKILL.md."""
    skill_name: str
    skill_path: Optional[str]
    score: int             # 0-100
    grade: str             # A / B / C / D / F
    issues: List[QualityIssue] = field(default_factory=list)
    passed_checks: List[str] = field(default_factory=list)

    @property
    def errors(self) -> List[QualityIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[QualityIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def summary(self) -> str:
        """One-line CLI-friendly summary."""
        return (
            f"{self.skill_name}: {self.grade} ({self.score}/100) — "
            f"{len(self.errors)} errors, {len(self.warnings)} warnings"
        )

    def full_report(self) -> str:
        """Multi-line report for /skillcheck output."""
        lines = [
            f"  Skill: {self.skill_name}",
            f"  Score: {self.score}/100  Grade: {self.grade}",
            "",
        ]
        if self.passed_checks:
            lines.append("  ✅ Passed:")
            for c in self.passed_checks:
                lines.append(f"     • {c}")
            lines.append("")
        if self.errors:
            lines.append("  ❌ Errors (must fix):")
            for issue in self.errors:
                lines.append(f"     [{issue.failure_mode}] {issue.message}")
                lines.append(f"       → Fix: {issue.fix}")
            lines.append("")
        if self.warnings:
            lines.append("  ⚠️  Warnings (should fix):")
            for issue in self.warnings:
                lines.append(f"     [{issue.failure_mode}] {issue.message}")
                lines.append(f"       → Fix: {issue.fix}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core validator
# ---------------------------------------------------------------------------

def validate_skill(content: str, skill_path: Optional[str] = None) -> SkillQualityReport:
    """Score a SKILL.md string against production-quality criteria.

    Returns a SkillQualityReport with score (0-100), grade, issues, and
    passed checks.  Does NOT require disk access — pass the raw content.
    """
    frontmatter, body = parse_frontmatter(content)
    skill_name = str(frontmatter.get("name") or _name_from_path(skill_path) or "unknown")

    issues: List[QualityIssue] = []
    passed: List[str] = []
    score = 100  # start full, deduct for failures

    # ── Check 1: YAML frontmatter present ────────────────────────────────
    if not frontmatter:
        issues.append(QualityIssue(
            severity="error",
            failure_mode="silent-skill",
            message="No YAML frontmatter found. Skill will never activate.",
            fix="Add --- frontmatter block with name and description fields at the top of SKILL.md",
        ))
        score -= 30
    else:
        passed.append("YAML frontmatter present")

    # ── Check 2: description field (trigger strength) ─────────────────────
    description = str(frontmatter.get("description") or "").strip()
    if not description:
        issues.append(QualityIssue(
            severity="error",
            failure_mode="silent-skill",
            message="No description field. Claude cannot match this skill to user requests.",
            fix="Add a 'description' field listing 5+ trigger phrases and negative boundaries.",
        ))
        score -= 25
    else:
        trigger_phrases = _count_trigger_phrases(description)
        if trigger_phrases < MIN_TRIGGER_PHRASES:
            issues.append(QualityIssue(
                severity="warning",
                failure_mode="silent-skill",
                message=f"Description has only ~{trigger_phrases} trigger phrases (need {MIN_TRIGGER_PHRASES}+). Skill may not fire reliably.",
                fix="Add more explicit trigger phrases: 'Use when user says X, Y, Z...' List edge-case phrasings.",
            ))
            score -= 10
        else:
            passed.append(f"Trigger description has {trigger_phrases}+ phrases")

        if not _has_negative_boundary(description):
            issues.append(QualityIssue(
                severity="warning",
                failure_mode="hijacker",
                message="Description has no negative boundary (Do NOT use for...). Skill may fire on wrong requests.",
                fix="Add 'Do NOT use for X, Y, Z' to the description to prevent false activations.",
            ))
            score -= 8
        else:
            passed.append("Negative boundary declared in trigger")

    # ── Check 3: Required structural sections ────────────────────────────
    for section_key, pattern in REQUIRED_SECTIONS.items():
        if pattern.search(body):
            passed.append(f"Has {section_key.replace('_', ' ').title()} section")
        else:
            severity = "error" if section_key in ("workflow", "output_format") else "warning"
            failure = {"workflow": "drifter", "output_format": "overachiever"}.get(section_key, "structure")
            issues.append(QualityIssue(
                severity=severity,
                failure_mode=failure,
                message=f"Missing '## {section_key.replace('_', ' ').title()}' section.",
                fix=f"Add a '## {section_key.replace('_', ' ').title()}' section following the 5-component structure.",
            ))
            score -= 10 if severity == "error" else 5

    # ── Check 4: Workflow quality — numbered steps, imperative verbs ──────
    workflow_match = re.search(
        r"^##\s+workflow\b.*?(?=\n##\s|\Z)",
        body,
        re.MULTILINE | re.IGNORECASE | re.DOTALL,
    )
    if workflow_match:
        workflow_text = workflow_match.group(0)
        step_count = len(re.findall(r"^\s*\d+\.", workflow_text, re.MULTILINE))
        if step_count < 3:
            issues.append(QualityIssue(
                severity="warning",
                failure_mode="drifter",
                message=f"Workflow has only {step_count} numbered step(s). Fewer than 3 steps is too vague.",
                fix="Break the workflow into 3+ numbered imperative steps: '1. Read X', '2. Generate Y', '3. Review Z'",
            ))
            score -= 8
        else:
            passed.append(f"Workflow has {step_count} numbered steps")

        vague_found = [v for v in VAGUE_VERBS if v in workflow_text.lower()]
        if vague_found:
            issues.append(QualityIssue(
                severity="warning",
                failure_mode="drifter",
                message=f"Workflow contains vague instructions: {', '.join(vague_found[:3])}...",
                fix="Replace vague verbs with specific, testable actions: 'If X, do Y' not 'handle appropriately'.",
            ))
            score -= 5

    # ── Check 5: Examples — at least one happy-path and one edge case ─────
    examples_match = re.search(
        r"^##\s+examples?\b.*?(?=\n##\s|\Z)",
        body,
        re.MULTILINE | re.IGNORECASE | re.DOTALL,
    )
    if examples_match:
        examples_text = examples_match.group(0)
        # Match both "**Input:**" and "**Input**:" and "Input:" formats
        input_count = len(re.findall(r"\*\*input\b|\binput:", examples_text, re.IGNORECASE))
        edge_case_count = len(re.findall(r"edge.case|unusual|missing|empty|wrong", examples_text, re.IGNORECASE))

        if input_count < 1:
            issues.append(QualityIssue(
                severity="warning",
                failure_mode="fragile",
                message="Examples section has no concrete Input/Output pairs.",
                fix="Add '**Input:** ...' and '**Output:** ...' pairs showing exactly what you want.",
            ))
            score -= 8
        else:
            passed.append(f"Examples section has {input_count} Input/Output pair(s)")

        if edge_case_count < 1:
            issues.append(QualityIssue(
                severity="info",
                failure_mode="fragile",
                message="No edge-case examples found. Skill may break on unusual inputs.",
                fix="Add an '### Edge Case' section showing how to handle missing fields, bad inputs, etc.",
            ))
            score -= 3
        else:
            passed.append("Edge-case handling documented")

    # ── Check 6: Output format specifics ─────────────────────────────────
    fmt_match = re.search(
        r"^##\s+output.format\b.*?(?=\n##\s|\Z)",
        body,
        re.MULTILINE | re.IGNORECASE | re.DOTALL,
    )
    if fmt_match:
        fmt_text = fmt_match.group(0)
        has_length = bool(re.search(r"\d+.*(word|line|char|sentence|paragraph)", fmt_text, re.IGNORECASE))
        has_tone = bool(re.search(r"tone|voice|style|formal|casual|professional|concise", fmt_text, re.IGNORECASE))
        if not has_length:
            issues.append(QualityIssue(
                severity="info",
                failure_mode="overachiever",
                message="Output Format section doesn't specify length (words, lines, etc.).",
                fix="Add e.g. 'Total length: 300-500 words' or 'Max 10 bullet points'.",
            ))
            score -= 2
        else:
            passed.append("Output length specified")
        if not has_tone:
            issues.append(QualityIssue(
                severity="info",
                failure_mode="overachiever",
                message="Output Format section doesn't specify tone/style.",
                fix="Add e.g. 'Tone: professional, direct — no filler phrases'.",
            ))
            score -= 2
        else:
            passed.append("Output tone/style specified")

    # ── Clamp score and assign grade ──────────────────────────────────────
    score = max(0, min(100, score))
    grade = _score_to_grade(score)

    return SkillQualityReport(
        skill_name=skill_name,
        skill_path=skill_path,
        score=score,
        grade=grade,
        issues=issues,
        passed_checks=passed,
    )


def validate_skill_file(path: str | Path) -> SkillQualityReport:
    """Convenience: validate a skill from a file path."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Skill file not found: {path}")
    content = p.read_text(encoding="utf-8")
    return validate_skill(content, skill_path=str(p))


def validate_all_skills(skills_dir: str | Path | None = None) -> List[SkillQualityReport]:
    """Validate every SKILL.md found under skills_dir.

    If skills_dir is None, scans the user's ~/.hermes/skills/ directory.
    Returns list sorted by score ascending (worst first).
    """
    from agent.skill_utils import get_all_skills_dirs, iter_skill_index_files

    if skills_dir is not None:
        dirs = [Path(skills_dir)]
    else:
        dirs = get_all_skills_dirs()

    reports: List[SkillQualityReport] = []
    for d in dirs:
        if not d.is_dir():
            continue
        for skill_file in iter_skill_index_files(d, "SKILL.md"):
            try:
                report = validate_skill_file(skill_file)
                reports.append(report)
            except Exception:
                continue

    reports.sort(key=lambda r: r.score)
    return reports


# ---------------------------------------------------------------------------
# Template generator
# ---------------------------------------------------------------------------

def generate_skill_template(
    name: str,
    task_description: str,
    trigger_phrases: Optional[List[str]] = None,
    negative_boundaries: Optional[List[str]] = None,
    output_format_hint: str = "",
) -> str:
    """Generate a production-quality SKILL.md skeleton.

    Args:
        name: Hyphen-separated skill name (e.g. "proposal-generator")
        task_description: One sentence of what the skill does
        trigger_phrases: List of phrases that should activate the skill
        negative_boundaries: List of things this skill should NOT do
        output_format_hint: e.g. "Markdown document, 400-600 words"

    Returns:
        A complete SKILL.md string ready to save and iterate on.
    """
    slug = re.sub(r"[^a-z0-9-]", "-", name.lower().strip())
    slug = re.sub(r"-{2,}", "-", slug).strip("-") or "my-skill"

    # Build trigger description
    phrases = trigger_phrases or [f"do {slug}", f"create {slug}", f"generate {slug}", f"write {slug}", f"make {slug}"]
    negatives = negative_boundaries or [f"unrelated tasks"]

    phrase_list = "\n  ".join(phrases)
    negative_list = ", ".join(negatives)

    trigger_desc = (
        f"{task_description}\n"
        f"  Use this skill when the user says: {phrase_list}.\n"
        f"  Do NOT use for: {negative_list}."
    )

    output_spec = output_format_hint or "Markdown, 300-500 words, professional tone"

    template = f"""---
name: {slug}
description: >
  {trigger_desc}
---

## Overview

This skill {task_description.lower().rstrip(".")}. When activated, it follows
the workflow below to produce consistent, high-quality output every time.

## Workflow

1. **Gather inputs** — collect all required information from the user. Ask for
   anything missing before proceeding. Do NOT invent or assume values.

2. **[Main step]** — describe the primary transformation/generation/analysis here.
   Be specific. Each step should have exactly one way to interpret it.

3. **[Secondary step]** — add more steps as needed. Each must be:
   - One clear action written as an imperative command
   - Specific enough that there is only ONE way to interpret it
   - Testable: you can verify whether it was done correctly

4. **Apply output format** — follow the Output Format section exactly.

5. **Quality check** — before delivering, verify:
   - [ ] All required inputs were used
   - [ ] Output matches the specified format
   - [ ] No filler phrases or unnecessary caveats added

## Output Format

- Format: {output_spec}
- Headings: H2 for main sections, H3 for subsections
- Tone: [specify: professional / casual / technical / friendly]
- Length: [specify: word count or line count]
- Do NOT include: [list what to omit — filler phrases, unsolicited commentary, etc.]
- Output ONLY the [document/report/analysis]. Do NOT add explanatory text
  unless explicitly asked.

## Examples

### Happy Path Example

**Input:** "[Replace with a clean, complete, ideal input example]"

**Expected output:**
[Show the EXACT output you want — complete, formatted, matching your spec.
This is the most important part. Claude will pattern-match to this example
more than to any abstract instruction above.]

### Edge Case Example

**Input:** "[Replace with an unusual input — missing fields, wrong format, etc.]"

**Expected behavior:**
[Describe exactly what to do: ask for missing info, skip optional sections,
add a placeholder note, etc. Never leave edge cases to interpretation.]

## Notes

- Skill version: 1.0
- Last validated: [date]
- Test this skill with: `/skilltest {slug}`
"""
    return template


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _count_trigger_phrases(description: str) -> int:
    """Estimate the number of explicit trigger phrases in a description."""
    # Count comma/semicolon separated items + sentence count as proxy
    phrase_indicators = re.findall(
        r"(?:user says|trigger|activate|invoke|when.*?says|use when|use for|use this)",
        description,
        re.IGNORECASE,
    )
    # Also count quoted phrases
    quoted = re.findall(r"['\"][^'\"]{2,40}['\"]", description)
    # Count comma-separated list items after "when" clauses
    when_lists = re.findall(r"(?:says|types|asks for|requests?)[^.]+", description, re.IGNORECASE)
    comma_items = sum(len(re.split(r"[,;]", m)) for m in when_lists)
    return max(len(phrase_indicators) + len(quoted), comma_items)


def _has_negative_boundary(description: str) -> bool:
    """Return True if description contains explicit negative boundaries."""
    patterns = [
        r"do not use for",
        r"do not activate",
        r"do not trigger",
        r"not for",
        r"exclude",
        r"avoid.*when",
        r"different from",
        r"do NOT",
    ]
    lower = description.lower()
    return any(re.search(p, lower) for p in patterns)


def _score_to_grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 55:
        return "D"
    return "F"


def _name_from_path(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    p = Path(path)
    if p.name == "SKILL.md":
        return p.parent.name
    return p.stem
