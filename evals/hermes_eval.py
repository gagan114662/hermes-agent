#!/usr/bin/env python3
"""
Hermes Eval Harness — Static Analysis Edition
Scores SOUL.md and system prompt quality WITHOUT making API calls.

This is the "prepare.py" equivalent from autoresearch.
DO NOT let the autoresearch loop modify this file.

Checks:
1. Execution-first language patterns
2. Tool usage instructions present
3. Anti-description guardrails
4. Platform-specific workflows documented
5. Identity clarity
6. Simplicity (fewer lines for same coverage = better)
"""
import json
import re
import sys
import time
from pathlib import Path

SOUL_MD = Path.home() / ".hermes" / "SOUL.md"
SKILLS_DIR = Path(__file__).parent.parent / "skills"
TOOLSETS_PY = Path(__file__).parent.parent / "toolsets.py"


def load_soul() -> str:
    if SOUL_MD.exists():
        return SOUL_MD.read_text(encoding="utf-8")
    return ""


def load_skills() -> dict[str, str]:
    skills = {}
    if SKILLS_DIR.exists():
        for f in SKILLS_DIR.glob("*.md"):
            skills[f.stem] = f.read_text(encoding="utf-8")
    return skills


def load_toolsets() -> str:
    if TOOLSETS_PY.exists():
        return TOOLSETS_PY.read_text(encoding="utf-8")
    return ""


# ─── Scoring functions ───────────────────────────────────────────────

def score_execution_language(soul: str) -> tuple[float, list[str]]:
    """Does SOUL.md push execution over description?"""
    notes = []
    score = 0.0
    soul_lower = soul.lower()

    # Positive signals (execution-first)
    exec_phrases = [
        "do the work",
        "execute",
        "do it",
        "pick up your tools",
        "use browser_upload_file",
        "use browser_navigate",
        "use browser_save_image",
        "browser_click",
        "browser_type",
        "fully automated",
        "zero manual steps",
        "bypasses the os file picker",
        "do not describe the work",
        "you are not a consultant",
        "you are not a secretary",
        "execution over planning",
    ]
    found_exec = [p for p in exec_phrases if p in soul_lower]
    exec_ratio = len(found_exec) / len(exec_phrases)
    score += exec_ratio * 0.6
    if exec_ratio < 0.5:
        notes.append(f"Missing execution phrases: only {len(found_exec)}/{len(exec_phrases)}")

    # Negative signals (should NOT have wishy-washy language)
    weak_phrases = [
        "i cannot",
        "i can't post",
        "not possible",
        "limitation",
        "workaround",
        "the user must",
        "ask the user to",
    ]
    found_weak = [p for p in weak_phrases if p in soul_lower]
    if found_weak:
        penalty = len(found_weak) * 0.1
        score -= penalty
        notes.append(f"Weak/defeatist phrases found: {found_weak}")

    # Strong override present?
    if "critical" in soul_lower and "browser_upload_file" in soul_lower:
        score += 0.2
    else:
        notes.append("Missing CRITICAL override section for Instagram posting")

    # "NEVER STOP" / autonomous work language
    if any(p in soul_lower for p in ["never stop", "default: execute", "do something rather than write"]):
        score += 0.2
    else:
        notes.append("Missing autonomous execution emphasis")

    return (max(0.0, min(1.0, score)), notes)


def score_tool_coverage(soul: str, skills: dict[str, str]) -> tuple[float, list[str]]:
    """Are all critical tools documented in SOUL.md or skills?"""
    notes = []
    combined = soul + " ".join(skills.values())
    combined_lower = combined.lower()

    critical_tools = {
        "browser_upload_file": "Instagram image upload without OS file picker",
        "browser_save_image": "Save images from web pages to disk",
        "browser_navigate": "Navigate to URLs",
        "browser_snapshot": "Take page snapshots for element refs",
        "browser_click": "Click elements on page",
        "browser_type": "Type into input fields",
        "web_search": "Search the web",
        "browser_vision": "Visual page inspection",
    }

    found = 0
    for tool, desc in critical_tools.items():
        if tool in combined_lower:
            found += 1
        else:
            notes.append(f"Missing tool documentation: {tool} ({desc})")

    score = found / len(critical_tools)
    return (score, notes)


def score_platform_workflows(soul: str, skills: dict[str, str]) -> tuple[float, list[str]]:
    """Are step-by-step workflows documented for each platform?"""
    notes = []
    combined = soul + " ".join(skills.values())
    combined_lower = combined.lower()

    platforms = {
        "instagram": ["browser_upload_file", "create", "caption", "share"],
        "twitter": ["tweet", "post", "what is happening"],
        "linkedin": ["start a post", "linkedin.com"],
        "facebook": ["what's on your mind", "facebook.com"],
    }

    total = 0
    found = 0
    for platform, keywords in platforms.items():
        total += 1
        matched = sum(1 for k in keywords if k in combined_lower)
        if matched >= 2:
            found += 1
        else:
            notes.append(f"Incomplete {platform} workflow (only {matched}/{len(keywords)} keywords)")

    score = found / total if total > 0 else 0.0
    return (score, notes)


def score_identity(soul: str) -> tuple[float, list[str]]:
    """Does SOUL.md establish clear employee identity?"""
    notes = []
    soul_lower = soul.lower()

    checks = {
        "employee_not_assistant": any(p in soul_lower for p in ["not an assistant", "not a chatbot", "an employee"]),
        "business_aware": any(p in soul_lower for p in ["business profile", "business described"]),
        "reports_results": any(p in soul_lower for p in ["report results", "report what you did", "what you accomplished"]),
        "proactive": any(p in soul_lower for p in ["proactively", "don't wait to be asked", "see something that needs doing"]),
        "tracks_work": any(p in soul_lower for p in ["track your work", "log", "keep records"]),
    }

    passed = sum(1 for v in checks.values() if v)
    for check, ok in checks.items():
        if not ok:
            notes.append(f"Missing identity signal: {check}")

    score = passed / len(checks)
    return (score, notes)


def score_guardrails(soul: str) -> tuple[float, list[str]]:
    """Are anti-description guardrails present?"""
    notes = []
    soul_lower = soul.lower()

    guardrails = [
        ("stop_catch", "catch yourself writing"),
        ("plan_vs_execute", "when to plan vs execute"),
        ("default_execute", "default: execute"),
        ("not_consultant", "not a consultant"),
        ("not_secretary", "not a secretary"),
        ("not_chatbot", "not a chatbot"),
        ("can_do_list", "what you can do"),
        ("cannot_do_list", "what you cannot do"),
        ("partially_do_list", "what you can partially do"),
    ]

    found = 0
    for name, phrase in guardrails:
        if phrase in soul_lower:
            found += 1
        else:
            notes.append(f"Missing guardrail: {name} ('{phrase}')")

    score = found / len(guardrails)
    return (score, notes)


def score_simplicity(soul: str) -> tuple[float, list[str]]:
    """Simpler is better. Penalize bloat."""
    notes = []
    lines = soul.strip().splitlines()
    line_count = len(lines)
    char_count = len(soul)

    # Sweet spot: 80-200 lines. Under = too sparse. Over = bloated.
    if line_count < 40:
        score = 0.5
        notes.append(f"Too sparse ({line_count} lines) — may miss critical instructions")
    elif line_count <= 120:
        score = 1.0  # Sweet spot
    elif line_count <= 200:
        score = 0.8
        notes.append(f"Getting long ({line_count} lines) — look for redundancy")
    elif line_count <= 300:
        score = 0.6
        notes.append(f"Bloated ({line_count} lines) — trim unnecessary content")
    else:
        score = 0.4
        notes.append(f"Very bloated ({line_count} lines) — major trim needed")

    # Check for duplicate/redundant sections
    paragraphs = re.split(r'\n\n+', soul)
    if len(paragraphs) > 30:
        score -= 0.1
        notes.append(f"Too many sections ({len(paragraphs)})")

    return (max(0.0, min(1.0, score)), notes)


def score_toolset_registration(toolsets_content: str) -> tuple[float, list[str]]:
    """Are browser_upload_file and browser_save_image in the toolsets?"""
    notes = []
    score = 0.0

    if "browser_upload_file" in toolsets_content:
        score += 0.5
    else:
        notes.append("browser_upload_file NOT in toolsets.py")

    if "browser_save_image" in toolsets_content:
        score += 0.5
    else:
        notes.append("browser_save_image NOT in toolsets.py")

    return (score, notes)


# ─── Main eval ───────────────────────────────────────────────────────

def run_eval(dry_run: bool = False, **kwargs) -> dict:
    """
    Run static analysis eval. No API calls.
    Returns composite score (0.0 - 1.0).
    """
    t_start = time.time()

    soul = load_soul()
    skills = load_skills()
    toolsets = load_toolsets()

    if not soul:
        return {"score": 0.0, "error": "SOUL.md not found"}

    # Run all scoring functions
    categories = {}

    s, n = score_execution_language(soul)
    categories["execution_language"] = {"score": s, "notes": n, "weight": 0.25}

    s, n = score_tool_coverage(soul, skills)
    categories["tool_coverage"] = {"score": s, "notes": n, "weight": 0.20}

    s, n = score_platform_workflows(soul, skills)
    categories["platform_workflows"] = {"score": s, "notes": n, "weight": 0.15}

    s, n = score_identity(soul)
    categories["identity"] = {"score": s, "notes": n, "weight": 0.10}

    s, n = score_guardrails(soul)
    categories["guardrails"] = {"score": s, "notes": n, "weight": 0.15}

    s, n = score_simplicity(soul)
    categories["simplicity"] = {"score": s, "notes": n, "weight": 0.05}

    s, n = score_toolset_registration(toolsets)
    categories["toolset_registration"] = {"score": s, "notes": n, "weight": 0.10}

    # Composite weighted score
    total_score = sum(
        cat["score"] * cat["weight"]
        for cat in categories.values()
    )

    elapsed = time.time() - t_start

    # Build results in the format autoresearch expects
    results = []
    pass_count = 0
    fail_count = 0
    for name, cat in categories.items():
        composite = cat["score"]
        if composite >= 0.7:
            pass_count += 1
        else:
            fail_count += 1
        results.append({
            "id": name,
            "category": name,
            "composite": round(composite, 4),
            "scores": {"score": round(composite, 4)},
            "explanations": cat["notes"],
            "violations": [],
            "weight": cat["weight"],
            "elapsed": 0,
            "tool_calls": [],
            "response_length": 0,
            "response_preview": "",
        })

    summary = {
        "score": round(total_score, 4),
        "total_weighted": round(total_score, 4),
        "max_weighted": 1.0,
        "results": results,
        "elapsed": round(elapsed, 3),
        "model": "static-analysis",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "scenarios_count": len(categories),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "categories": {
            name: {"score": round(cat["score"], 4), "notes": cat["notes"]}
            for name, cat in categories.items()
        },
    }

    return summary


def print_summary(summary: dict):
    print("\n" + "=" * 70)
    print(f"HERMES EVAL SCORE: {summary['score']:.4f}")
    print(f"Method: Static Analysis | Time: {summary['elapsed']:.3f}s")
    print(f"Pass: {summary['pass_count']}/{summary['scenarios_count']} | "
          f"Fail: {summary['fail_count']}/{summary['scenarios_count']}")
    print("=" * 70)

    for r in summary["results"]:
        status = "PASS" if r["composite"] >= 0.7 else "FAIL"
        print(f"  [{status}] {r['id']:<25} {r['composite']:.3f}")
        for note in r["explanations"]:
            print(f"         ! {note}")

    print(f"\nFinal: {summary['score']:.4f}")


if __name__ == "__main__":
    summary = run_eval()
    print_summary(summary)

    out_path = Path(__file__).parent / "eval_results.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nResults saved to {out_path}")
