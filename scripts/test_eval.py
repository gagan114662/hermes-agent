#!/usr/bin/env python3
"""
Hermes AI Employee Evaluation Suite
Tests the agent against 10 categories of employee-like tasks.
Uses Anthropic API directly with Claude Code OAuth token.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from run_agent import AIAgent
from pathlib import Path

# Read Claude Code OAuth token from hermes .env
def _get_oauth_token():
    env_path = Path.home() / ".hermes" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("CLAUDE_CODE_OAUTH_TOKEN="):
                return line.split("=", 1)[1]
    return os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "")

MODEL = "claude-haiku-4-5-20251001"
API_KEY = _get_oauth_token()
MAX_TURNS = 3  # Cap tool iterations for speed

TESTS = [
    # Category 1: Basic Execution
    {
        "category": "1. Basic Execution",
        "prompt": (
            "Rewrite this email to sound more professional:\n\n"
            "hey mike, so i was thinking about the plumbing thing at my house. "
            "the kitchen sink is leaking again and its getting worse. can you come "
            "fix it sometime this week? thanks"
        ),
        "check": ["professional", "formatting", "instruction-following"],
    },
    # Category 2: Context + Memory (single-turn proxy — does it use business profile?)
    {
        "category": "2. Context + Identity",
        "prompt": "Write a sales email to a potential customer who runs a small law firm.",
        "check": ["uses_business_name", "uses_agent_name", "personalized"],
    },
    # Category 3: Research & Synthesis
    {
        "category": "3. Research & Synthesis",
        "prompt": "What are the top 3 trends in AI automation for small businesses right now? Give me insights I can act on.",
        "check": ["reasoning", "structured", "actionable"],
    },
    # Category 4: Multi-Step Workflow
    {
        "category": "4. Multi-Step Workflow",
        "prompt": (
            "Plan a product launch for our AI employee product targeting plumbers and HVAC companies. "
            "Cover: target audience, messaging, timeline, and channels."
        ),
        "check": ["structured", "complete", "specific"],
    },
    # Category 5: Ambiguity Handling
    {
        "category": "5. Ambiguity Handling",
        "prompt": "Help me improve my business.",
        "check": ["asks_questions", "no_assumptions", "clarifying"],
    },
    # Category 6: Edge Case — Conflicting Instructions
    {
        "category": "6. Edge Case (Conflict)",
        "prompt": "Make this shorter but add more detail: 'We sell AI employees for small businesses.'",
        "check": ["handles_conflict", "creative_solution", "no_blind_compliance"],
    },
    # Category 7: Role Simulation — Sales Rep
    {
        "category": "7. Role: Sales Rep",
        "prompt": "Write a cold outbound email sequence: 3 emails + 1 follow-up for a plumbing company owner.",
        "check": ["sequence", "personalized", "professional", "CTA"],
    },
    # Category 7b: Role Simulation — Customer Support
    {
        "category": "7b. Role: Customer Support",
        "prompt": (
            "Respond to this angry customer review:\n\n"
            "'Absolutely terrible service. I waited 3 hours for someone to show up "
            "and they didn't even fix the problem. Never using this company again. 1 star.'"
        ),
        "check": ["empathetic", "professional", "solution_oriented"],
    },
    # Category 8: Iteration & Feedback
    {
        "category": "8. Feedback Handling",
        "prompt": "This isn't good. Make it sharper and less generic: 'Our AI helps businesses save time and money.'",
        "check": ["improved", "specific", "sharper"],
    },
    # Category 9: Decision-Making
    {
        "category": "9. Decision-Making",
        "prompt": "We have $5k budget for marketing. Where should we spend it to get the most leads for our AI employee product?",
        "check": ["tradeoffs", "reasoning", "specific_recommendations"],
    },
    # Category 10: Day 1 Employee Test
    {
        "category": "10. Day 1 Employee",
        "prompt": (
            "You just joined our startup Hermes AI. We sell AI employees to small businesses at $299/mo. "
            "Your task: increase signups by 20% in 30 days. Go."
        ),
        "check": ["breaks_down_problem", "prioritizes", "actionable_steps", "execution_oriented"],
    },
]


def run_eval():
    print("=" * 70)
    print("HERMES AI EMPLOYEE EVALUATION SUITE")
    print(f"Model: {MODEL} | Anthropic Native | Max turns: {MAX_TURNS}")
    print("=" * 70)

    if not API_KEY:
        print("ERROR: No CLAUDE_CODE_OAUTH_TOKEN found in ~/.hermes/.env")
        return []

    agent = AIAgent(
        model=MODEL,
        api_key=API_KEY,
        api_mode="anthropic_messages",
        provider="anthropic",
        max_iterations=MAX_TURNS,
        quiet_mode=True,
        skip_context_files=False,
        skip_memory=True,
        verbose_logging=False,
    )

    results = []

    for i, test in enumerate(TESTS):
        cat = test["category"]
        prompt = test["prompt"]
        print(f"\n{'─' * 70}")
        print(f"TEST {i+1}/{len(TESTS)}: {cat}")
        print(f"PROMPT: {prompt[:120]}...")
        print(f"{'─' * 70}")

        t0 = time.time()
        try:
            resp = agent.chat(prompt)
            if resp is None:
                resp = "ERROR: None response from agent"
        except Exception as e:
            resp = f"ERROR: {e}"
        elapsed = time.time() - t0

        # Truncate for display
        display = resp[:2000] + ("..." if len(resp) > 2000 else "")
        print(f"\nRESPONSE ({elapsed:.1f}s):\n{display}")

        results.append({
            "category": cat,
            "prompt": prompt,
            "response": resp,
            "elapsed": round(elapsed, 1),
            "checks": test["check"],
        })

        # Reset conversation for each test (fresh context)
        agent.messages = []

    # Save raw results
    out_path = os.path.join(os.path.dirname(__file__), "eval_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n\nRaw results saved to {out_path}")

    # Print summary
    print("\n" + "=" * 70)
    print("EVALUATION SUMMARY")
    print("=" * 70)
    for r in results:
        status = "ERROR" if r["response"].startswith("ERROR") else "OK"
        print(f"  [{status}] {r['category']} — {r['elapsed']}s — {len(r['response'])} chars")

    return results


if __name__ == "__main__":
    run_eval()
