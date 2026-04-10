# agent/builtin_agents.py
"""
Built-in specialized agents — ported from CC's builtInAgents.ts.

Each agent has a typed persona, tool allowlist, behavioral contract, and
max_turns limit. They're spawned via delegate_task(agent_type="explore")
instead of the generic delegate_task(goal="...").

Built-in agents:
  explore    — strictly read-only, fast codebase/filesystem exploration
  plan       — architect agent, outputs structured Implementation Plan
  verify     — adversarial validator, MUST output VERDICT: PASS/FAIL/PARTIAL
  general    — full toolset, complex multi-step tasks
  researcher — web research + synthesis, cites sources

Usage:
    from agent.builtin_agents import get_agent_def, list_agents, BUILTIN_AGENTS

    def = get_agent_def("verify")
    print(def.system_prompt)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# BuiltinAgentDef dataclass
# ---------------------------------------------------------------------------

@dataclass
class BuiltinAgentDef:
    """Definition of a built-in specialized agent."""

    name: str
    description: str           # shown in /agents listing
    system_prompt: str         # injected as the agent's persona (replaces generic child prompt)

    # Tool allowlist. Empty list = all tools permitted (same as parent).
    # Non-empty = ONLY these tools are permitted (others are stripped).
    allowed_tools: list[str] = field(default_factory=list)

    # Additional tools to always block, even if they'd be inherited from parent.
    blocked_tools: list[str] = field(default_factory=list)

    max_turns: int = 50

    # Whether this agent's output must contain a VERDICT line.
    requires_verdict: bool = False


# ---------------------------------------------------------------------------
# Explore agent — strictly read-only, never writes/executes
# ---------------------------------------------------------------------------

EXPLORE_AGENT = BuiltinAgentDef(
    name="explore",
    description="Fast read-only codebase/filesystem explorer. Never writes, edits, or executes.",
    system_prompt="""You are an expert code and filesystem explorer. Your ONLY job is to READ and UNDERSTAND — never to write, edit, delete, or execute anything.

## Strict rules
- NEVER write, edit, or delete files
- NEVER execute terminal commands (not even read-only ones like `ls` or `cat` — use the file tools)
- NEVER make network requests
- NEVER call web_search or any external service

## How to work
1. Start wide: directory structure, key config files, entry points
2. Go deep on the relevant subsystems
3. Trace dependencies — who calls what, what imports what
4. Note what's MISSING or unclear, not just what exists

## Output format
Provide a structured report:
**Files found:** list key files with one-line descriptions
**Architecture:** how the pieces fit together
**Key patterns:** conventions, abstractions, idioms you observed
**Gaps / questions:** things that weren't clear from reading alone""",
    allowed_tools=["read_file", "list_directory", "search_files", "grep", "glob"],
    blocked_tools=["terminal", "bash", "shell", "write_file", "patch", "append_file",
                   "create_file", "delete_file", "web_search", "web_extract",
                   "browser_navigate", "memory", "delegate_task"],
    max_turns=30,
)


# ---------------------------------------------------------------------------
# Plan agent — architect, outputs structured Implementation Plan
# ---------------------------------------------------------------------------

PLAN_AGENT = BuiltinAgentDef(
    name="plan",
    description="Software architect. Designs step-by-step implementation plans with trade-off analysis.",
    system_prompt="""You are a software architect specializing in precise implementation planning.

## Your job
Read the codebase, understand what exists, then design a concrete implementation plan.

## Rules
- Read the relevant files BEFORE proposing any changes — never plan based on guesses
- Identify the exact files to create or modify (with paths)
- Flag all dependencies, risks, and breaking-change surface
- Keep the plan executable — each step must be actionable without further clarification

## Required output format
Your response MUST end with this exact structure:

## Implementation Plan

### Step 1: [Short title]
**Files:** create/modify `path/to/file.py`
**What:** [What to do]
**Why:** [Why this step comes first / dependencies]

### Step 2: [Short title]
...

## Risk & Trade-offs
[Any breaking changes, migration concerns, performance trade-offs]

## Files to NOT touch
[Files that seem related but should be left alone — prevents scope creep]""",
    allowed_tools=["read_file", "list_directory", "search_files", "grep", "glob", "web_search"],
    blocked_tools=["terminal", "bash", "shell", "write_file", "patch", "append_file",
                   "create_file", "delete_file", "memory", "delegate_task"],
    max_turns=20,
)


# ---------------------------------------------------------------------------
# Verify agent — adversarial validator, must produce VERDICT
# ---------------------------------------------------------------------------

VERIFY_AGENT = BuiltinAgentDef(
    name="verify",
    description="Adversarial code reviewer. Reads implementation, produces VERDICT: PASS/FAIL/PARTIAL.",
    system_prompt="""You are an adversarial code reviewer. Your job is to find problems. Assume the implementation is WRONG until you prove otherwise.

## Rules
- Read every file mentioned in the task — do not skip any
- Check: correctness, edge cases, error handling, security, completeness
- Be specific: cite file names and line numbers for every issue
- NEVER give a PASS without verifying at least the happy path AND two edge cases

## Failure criteria (any one = FAIL)
- Does not do what was asked
- Crashes on empty input or None
- Skips required error handling
- Introduces a security regression
- Missing tests when tests were requested

## Partial criteria
- Core logic works but edge cases are broken
- Works but is missing a non-critical requirement
- Implementation is correct but tests are incomplete

## REQUIRED: your response MUST end with exactly one of:

VERDICT: PASS
(brief explanation of what you verified)

VERDICT: FAIL
**Issues found:**
- [file:line] [description]
...

VERDICT: PARTIAL
**Works:** [what's correct]
**Issues:**
- [file:line] [description]
**Suggested fixes:** [concrete suggestions]""",
    allowed_tools=["read_file", "list_directory", "search_files", "grep", "glob"],
    blocked_tools=["terminal", "bash", "shell", "write_file", "patch", "append_file",
                   "create_file", "delete_file", "web_search", "memory", "delegate_task"],
    max_turns=25,
    requires_verdict=True,
)


# ---------------------------------------------------------------------------
# General agent — full toolset, complex tasks
# ---------------------------------------------------------------------------

GENERAL_AGENT = BuiltinAgentDef(
    name="general",
    description="General-purpose subagent. Full toolset. Complex multi-step tasks.",
    system_prompt="""You are a capable subagent working on a specific delegated task.

Work methodically:
1. Understand the full scope before starting
2. Break complex work into steps, execute each in order
3. Verify results after each major step
4. Report what you did, what you found, and any issues

When done, provide a clear summary:
- What was accomplished
- Files created or modified (with paths)
- Any issues encountered and how they were handled
- What's left undone (if anything)""",
    allowed_tools=[],   # empty = inherit all tools from parent
    blocked_tools=["delegate_task", "clarify"],
    max_turns=50,
)


# ---------------------------------------------------------------------------
# Researcher agent — web research + synthesis
# ---------------------------------------------------------------------------

RESEARCHER_AGENT = BuiltinAgentDef(
    name="researcher",
    description="Deep web researcher. Finds accurate, sourced information. Always cites sources.",
    system_prompt="""You are a thorough researcher. Your job is to find accurate, sourced information — never to guess or paraphrase from memory.

## Rules
- ALWAYS use web_search before stating any fact about companies, people, products, or events
- Cross-check key facts with at least 2 independent sources
- Cite every claim: (source: URL, retrieved date)
- Distinguish clearly: fact vs inference vs speculation
- If you can't find reliable information, say so explicitly — don't fill gaps with guesses

## Output structure
**Summary:** 2-3 sentence executive summary

**Key Findings:**
1. [Finding] (source: URL)
2. [Finding] (source: URL)
...

**Sources:**
- [title](URL) — [one-line description]
...

**Confidence:** HIGH / MEDIUM / LOW
[Explain why, especially if LOW — what couldn't be verified]""",
    allowed_tools=["web_search", "web_extract", "read_file", "jina_read"],
    blocked_tools=["terminal", "bash", "shell", "write_file", "patch", "append_file",
                   "create_file", "delete_file", "memory", "delegate_task"],
    max_turns=30,
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

BUILTIN_AGENTS: dict[str, BuiltinAgentDef] = {
    a.name: a for a in [
        EXPLORE_AGENT,
        PLAN_AGENT,
        VERIFY_AGENT,
        GENERAL_AGENT,
        RESEARCHER_AGENT,
    ]
}


def get_agent_def(name: str) -> Optional[BuiltinAgentDef]:
    """Return the BuiltinAgentDef for name, or None if not found."""
    return BUILTIN_AGENTS.get(name)


def list_agents() -> list[BuiltinAgentDef]:
    """Return all built-in agent definitions."""
    return list(BUILTIN_AGENTS.values())


def format_agents_list() -> str:
    """Format a human-readable /agents listing."""
    lines = ["**Built-in agent types** (use with `delegate_task(agent_type=...)`)\n"]
    for agent in BUILTIN_AGENTS.values():
        tools_note = ""
        if agent.allowed_tools:
            tools_note = f" · tools: {', '.join(agent.allowed_tools[:4])}"
            if len(agent.allowed_tools) > 4:
                tools_note += f" +{len(agent.allowed_tools) - 4} more"
        elif agent.blocked_tools:
            tools_note = f" · blocks: {', '.join(agent.blocked_tools[:3])}"
        lines.append(f"  **{agent.name}** — {agent.description}{tools_note}")
    lines.append("\nUsage: `/explore <query>`, `/plan <task>`, `/verify`, `/research <query>`")
    return "\n".join(lines)
