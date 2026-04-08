"""
Discovery Tool — Find the Real Problem, Not the Stated One

Every client conversation starts with a stated problem.
The stated problem is almost never the actual problem.

This tool runs structured discovery before any build begins,
extracting the real problem and saving findings to a client project doc.
"""

import json
import os
import urllib.request
from datetime import datetime
from pathlib import Path

from tools.registry import registry


def _projects_dir(client: str) -> Path:
    safe = client.lower().replace(" ", "_").replace("/", "_")
    d = Path(os.path.expanduser(f"~/.hermes/projects/{safe}"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ollama(prompt: str, timeout: int = 90) -> str:
    model = os.environ.get("OLLAMA_MODEL", "gemma3:4b")
    base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(
        f"{base}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read()).get("response", "").strip()
    except Exception as e:
        return f"Error: {e}"


_DISCOVERY_QUESTIONS = [
    "What does your current process look like, step by step from start to end?",
    "Where does it break down or slow down?",
    "What have you already tried that didn't work?",
    "What does success look like in 30 days? In 90 days?",
    "What's in your current tech stack and what are you locked into?",
]


def discovery_run(client_name: str, stated_problem: str, answers: str = "") -> str:
    """
    Run a structured discovery session to find the real problem beneath the stated one.

    Args:
        client_name: Name of the client or business
        stated_problem: What the client says they need ("we need a chatbot")
        answers: Optional — pre-filled answers to the 5 discovery questions,
                 separated by '|||'. If empty, returns the questions to ask.

    Workflow:
        1. Call discovery_run(client, stated_problem) — get questions to ask
        2. Ask client the questions, collect answers
        3. Call discovery_run(client, stated_problem, answers="ans1|||ans2|||ans3|||ans4|||ans5")
        4. AI analyzes answers and writes discovery.md
    """
    if not answers:
        lines = [
            f"Discovery questions for {client_name}:",
            f"Stated problem: \"{stated_problem}\"",
            "",
            "Ask the client these 5 questions and collect their answers:",
            "",
        ]
        for i, q in enumerate(_DISCOVERY_QUESTIONS, 1):
            lines.append(f"{i}. {q}")
        lines.append("")
        lines.append("Then call: discovery_run(client_name, stated_problem, answers='ans1|||ans2|||ans3|||ans4|||ans5')")
        return "\n".join(lines)

    # Parse answers
    ans = [a.strip() for a in answers.split("|||")]
    while len(ans) < 5:
        ans.append("(not answered)")

    qa_text = "\n".join(
        f"Q{i+1}: {_DISCOVERY_QUESTIONS[i]}\nA{i+1}: {ans[i]}"
        for i in range(5)
    )

    prompt = f"""You are a senior systems consultant analyzing a discovery call.

Client: {client_name}
Stated problem: "{stated_problem}"

Discovery answers:
{qa_text}

Analyze the above and produce a discovery document with these sections:

## Real Problem
(The actual problem beneath the stated one — be specific, not generic)

## Root Cause
(Why this problem exists — process gap, tool gap, people gap, or data gap?)

## Current Stack
(What tools/systems they use, what they're locked into)

## Success Criteria
(Precise, measurable outcomes for 30 and 90 days)

## Risk Flags
(Things that could make this project fail — legacy systems, no API, unclear ownership, etc.)

## Recommended Approach
(In 2-3 sentences: what should actually be built and why)

Be direct and specific. No filler. Write for a technical audience."""

    analysis = _ollama(prompt, timeout=90)
    if analysis.startswith("Error"):
        return analysis

    doc = f"# Discovery: {client_name}\n\n"
    doc += f"**Date:** {datetime.now().strftime('%Y-%m-%d')}\n"
    doc += f"**Stated problem:** {stated_problem}\n\n"
    doc += "---\n\n"
    doc += analysis

    path = _projects_dir(client_name) / "discovery.md"
    path.write_text(doc)

    return f"Discovery complete for {client_name}.\n\nSaved to: {path}\n\n{analysis[:600]}..."


def discovery_read(client_name: str) -> str:
    """Read the discovery document for a client."""
    path = _projects_dir(client_name) / "discovery.md"
    if not path.exists():
        return f"No discovery doc found for '{client_name}'. Run discovery_run first."
    return path.read_text()


registry.register(
    name="discovery_run",
    toolset="crm",
    schema={
        "name": "discovery_run",
        "description": "Run structured discovery to find the real problem beneath what a client says they need. Returns 5 questions to ask, then analyzes their answers to produce a discovery document. Call twice: first to get questions, then with answers to generate the doc.",
        "parameters": {
            "type": "object",
            "properties": {
                "client_name": {"type": "string", "description": "Client or business name"},
                "stated_problem": {"type": "string", "description": "What the client says they need"},
                "answers": {"type": "string", "description": "Client's answers to the 5 discovery questions, separated by '|||'. Leave empty to get the questions first."},
            },
            "required": ["client_name", "stated_problem"],
        },
    },
    handler=lambda args, **kw: discovery_run(
        client_name=args["client_name"],
        stated_problem=args["stated_problem"],
        answers=args.get("answers", ""),
    ),
)

registry.register(
    name="discovery_read",
    toolset="crm",
    schema={
        "name": "discovery_read",
        "description": "Read the discovery document for a client.",
        "parameters": {
            "type": "object",
            "properties": {
                "client_name": {"type": "string", "description": "Client name"},
            },
            "required": ["client_name"],
        },
    },
    handler=lambda args, **kw: discovery_read(client_name=args["client_name"]),
)
