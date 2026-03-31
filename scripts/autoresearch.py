#!/usr/bin/env python3
"""
Hermes Autoresearch Loop
Inspired by github.com/karpathy/autoresearch

Continuously improves Hermes by:
1. Static-analyzing SOUL.md for quality signals
2. Using Claude Code CLI (subscription, no API billing) to propose changes
3. Keeping improvements, reverting regressions
4. Logging everything to results.tsv
5. NEVER STOPPING (until killed)

NO API CALLS. Uses Claude Code CLI for proposals, static analysis for scoring.

Usage:
    python3 scripts/autoresearch.py                  # Run forever
    python3 scripts/autoresearch.py --max-runs 5     # Run 5 experiments
    python3 scripts/autoresearch.py --baseline-only  # Just run baseline eval
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

EVALS_DIR = REPO_ROOT / "evals"
RESULTS_TSV = EVALS_DIR / "results.tsv"
SOUL_MD = Path.home() / ".hermes" / "SOUL.md"

# Files the researcher is allowed to modify
MUTABLE_FILES = [str(SOUL_MD)]


def git_commit(message: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=REPO_ROOT, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", message, "--allow-empty"],
        cwd=REPO_ROOT, capture_output=True,
    )
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    return result.stdout.strip()


def git_current_hash() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    return result.stdout.strip()


def read_mutable_files() -> dict[str, str]:
    contents = {}
    for fpath in MUTABLE_FILES:
        p = Path(fpath)
        if p.exists():
            contents[fpath] = p.read_text(encoding="utf-8")
    return contents


def write_mutable_files(contents: dict[str, str]):
    for fpath, content in contents.items():
        Path(fpath).write_text(content, encoding="utf-8")


def load_results_history() -> list[dict]:
    if not RESULTS_TSV.exists():
        return []
    results = []
    with open(RESULTS_TSV) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            results.append(row)
    return results


def append_result(result: dict):
    file_exists = RESULTS_TSV.exists()
    fieldnames = [
        "timestamp", "run", "commit", "score", "prev_score", "delta",
        "status", "description", "elapsed_s", "pass_count", "fail_count",
    ]
    with open(RESULTS_TSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        if not file_exists:
            writer.writeheader()
        writer.writerow(result)


def run_eval() -> dict:
    """Run static analysis eval. Zero API calls."""
    from evals.hermes_eval import run_eval as _run_eval
    return _run_eval()


def propose_change(
    current_files: dict[str, str],
    history: list[dict],
    eval_results: dict,
) -> dict | None:
    """
    Use Claude Code CLI (subscription, no API billing) to propose a change.
    Falls back to rule-based proposals if CLI unavailable.
    """
    # Build context
    history_text = ""
    if history:
        recent = history[-10:]
        history_text = "Recent experiments:\n"
        for h in recent:
            history_text += (
                f"  Run {h.get('run','?')}: score={h.get('score','?')} "
                f"delta={h.get('delta','?')} status={h.get('status','?')} "
                f"— {h.get('description','?')}\n"
            )

    failures_text = ""
    if eval_results and "results" in eval_results:
        failures = [r for r in eval_results["results"] if r["composite"] < 0.7]
        if failures:
            failures_text = "\nFailing categories:\n"
            for f in failures:
                failures_text += (
                    f"  {f['id']}: score={f['composite']:.3f} "
                    f"— {', '.join(f.get('explanations', []))}\n"
                )

    files_text = ""
    for fpath, content in current_files.items():
        fname = Path(fpath).name
        files_text += f"\n--- {fname} ---\n{content}\n"

    prompt = f"""You are improving Hermes SOUL.md. Propose ONE small change to improve the eval score.

Current score: {eval_results.get('score', 'unknown')}
{history_text}
{failures_text}

Current SOUL.md:
{files_text}

RULES:
1. ONE change at a time. Small, focused.
2. Fix worst-scoring category first.
3. Simpler is better.
4. Focus on execution over description.

Output ONLY valid JSON (no markdown, no explanation):
{{"description": "one sentence", "hypothesis": "why this helps", "target": "category_name", "files": {{"{str(SOUL_MD)}": "FULL new file content"}}}}

Or if no change needed: {{"description": "no_change", "files": {{}}}}"""

    # Try Claude Code CLI (uses subscription, no API billing)
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=120,
            cwd=str(REPO_ROOT),
        )
        if result.returncode == 0:
            # Parse claude CLI JSON output
            output = result.stdout.strip()
            try:
                cli_response = json.loads(output)
                # Claude CLI returns {"result": "..."} format
                response_text = cli_response.get("result", output)
            except json.JSONDecodeError:
                response_text = output

            # Extract JSON from response
            proposal = _extract_json(response_text)
            if proposal:
                if proposal.get("description") == "no_change" or not proposal.get("files"):
                    print("  Researcher says: no change needed")
                    return None
                print(f"  Proposal: {proposal.get('description', '?')}")
                return proposal

    except FileNotFoundError:
        print("  Claude CLI not found, using rule-based proposals")
    except subprocess.TimeoutExpired:
        print("  Claude CLI timed out")
    except Exception as e:
        print(f"  Claude CLI error: {e}")

    # Fallback: rule-based proposals based on eval results
    return _rule_based_proposal(current_files, eval_results)


def _extract_json(text: str) -> dict | None:
    """Extract JSON from text that may have markdown wrapping."""
    # Try direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # Try finding JSON in markdown blocks
    if "```json" in text:
        try:
            start = text.index("```json") + 7
            end = text.index("```", start)
            return json.loads(text[start:end].strip())
        except (ValueError, json.JSONDecodeError):
            pass

    if "```" in text:
        try:
            start = text.index("```") + 3
            end = text.index("```", start)
            return json.loads(text[start:end].strip())
        except (ValueError, json.JSONDecodeError):
            pass

    # Try finding {...} pattern
    import re
    match = re.search(r'\{[^{}]*"description"[^{}]*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


def _rule_based_proposal(
    current_files: dict[str, str],
    eval_results: dict,
) -> dict | None:
    """Deterministic proposals based on eval failures. No API calls."""
    if not eval_results or "results" not in eval_results:
        return None

    # Find worst category
    failures = sorted(
        [r for r in eval_results["results"] if r["composite"] < 0.7],
        key=lambda r: r["composite"],
    )

    if not failures:
        # All passing — try simplification
        soul = current_files.get(str(SOUL_MD), "")
        lines = soul.splitlines()
        # Remove consecutive blank lines (simplification)
        new_lines = []
        prev_blank = False
        for line in lines:
            is_blank = line.strip() == ""
            if is_blank and prev_blank:
                continue
            new_lines.append(line)
            prev_blank = is_blank
        new_soul = "\n".join(new_lines)
        if new_soul != soul:
            return {
                "description": "Remove redundant blank lines for simplicity",
                "files": {str(SOUL_MD): new_soul},
            }
        return None

    worst = failures[0]
    soul = current_files.get(str(SOUL_MD), "")

    # Rule-based fixes for each category
    if worst["id"] == "execution_language":
        for note in worst.get("explanations", []):
            if "Missing execution phrases" in note:
                # Add stronger execution language
                if "NEVER describe work. ALWAYS do work." not in soul:
                    soul = soul.replace(
                        "## CORE RULE: DO THE WORK. DO NOT DESCRIBE THE WORK.",
                        "## CORE RULE: DO THE WORK. DO NOT DESCRIBE THE WORK.\n\n"
                        "NEVER describe work. ALWAYS do work. Pick up your tools and execute.",
                    )
                    return {
                        "description": "Strengthen execution-first language in core rule",
                        "files": {str(SOUL_MD): soul},
                    }

    elif worst["id"] == "guardrails":
        for note in worst.get("explanations", []):
            if "catch yourself writing" in note and "catch yourself writing" not in soul.lower():
                # Add the self-check guardrail
                soul = soul.replace(
                    "## EXECUTION OVER PLANNING. ALWAYS.",
                    '## EXECUTION OVER PLANNING. ALWAYS.\n\n'
                    'If you catch yourself writing "Here\'s a plan..." or "I recommend..." '
                    'or "You should..." — STOP. Ask yourself: "Can I do any part of this '
                    'right now?" If yes, do it first, then report what you did.',
                )
                return {
                    "description": "Add self-check guardrail for description detection",
                    "files": {str(SOUL_MD): soul},
                }

    elif worst["id"] == "toolset_registration":
        # This needs code changes, not SOUL.md changes
        print("  toolset_registration failures require code changes, not SOUL.md")
        return None

    elif worst["id"] == "simplicity":
        # Try to trim the file
        lines = soul.splitlines()
        new_lines = []
        for line in lines:
            # Remove comment-only lines that add no value
            stripped = line.strip()
            if stripped.startswith("<!--") and stripped.endswith("-->"):
                continue
            new_lines.append(line)
        new_soul = "\n".join(new_lines)
        if new_soul != soul:
            return {
                "description": "Remove HTML comments for simplicity",
                "files": {str(SOUL_MD): new_soul},
            }

    return None


def main():
    parser = argparse.ArgumentParser(description="Hermes Autoresearch Loop (no API calls)")
    parser.add_argument("--max-runs", type=int, default=0, help="Max experiments (0=infinite)")
    parser.add_argument("--baseline-only", action="store_true", help="Just run baseline eval")
    args = parser.parse_args()

    print("=" * 70)
    print("HERMES AUTORESEARCH LOOP (static analysis + Claude Code CLI)")
    print(f"Max runs: {'infinite' if args.max_runs == 0 else args.max_runs}")
    print(f"Mutable files: {[Path(f).name for f in MUTABLE_FILES]}")
    print(f"NO API BILLING — uses Claude Code subscription only")
    print("=" * 70)

    # Baseline
    print("\n>>> Running baseline eval (static analysis)...")
    baseline = run_eval()
    baseline_score = baseline.get("score", 0.0)
    baseline_hash = git_current_hash()

    # Print detailed baseline
    from evals.hermes_eval import print_summary
    print_summary(baseline)

    append_result({
        "timestamp": datetime.now().isoformat(),
        "run": 0,
        "commit": baseline_hash,
        "score": f"{baseline_score:.4f}",
        "prev_score": "",
        "delta": "",
        "status": "baseline",
        "description": "Initial baseline measurement",
        "elapsed_s": baseline.get("elapsed", 0),
        "pass_count": baseline.get("pass_count", 0),
        "fail_count": baseline.get("fail_count", 0),
    })

    if args.baseline_only:
        print("\nBaseline-only mode. Done.")
        return

    # THE LOOP
    run_number = 0
    prev_score = baseline_score
    best_score = baseline_score
    best_hash = baseline_hash
    last_eval = baseline

    while True:
        run_number += 1
        if args.max_runs > 0 and run_number > args.max_runs:
            print(f"\nReached max runs ({args.max_runs}). Stopping.")
            break

        print(f"\n{'=' * 70}")
        print(f"EXPERIMENT {run_number} | Best: {best_score:.4f} | Current: {prev_score:.4f}")
        print(f"{'=' * 70}")

        current_files = read_mutable_files()
        history = load_results_history()

        # Propose
        print("\n>>> Proposing change...")
        proposal = propose_change(current_files, history, last_eval)

        if proposal is None:
            print("  No change proposed. Done for now.")
            append_result({
                "timestamp": datetime.now().isoformat(),
                "run": run_number,
                "commit": git_current_hash(),
                "score": f"{prev_score:.4f}",
                "prev_score": f"{prev_score:.4f}",
                "delta": "0.0000",
                "status": "skip",
                "description": "No change proposed",
                "elapsed_s": 0,
                "pass_count": 0,
                "fail_count": 0,
            })
            if args.max_runs == 0:
                time.sleep(60)
                continue
            else:
                break

        # Apply
        print("\n>>> Applying change...")
        try:
            new_files = proposal.get("files", {})
            write_mutable_files(new_files)
        except Exception as e:
            print(f"  Error applying change: {e}")
            for fpath, content in current_files.items():
                Path(fpath).write_text(content, encoding="utf-8")
            continue

        desc = proposal.get("description", "autoresearch change")
        commit_hash = git_commit(f"autoresearch: {desc}")
        print(f"  Committed: {commit_hash}")

        # Eval (static analysis, instant)
        print("\n>>> Running eval...")
        eval_result = run_eval()
        new_score = eval_result.get("score", 0.0)
        delta = new_score - prev_score

        print(f"\n  Score: {new_score:.4f} (delta: {delta:+.4f})")

        # Keep or discard
        if new_score > prev_score:
            status = "keep"
            print(f"  >>> KEEPING (improved by {delta:+.4f})")
            prev_score = new_score
            last_eval = eval_result
            if new_score > best_score:
                best_score = new_score
                best_hash = commit_hash
                print(f"  >>> NEW BEST: {best_score:.4f}")
        elif new_score == prev_score:
            old_len = sum(len(v) for v in current_files.values())
            new_len = sum(len(Path(f).read_text()) for f in new_files if Path(f).exists())
            if new_len < old_len:
                status = "keep_simpler"
                print(f"  >>> KEEPING (same score, simpler)")
                last_eval = eval_result
            else:
                status = "discard_same"
                print(f"  >>> DISCARDING (same score, not simpler)")
                write_mutable_files(current_files)
                git_commit(f"revert: {desc}")
        else:
            status = "discard"
            print(f"  >>> DISCARDING (regressed by {delta:.4f})")
            write_mutable_files(current_files)
            git_commit(f"revert: {desc}")

        append_result({
            "timestamp": datetime.now().isoformat(),
            "run": run_number,
            "commit": commit_hash,
            "score": f"{new_score:.4f}",
            "prev_score": f"{prev_score:.4f}",
            "delta": f"{delta:+.4f}",
            "status": status,
            "description": desc,
            "elapsed_s": round(eval_result.get("elapsed", 0), 3),
            "pass_count": eval_result.get("pass_count", 0),
            "fail_count": eval_result.get("fail_count", 0),
        })

        time.sleep(2)

    print("\n" + "=" * 70)
    print("AUTORESEARCH COMPLETE")
    print(f"Total experiments: {run_number}")
    print(f"Best score: {best_score:.4f} (commit {best_hash})")
    print(f"Results: {RESULTS_TSV}")
    print("=" * 70)


if __name__ == "__main__":
    main()
