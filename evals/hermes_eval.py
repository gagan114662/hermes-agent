#!/usr/bin/env python3
"""
Hermes Eval Harness — the immutable evaluation function.
This is the "prepare.py" equivalent from autoresearch.
DO NOT let the autoresearch loop modify this file.

Scores Hermes on execution vs. description across 12 test scenarios.
Returns a composite score (0.0 - 1.0) where 1.0 = perfect employee.
"""
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from run_agent import AIAgent


def _get_api_key():
    """Load API key from hermes .env."""
    env_path = Path.home() / ".hermes" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("CLAUDE_CODE_OAUTH_TOKEN="):
                return line.split("=", 1)[1]
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1]
    return os.environ.get("ANTHROPIC_API_KEY", "")


def load_scenarios(path: str = None) -> list[dict]:
    """Load test scenarios from JSON."""
    if path is None:
        path = str(Path(__file__).parent / "scenarios.json")
    with open(path) as f:
        return json.load(f)


def score_response(scenario: dict, response: str, tool_calls: list[str]) -> dict:
    """
    Score a single response against scenario criteria.
    Returns dict with individual scores and explanations.
    """
    scores = {}
    explanations = []
    response_lower = response.lower()

    # 1. Execution score: did it DO the thing vs DESCRIBE the thing?
    # Negative signals (describing work instead of doing it)
    describe_phrases = [
        "here's what you should do",
        "here's a plan",
        "i recommend you",
        "you need to",
        "you should",
        "here are the steps",
        "follow these steps",
        "the final step is yours",
        "i can't do this directly",
        "you'll need to",
        "please do the following",
    ]
    describe_count = sum(1 for p in describe_phrases if p in response_lower)
    execution_score = max(0.0, 1.0 - (describe_count * 0.2))
    scores["execution"] = execution_score
    if describe_count > 0:
        explanations.append(f"Found {describe_count} 'describing work' phrases")

    # 2. Must-not-contain check (hard failures)
    violations = []
    for phrase in scenario.get("must_not_contain", []):
        if phrase.lower() in response_lower:
            violations.append(phrase)
    if violations:
        scores["must_not"] = 0.0
        explanations.append(f"Contains forbidden: {violations}")
    else:
        scores["must_not"] = 1.0

    # 3. Must-contain-any check (at least one required phrase)
    required = scenario.get("must_contain_any", [])
    if required:
        found = [p for p in required if p.lower() in response_lower]
        scores["must_contain"] = 1.0 if found else 0.0
        if not found:
            explanations.append(f"Missing all required phrases: {required}")
    else:
        scores["must_contain"] = 1.0

    # 4. Tool usage check
    required_tools = scenario.get("must_use_tools", [])
    if required_tools:
        used = [t for t in required_tools if t in tool_calls]
        scores["tool_usage"] = len(used) / len(required_tools)
        missing = [t for t in required_tools if t not in tool_calls]
        if missing:
            explanations.append(f"Missing required tools: {missing}")
    else:
        scores["tool_usage"] = 1.0

    # 5. Response quality (length, structure)
    if len(response) < 50:
        scores["quality"] = 0.3
        explanations.append("Response too short (<50 chars)")
    elif len(response) > 10000:
        scores["quality"] = 0.7
        explanations.append("Response very long (>10k chars)")
    else:
        scores["quality"] = 1.0

    # Composite: weighted average
    weights = {
        "execution": 0.30,
        "must_not": 0.25,
        "must_contain": 0.20,
        "tool_usage": 0.15,
        "quality": 0.10,
    }
    composite = sum(scores[k] * weights[k] for k in weights)

    return {
        "composite": round(composite, 4),
        "scores": {k: round(v, 4) for k, v in scores.items()},
        "explanations": explanations,
        "violations": violations,
    }


def run_eval(
    model: str = "claude-haiku-4-5-20251001",
    max_iterations: int = 5,
    scenarios: list[dict] = None,
    dry_run: bool = False,
) -> dict:
    """
    Run the full eval suite. Returns composite score + per-scenario results.

    Args:
        model: Model to use for eval
        max_iterations: Max tool-calling loops per scenario
        scenarios: Override scenarios list
        dry_run: If True, skip actual API calls (for testing the harness)

    Returns:
        {
            "score": float (0.0 - 1.0),
            "total_weighted": float,
            "max_weighted": float,
            "results": [...per-scenario results...],
            "elapsed": float,
            "model": str,
            "timestamp": str,
        }
    """
    if scenarios is None:
        scenarios = load_scenarios()

    api_key = _get_api_key()
    if not api_key and not dry_run:
        return {"score": 0.0, "error": "No API key found"}

    agent = None
    if not dry_run:
        agent = AIAgent(
            model=model,
            api_key=api_key,
            api_mode="anthropic_messages",
            provider="anthropic",
            max_iterations=max_iterations,
            quiet_mode=True,
            skip_context_files=False,  # Load SOUL.md — that's what we're testing
            skip_memory=True,
            verbose_logging=False,
        )

    results = []
    total_weighted = 0.0
    max_weighted = 0.0
    t_start = time.time()

    for i, scenario in enumerate(scenarios):
        sid = scenario["id"]
        weight = scenario.get("weight", 1)
        max_weighted += weight

        print(f"\n[{i+1}/{len(scenarios)}] {sid} (weight={weight})")

        if dry_run:
            response = f"[DRY RUN] Would test: {scenario['prompt'][:60]}..."
            tool_calls = []
            elapsed = 0.0
        else:
            t0 = time.time()
            try:
                # Track tool calls by inspecting agent messages after run
                response = agent.chat(scenario["prompt"])
                if response is None:
                    response = "ERROR: None response"
            except Exception as e:
                response = f"ERROR: {e}"
            elapsed = time.time() - t0

            # Extract tool calls from agent's message history
            tool_calls = []
            for msg in getattr(agent, "_session_messages", []):
                if isinstance(msg, dict) and msg.get("role") == "assistant":
                    for block in msg.get("content", []):
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            tool_calls.append(block.get("name", ""))

            # Reset for next scenario
            agent.messages = []
            if hasattr(agent, "_session_messages"):
                agent._session_messages = []

        # Score
        result = score_response(scenario, response, tool_calls)
        result["id"] = sid
        result["category"] = scenario["category"]
        result["weight"] = weight
        result["elapsed"] = round(elapsed, 1)
        result["tool_calls"] = tool_calls
        result["response_length"] = len(response)
        result["response_preview"] = response[:300]

        total_weighted += result["composite"] * weight
        results.append(result)

        status = "PASS" if result["composite"] >= 0.7 else "FAIL"
        print(f"  {status} score={result['composite']:.3f} elapsed={elapsed:.1f}s tools={tool_calls[:5]}")
        if result["explanations"]:
            for exp in result["explanations"]:
                print(f"  ! {exp}")

    total_elapsed = time.time() - t_start
    final_score = total_weighted / max_weighted if max_weighted > 0 else 0.0

    summary = {
        "score": round(final_score, 4),
        "total_weighted": round(total_weighted, 4),
        "max_weighted": max_weighted,
        "results": results,
        "elapsed": round(total_elapsed, 1),
        "model": model,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "scenarios_count": len(scenarios),
        "pass_count": sum(1 for r in results if r["composite"] >= 0.7),
        "fail_count": sum(1 for r in results if r["composite"] < 0.7),
    }

    return summary


def print_summary(summary: dict):
    """Pretty-print eval summary."""
    print("\n" + "=" * 70)
    print(f"HERMES EVAL SCORE: {summary['score']:.4f}")
    print(f"Model: {summary['model']} | Time: {summary['elapsed']:.0f}s")
    print(f"Pass: {summary['pass_count']}/{summary['scenarios_count']} | "
          f"Fail: {summary['fail_count']}/{summary['scenarios_count']}")
    print("=" * 70)

    for r in summary["results"]:
        status = "PASS" if r["composite"] >= 0.7 else "FAIL"
        print(f"  [{status}] {r['id']:<25} {r['composite']:.3f}  "
              f"(exec={r['scores']['execution']:.2f} "
              f"tools={r['scores']['tool_usage']:.2f} "
              f"contain={r['scores']['must_contain']:.2f})")

    print(f"\nFinal: {summary['score']:.4f}")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    summary = run_eval(dry_run=dry)
    print_summary(summary)

    # Save results
    out_path = Path(__file__).parent / "eval_results.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nResults saved to {out_path}")
