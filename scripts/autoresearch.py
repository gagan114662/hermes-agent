#!/usr/bin/env python3
"""
Hermes Autoresearch Loop
Inspired by github.com/karpathy/autoresearch

Continuously improves Hermes by:
1. Proposing a change to SOUL.md / toolsets / skills
2. Running the eval harness
3. Keeping improvements, reverting regressions
4. Logging everything to results.tsv
5. NEVER STOPPING (until killed)

Usage:
    python3 scripts/autoresearch.py                  # Run forever
    python3 scripts/autoresearch.py --max-runs 5     # Run 5 experiments
    python3 scripts/autoresearch.py --dry-run        # Test without API calls
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

# Setup paths
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from run_agent import AIAgent

EVALS_DIR = REPO_ROOT / "evals"
RESULTS_TSV = EVALS_DIR / "results.tsv"
SOUL_MD = Path.home() / ".hermes" / "SOUL.md"
TOOLSETS_PY = REPO_ROOT / "toolsets.py"
SKILLS_DIR = REPO_ROOT / "skills"

# Files the researcher agent is allowed to modify
MUTABLE_FILES = [
    str(SOUL_MD),
    # str(TOOLSETS_PY),  # Uncomment when ready to let it modify toolsets
    # Add skill files as needed
]

# The researcher uses a smarter model to propose changes
RESEARCHER_MODEL = "claude-sonnet-4-6"
# The eval runs on the same model Hermes uses in production
EVAL_MODEL = "claude-haiku-4-5-20251001"


def _get_api_key():
    env_path = Path.home() / ".hermes" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("CLAUDE_CODE_OAUTH_TOKEN="):
                return line.split("=", 1)[1]
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1]
    return os.environ.get("ANTHROPIC_API_KEY", "")


def git_commit(message: str) -> str:
    """Commit current state, return short hash."""
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


def git_reset_hard(commit_hash: str):
    """Revert to a specific commit."""
    subprocess.run(
        ["git", "reset", "--hard", commit_hash],
        cwd=REPO_ROOT, capture_output=True,
    )


def git_current_hash() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    return result.stdout.strip()


def read_mutable_files() -> dict[str, str]:
    """Read all mutable files into a dict."""
    contents = {}
    for fpath in MUTABLE_FILES:
        p = Path(fpath)
        if p.exists():
            contents[fpath] = p.read_text(encoding="utf-8")
    return contents


def write_mutable_files(contents: dict[str, str]):
    """Write modified file contents back to disk."""
    for fpath, content in contents.items():
        Path(fpath).write_text(content, encoding="utf-8")


def load_results_history() -> list[dict]:
    """Load past experiment results from TSV."""
    if not RESULTS_TSV.exists():
        return []
    results = []
    with open(RESULTS_TSV) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            results.append(row)
    return results


def append_result(result: dict):
    """Append a single result to the TSV."""
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


def run_eval(dry_run: bool = False) -> dict:
    """Run the eval harness and return the summary."""
    from evals.hermes_eval import run_eval as _run_eval
    return _run_eval(model=EVAL_MODEL, max_iterations=5, dry_run=dry_run)


def propose_change(
    api_key: str,
    current_files: dict[str, str],
    history: list[dict],
    eval_results: dict,
) -> dict[str, str] | None:
    """
    Use a researcher agent to propose a single improvement to Hermes.
    Returns modified file contents, or None if no change proposed.
    """
    # Build context for the researcher
    history_text = ""
    if history:
        recent = history[-10:]  # Last 10 experiments
        history_text = "Recent experiments:\n"
        for h in recent:
            history_text += (
                f"  Run {h.get('run','?')}: score={h.get('score','?')} "
                f"delta={h.get('delta','?')} status={h.get('status','?')} "
                f"— {h.get('description','?')}\n"
            )

    # Format eval failures for the researcher
    failures_text = ""
    if eval_results and "results" in eval_results:
        failures = [r for r in eval_results["results"] if r["composite"] < 0.7]
        if failures:
            failures_text = "\nFailing scenarios:\n"
            for f in failures:
                failures_text += (
                    f"  {f['id']}: score={f['composite']:.3f} "
                    f"— {', '.join(f.get('explanations', []))}\n"
                )

    # Build the files context
    files_text = ""
    for fpath, content in current_files.items():
        fname = Path(fpath).name
        files_text += f"\n--- {fname} ({fpath}) ---\n{content}\n"

    prompt = f"""You are an autonomous researcher improving Hermes, an AI employee agent.

Your job: propose ONE small, targeted change to improve the eval score.

Current eval score: {eval_results.get('score', 'unknown')}
{history_text}
{failures_text}

Files you can modify:
{files_text}

RULES:
1. Make ONE change at a time. Small, focused, testable.
2. Prefer changes that fix the worst-scoring scenario first.
3. Simpler is better. Removing unnecessary text for same score = good.
4. Focus on making Hermes EXECUTE instead of DESCRIBE work.
5. Don't add complexity unless it demonstrably helps.
6. Think about what instructions would make the LLM actually call tools vs talk about calling tools.

OUTPUT FORMAT (strict JSON):
{{
  "description": "One sentence describing the change",
  "hypothesis": "Why this should improve the score",
  "target_scenario": "Which failing scenario this targets",
  "files": {{
    "/path/to/file": "FULL new file content here"
  }}
}}

If you believe no improvement is possible, return:
{{"description": "no_change", "files": {{}}}}
"""

    agent = AIAgent(
        model=RESEARCHER_MODEL,
        api_key=api_key,
        api_mode="anthropic_messages",
        provider="anthropic",
        max_iterations=1,  # No tool use, just thinking
        quiet_mode=True,
        skip_context_files=True,
        skip_memory=True,
    )

    try:
        response = agent.chat(prompt)
    except Exception as e:
        print(f"  Researcher error: {e}")
        return None

    # Parse JSON from response
    try:
        # Find JSON in the response (may be wrapped in markdown)
        json_match = None
        # Try to find JSON block
        if "```json" in response:
            start = response.index("```json") + 7
            end = response.index("```", start)
            json_match = response[start:end].strip()
        elif "```" in response:
            start = response.index("```") + 3
            end = response.index("```", start)
            json_match = response[start:end].strip()
        else:
            # Try parsing the whole response
            json_match = response.strip()

        proposal = json.loads(json_match)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"  Could not parse researcher response: {e}")
        print(f"  Response preview: {response[:200]}")
        return None

    if proposal.get("description") == "no_change" or not proposal.get("files"):
        print("  Researcher says: no change to propose")
        return None

    print(f"  Proposal: {proposal.get('description', '?')}")
    print(f"  Hypothesis: {proposal.get('hypothesis', '?')}")
    print(f"  Target: {proposal.get('target_scenario', '?')}")

    return proposal


def main():
    parser = argparse.ArgumentParser(description="Hermes Autoresearch Loop")
    parser.add_argument("--max-runs", type=int, default=0, help="Max experiments (0=infinite)")
    parser.add_argument("--dry-run", action="store_true", help="Skip API calls")
    parser.add_argument("--baseline-only", action="store_true", help="Just run baseline eval")
    args = parser.parse_args()

    api_key = _get_api_key()
    if not api_key and not args.dry_run:
        print("ERROR: No API key found in ~/.hermes/.env")
        sys.exit(1)

    print("=" * 70)
    print("HERMES AUTORESEARCH LOOP")
    print(f"Researcher: {RESEARCHER_MODEL} | Eval: {EVAL_MODEL}")
    print(f"Max runs: {'infinite' if args.max_runs == 0 else args.max_runs}")
    print(f"Mutable files: {[Path(f).name for f in MUTABLE_FILES]}")
    print("=" * 70)

    # Step 1: Baseline eval
    print("\n>>> Running baseline eval...")
    baseline = run_eval(dry_run=args.dry_run)
    baseline_score = baseline.get("score", 0.0)
    baseline_hash = git_current_hash()

    print(f"\nBASELINE SCORE: {baseline_score:.4f} (commit {baseline_hash})")

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

    # Step 2: THE LOOP — NEVER STOP
    run_number = 0
    prev_score = baseline_score
    best_score = baseline_score
    best_hash = baseline_hash

    while True:
        run_number += 1
        if args.max_runs > 0 and run_number > args.max_runs:
            print(f"\nReached max runs ({args.max_runs}). Stopping.")
            break

        print(f"\n{'=' * 70}")
        print(f"EXPERIMENT {run_number} | Best: {best_score:.4f} | Current: {prev_score:.4f}")
        print(f"{'=' * 70}")

        # Load current state
        current_files = read_mutable_files()
        history = load_results_history()

        # Propose a change
        print("\n>>> Proposing change...")
        proposal = propose_change(api_key, current_files, history, baseline)

        if proposal is None:
            print("  No change proposed. Sleeping 30s...")
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
            time.sleep(30)
            continue

        # Apply the change
        print("\n>>> Applying change...")
        pre_change_hash = git_current_hash()

        try:
            new_files = proposal.get("files", {})
            write_mutable_files(new_files)
        except Exception as e:
            print(f"  Error applying change: {e}")
            # Revert
            for fpath, content in current_files.items():
                Path(fpath).write_text(content, encoding="utf-8")
            continue

        # Commit the change
        desc = proposal.get("description", "autoresearch change")
        commit_hash = git_commit(f"autoresearch: {desc}")
        print(f"  Committed: {commit_hash}")

        # Run eval
        print("\n>>> Running eval...")
        t0 = time.time()
        eval_result = run_eval(dry_run=args.dry_run)
        eval_elapsed = time.time() - t0
        new_score = eval_result.get("score", 0.0)
        delta = new_score - prev_score

        print(f"\n  Score: {new_score:.4f} (delta: {delta:+.4f})")

        # Keep or discard
        if new_score > prev_score:
            status = "keep"
            print(f"  >>> KEEPING (improved by {delta:+.4f})")
            prev_score = new_score
            if new_score > best_score:
                best_score = new_score
                best_hash = commit_hash
                print(f"  >>> NEW BEST: {best_score:.4f}")
            # Update baseline for next proposal
            baseline = eval_result
        elif new_score == prev_score:
            # Same score — keep if simpler (fewer lines), discard otherwise
            old_lines = sum(len(v.splitlines()) for v in current_files.values())
            new_lines = sum(
                len(Path(f).read_text().splitlines())
                for f in new_files
                if Path(f).exists()
            )
            if new_lines < old_lines:
                status = "keep_simpler"
                print(f"  >>> KEEPING (same score, simpler: {new_lines} vs {old_lines} lines)")
                baseline = eval_result
            else:
                status = "discard_same"
                print(f"  >>> DISCARDING (same score, not simpler)")
                # Revert
                write_mutable_files(current_files)
                git_commit(f"revert: {desc}")
        else:
            status = "discard"
            print(f"  >>> DISCARDING (regressed by {delta:.4f})")
            # Revert
            write_mutable_files(current_files)
            git_commit(f"revert: {desc}")

        # Log result
        append_result({
            "timestamp": datetime.now().isoformat(),
            "run": run_number,
            "commit": commit_hash,
            "score": f"{new_score:.4f}",
            "prev_score": f"{prev_score:.4f}",
            "delta": f"{delta:+.4f}",
            "status": status,
            "description": desc,
            "elapsed_s": round(eval_elapsed, 1),
            "pass_count": eval_result.get("pass_count", 0),
            "fail_count": eval_result.get("fail_count", 0),
        })

        # Brief pause between experiments
        print(f"\n  Sleeping 10s before next experiment...")
        time.sleep(10)

    # Final summary
    print("\n" + "=" * 70)
    print("AUTORESEARCH COMPLETE")
    print(f"Total experiments: {run_number}")
    print(f"Best score: {best_score:.4f} (commit {best_hash})")
    print(f"Results: {RESULTS_TSV}")
    print("=" * 70)


if __name__ == "__main__":
    main()
