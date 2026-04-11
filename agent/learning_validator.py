"""
Schema validation and quality scoring for Hermes learning loop entries.

Applied before any memory entry or skill is persisted.  Rejects learnings that
fail schema constraints or score below the configured quality threshold.

Configuration:
    HERMES_LEARNING_MIN_QUALITY   float 0.0–1.0; entries scoring below this are
                                  rejected (default: 0.30)
    HERMES_LEARNING_MAX_ENTRIES   max number of memory entries per target per
                                  profile (default: 100)
    HERMES_SKILL_MAX_COUNT        max total skills a profile may store (default: 500)

Quality scoring is intentionally heuristic and fast (no LLM calls):
  - Memory entries: penalise vagueness, noise, and extremes in length.
  - Skills: reward structured frontmatter, actionable instructions, examples.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Config ────────────────────────────────────────────────────────────────────

def _min_quality() -> float:
    try:
        return float(os.environ.get("HERMES_LEARNING_MIN_QUALITY", "0.30"))
    except (TypeError, ValueError):
        return 0.30


def _max_entries() -> int:
    try:
        return int(os.environ.get("HERMES_LEARNING_MAX_ENTRIES", "100"))
    except (TypeError, ValueError):
        return 100


def _max_skills() -> int:
    try:
        return int(os.environ.get("HERMES_SKILL_MAX_COUNT", "500"))
    except (TypeError, ValueError):
        return 500


# ── Memory entry schema ────────────────────────────────────────────────────────

class ValidationError(ValueError):
    """Raised when a learning entry fails schema or quality validation."""


_VALID_TARGETS = frozenset({"memory", "user", "team"})

# Entry must contain at least one word character (not just punctuation/spaces)
_MEANINGFUL_RE = re.compile(r"\w{3,}")

# Vagueness indicators that suggest low-information content
_VAGUE_WORDS = re.compile(
    r"\b(something|stuff|things|whatever|etc|blah|foo|bar|test|todo|fixme|tbd|n/a|placeholder)\b",
    re.IGNORECASE,
)

# High-information markers: numbers, quoted strings, code snippets, URLs, proper nouns
_INFORMATION_MARKERS = re.compile(
    r'(\d+|"[^"]{3,}"|`[^`]+`|https?://\S+|[A-Z][a-z]{2,}[A-Z]|\b[A-Z]{2,}\b)',
)


def validate_memory_entry(content: str, target: str) -> Optional[str]:
    """
    Validate a memory entry against schema rules.

    Returns an error string if invalid, None if OK.
    """
    if not isinstance(content, str):
        return "Memory content must be a string."

    content = content.strip()

    if not content:
        return "Memory content cannot be empty."

    if target not in _VALID_TARGETS:
        return f"Invalid memory target '{target}'. Must be one of: {', '.join(sorted(_VALID_TARGETS))}."

    if len(content) < 5:
        return "Memory entry too short (minimum 5 characters)."

    if len(content) > 10_000:
        return "Memory entry too long (maximum 10,000 characters per entry)."

    if not _MEANINGFUL_RE.search(content):
        return "Memory entry contains no meaningful text."

    return None


def validate_skill_entry(name: str, content: str) -> Optional[str]:
    """
    Validate a skill entry against schema rules (structural checks only).

    Returns an error string if invalid, None if OK.
    """
    if not isinstance(name, str) or not name.strip():
        return "Skill name must be a non-empty string."

    if not isinstance(content, str) or len(content.strip()) < 50:
        return "Skill content is too short to be useful (minimum 50 characters)."

    # Must have YAML frontmatter — defer detailed check to skill_manager_tool
    if not content.lstrip().startswith("---"):
        return "Skill content must begin with YAML frontmatter (---)."

    return None


# ── Quality scoring ────────────────────────────────────────────────────────────

def score_memory_entry(content: str, target: str) -> float:
    """
    Score a memory entry's quality in [0.0, 1.0].

    Heuristic — no LLM calls.  Higher = more likely to be genuinely useful.
    """
    content = content.strip()
    if not content:
        return 0.0

    score = 0.5  # neutral baseline

    # ── Length score ──────────────────────────────────────────────────────────
    n = len(content)
    if n < 10:
        score -= 0.3        # too short — probably noise
    elif n < 20:
        score -= 0.1
    elif 20 <= n <= 400:
        score += 0.1        # sweet spot
    elif n > 1000:
        score -= 0.1        # very long entries lose focus

    # ── Vagueness penalty ─────────────────────────────────────────────────────
    vague_matches = len(_VAGUE_WORDS.findall(content))
    score -= vague_matches * 0.05

    # ── Information density bonus ─────────────────────────────────────────────
    info_matches = len(_INFORMATION_MARKERS.findall(content))
    score += min(info_matches * 0.04, 0.20)

    # ── Structure bonus: bullet, colon, or sentence ───────────────────────────
    if re.search(r"[:,\-•]\s*\w", content):
        score += 0.05

    # ── User-target bonus: user facts are high-value ──────────────────────────
    if target == "user":
        score += 0.05

    return round(max(0.0, min(1.0, score)), 3)


def score_skill_entry(name: str, content: str) -> float:
    """
    Score a skill entry's quality in [0.0, 1.0].
    """
    content = content.strip()
    if not content:
        return 0.0

    score = 0.4

    # ── Frontmatter completeness ──────────────────────────────────────────────
    fm_section = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if fm_section:
        fm_text = fm_section.group(1)
        if re.search(r"\bname\s*:", fm_text, re.IGNORECASE):
            score += 0.05
        if re.search(r"\bdescription\s*:", fm_text, re.IGNORECASE):
            score += 0.08
        if re.search(r"\b(triggers?|usage|when_to_use)\s*:", fm_text, re.IGNORECASE):
            score += 0.07
    else:
        score -= 0.2    # no frontmatter is a big penalty

    # ── Content body ──────────────────────────────────────────────────────────
    body = re.sub(r"^---.*?---", "", content, flags=re.DOTALL).strip()
    body_len = len(body)

    if body_len < 50:
        score -= 0.25
    elif body_len < 200:
        score += 0.05
    else:
        score += 0.10

    # ── Structure: has headings ───────────────────────────────────────────────
    if re.search(r"^#{1,3}\s+\w", body, re.MULTILINE):
        score += 0.07

    # ── Has actionable instructions (numbered list, bullet steps) ─────────────
    if re.search(r"^\s*(\d+\.|[-*•])\s+", body, re.MULTILINE):
        score += 0.07

    # ── Has code examples ─────────────────────────────────────────────────────
    if "```" in body:
        score += 0.05

    return round(max(0.0, min(1.0, score)), 3)


# ── Combined gate ─────────────────────────────────────────────────────────────

def check_memory(content: str, target: str) -> tuple[float, Optional[str]]:
    """
    Run schema validation + quality scoring for a memory entry.

    Returns ``(score, error_or_None)``.  If error is not None the entry should
    be rejected.
    """
    err = validate_memory_entry(content, target)
    if err:
        return 0.0, err

    score = score_memory_entry(content, target)
    threshold = _min_quality()
    if score < threshold:
        return score, (
            f"Memory entry quality score {score:.2f} is below the minimum threshold "
            f"of {threshold:.2f}. The entry appears to be low-information or vague. "
            f"Add specific facts, numbers, or context to improve quality."
        )

    return score, None


def check_skill(name: str, content: str) -> tuple[float, Optional[str]]:
    """
    Run schema validation + quality scoring for a skill entry.

    Returns ``(score, error_or_None)``.
    """
    err = validate_skill_entry(name, content)
    if err:
        return 0.0, err

    score = score_skill_entry(name, content)
    threshold = _min_quality()
    if score < threshold:
        return score, (
            f"Skill quality score {score:.2f} is below the minimum threshold "
            f"of {threshold:.2f}. Ensure the skill has complete frontmatter, "
            f"a description, and structured instructions."
        )

    return score, None


# ── Profile limits ─────────────────────────────────────────────────────────────

def check_memory_limit(current_entry_count: int) -> Optional[str]:
    """
    Return an error string if adding one more entry would exceed the profile limit.
    """
    limit = _max_entries()
    if current_entry_count >= limit:
        return (
            f"Memory limit reached: this profile already has {current_entry_count} entries "
            f"(maximum: {limit}). Remove or consolidate existing entries before adding new ones. "
            f"Raise the limit with HERMES_LEARNING_MAX_ENTRIES."
        )
    return None


def check_skill_limit(current_skill_count: int) -> Optional[str]:
    """
    Return an error string if creating one more skill would exceed the profile limit.
    """
    limit = _max_skills()
    if current_skill_count >= limit:
        return (
            f"Skill limit reached: this profile already has {current_skill_count} skills "
            f"(maximum: {limit}). Delete unused skills first, or raise the limit with "
            f"HERMES_SKILL_MAX_COUNT."
        )
    return None
