# agent/task_graph.py
"""
Task graph executor — decompose → explore → parallelize → synthesize → verify → heal.

This is Hermes's answer to "what does an AI agent do with a big ambiguous goal?"
Claude Code runs one agent sequentially. Hermes runs a coordinated graph.

Pipeline:
    1. DECOMPOSE  — Plan agent breaks goal into independent subtasks
    2. EXPLORE    — Explore agent reads relevant code/data first (optional)
    3. PARALLELIZE — Spawn all independent subtasks simultaneously
    4. SYNTHESIZE  — Collect results, produce unified output
    5. VERIFY      — Verify agent checks the whole result
    6. HEAL        — If FAIL/PARTIAL, repair agent fixes issues

What makes this better than Claude Code:
  - CC runs tasks sequentially in one context window
  - Hermes runs independent tasks in parallel → faster
  - Hermes verifies the whole output, not just the last step
  - Hermes can heal failures automatically
  - Memdir ensures no agent re-discovers what others already found

Usage:
    from agent.task_graph import run_task_graph

    result = run_task_graph(
        goal="Refactor the authentication system to use JWT",
        parent_agent=agent,
        explore_first=True,
        auto_verify=True,
        auto_heal=True,
    )
    print(result.summary)

Or via slash command: /graph <goal>
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class SubtaskResult:
    index: int
    goal: str
    status: str         # "completed" | "failed" | "skipped"
    summary: str
    duration_seconds: float = 0.0


@dataclass
class TaskGraphResult:
    goal: str
    status: str             # "completed" | "partial" | "failed"
    summary: str            # final synthesized output
    subtasks: list[SubtaskResult] = field(default_factory=list)
    explore_summary: str = ""
    verify_verdict: str = ""
    heal_log: list[dict] = field(default_factory=list)
    total_duration_seconds: float = 0.0
    error: str = ""


# ---------------------------------------------------------------------------
# Decomposition prompt
# ---------------------------------------------------------------------------

_DECOMPOSE_PROMPT = """You are a task decomposition specialist.

Given a goal, break it into the MINIMUM number of independent subtasks that can run in parallel.

Rules:
- Each subtask must be independently executable (no dependency on another subtask's output)
- Maximum 4 subtasks (parallelism limit)
- If the goal is simple (1-2 steps), return just 1 subtask = the original goal
- Don't over-decompose — only split when there's genuine parallelism
- Each subtask must be concrete and actionable

Output ONLY valid JSON, no markdown, no explanation:
{{
  "subtasks": [
    {{"goal": "...", "rationale": "..."}},
    ...
  ],
  "synthesis_instructions": "how to combine the subtask results into a final answer"
}}

Goal to decompose: {goal}"""


_SYNTHESIS_PROMPT = """Synthesize the results from {n} parallel subtasks into a single coherent response.

Original goal: {goal}

Synthesis instructions: {synthesis_instructions}

Subtask results:
{results_text}

Write a clear, complete response that addresses the original goal using all subtask results.
Do not just list the results — integrate them into a unified answer."""


# ---------------------------------------------------------------------------
# Core executor
# ---------------------------------------------------------------------------

def run_task_graph(
    goal: str,
    parent_agent,
    *,
    explore_first: bool = True,
    auto_verify: bool = True,
    auto_heal: bool = True,
    max_subtasks: int = 4,
    quiet: bool = False,
) -> TaskGraphResult:
    """
    Run a full task graph for the given goal.

    Steps:
        1. Decompose goal into parallel subtasks (Plan agent)
        2. Optionally run Explore agent first to build shared context
        3. Run all subtasks in parallel
        4. Synthesize results
        5. Optionally verify (Verify agent)
        6. Optionally heal if FAIL/PARTIAL (Repair agent)

    Returns TaskGraphResult with full audit trail.
    """
    start = time.monotonic()

    if not goal or not goal.strip():
        return TaskGraphResult(
            goal=goal, status="failed", summary="", error="Empty goal"
        )

    session_id = getattr(parent_agent, "session_id", "default") or "default"

    def _log(msg: str) -> None:
        if not quiet:
            logger.info("task_graph: %s", msg)

    _log(f"starting for goal: {goal[:80]}")

    # ── Step 1: Decompose ────────────────────────────────────────────────────
    _log("step 1/5: decomposing goal")
    subtask_goals, synthesis_instructions = _decompose_goal(
        goal, parent_agent, max_subtasks
    )
    _log(f"decomposed into {len(subtask_goals)} subtasks")

    # ── Step 2: Explore (optional) ───────────────────────────────────────────
    explore_summary = ""
    if explore_first and len(subtask_goals) > 1:
        _log("step 2/5: running explore agent first")
        explore_summary = _run_explore(goal, parent_agent)
        if explore_summary:
            # Write to memdir so all parallel agents see it
            from agent.memdir import get_session_memdir
            memdir = get_session_memdir(session_id)
            memdir.write("explore_findings", explore_summary, source="explore")
            _log(f"explore complete: {len(explore_summary)} chars")

    # ── Step 3: Parallelize ──────────────────────────────────────────────────
    _log(f"step 3/5: running {len(subtask_goals)} subtasks in parallel")
    subtask_results = _run_parallel_subtasks(
        goal=goal,
        subtask_goals=subtask_goals,
        parent_agent=parent_agent,
        session_id=session_id,
        explore_summary=explore_summary,
    )

    completed = [r for r in subtask_results if r.status == "completed"]
    failed = [r for r in subtask_results if r.status == "failed"]
    _log(f"subtasks: {len(completed)} completed, {len(failed)} failed")

    # ── Step 4: Synthesize ───────────────────────────────────────────────────
    _log("step 4/5: synthesizing results")
    if not completed:
        return TaskGraphResult(
            goal=goal,
            status="failed",
            summary="All subtasks failed.",
            subtasks=subtask_results,
            explore_summary=explore_summary,
            total_duration_seconds=round(time.monotonic() - start, 2),
            error="No completed subtasks to synthesize",
        )

    synthesis = _synthesize(
        goal=goal,
        subtask_results=completed,
        synthesis_instructions=synthesis_instructions,
        parent_agent=parent_agent,
    )

    # ── Step 5: Verify (optional) ────────────────────────────────────────────
    verify_verdict = ""
    heal_log = []

    if auto_verify:
        _log("step 5/5: verifying synthesis")
        verify_verdict, heal_log = _verify_and_heal(
            goal=goal,
            synthesis=synthesis,
            parent_agent=parent_agent,
            auto_heal=auto_heal,
        )
        _log(f"verify result: {verify_verdict}")

    # ── Build final result ───────────────────────────────────────────────────
    if failed:
        status = "partial"
    elif verify_verdict == "FAIL":
        status = "partial"
    else:
        status = "completed"

    return TaskGraphResult(
        goal=goal,
        status=status,
        summary=synthesis,
        subtasks=subtask_results,
        explore_summary=explore_summary,
        verify_verdict=verify_verdict,
        heal_log=heal_log,
        total_duration_seconds=round(time.monotonic() - start, 2),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _decompose_goal(
    goal: str,
    parent_agent,
    max_subtasks: int,
) -> tuple[list[str], str]:
    """
    Use the Plan agent to decompose goal into parallel subtasks.
    Returns (subtask_goal_list, synthesis_instructions).
    Falls back to [goal] on any error.
    """
    try:
        from tools.delegate_tool import delegate_task

        decompose_goal = _DECOMPOSE_PROMPT.format(goal=goal)
        result_json = delegate_task(
            goal=decompose_goal,
            agent_type="plan",
            max_iterations=10,
            parent_agent=parent_agent,
        )
        data = json.loads(result_json)
        summary = data.get("results", [{}])[0].get("summary", "")

        # Extract JSON from summary (plan agent wraps it in markdown sometimes)
        import re
        json_match = re.search(r'\{.*\}', summary, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            subtasks = parsed.get("subtasks", [])
            goals = [t["goal"] for t in subtasks if t.get("goal")][:max_subtasks]
            synthesis = parsed.get("synthesis_instructions", "Combine all results.")
            if goals:
                return goals, synthesis
    except Exception as exc:
        logger.debug("task_graph._decompose_goal failed: %s", exc)

    return [goal], "Present the result directly."


def _run_explore(goal: str, parent_agent) -> str:
    """Run explore agent to understand the context before parallel work."""
    try:
        from tools.delegate_tool import delegate_task

        explore_goal = (
            f"Quickly explore the codebase/data relevant to this task and report "
            f"what you find. Focus on: file structure, key files, patterns, "
            f"tech stack, and anything directly relevant to:\n\n{goal}"
        )
        result_json = delegate_task(
            goal=explore_goal,
            agent_type="explore",
            max_iterations=15,
            parent_agent=parent_agent,
        )
        data = json.loads(result_json)
        return data.get("results", [{}])[0].get("summary", "")
    except Exception as exc:
        logger.debug("task_graph._run_explore failed: %s", exc)
        return ""


def _run_parallel_subtasks(
    goal: str,
    subtask_goals: list[str],
    parent_agent,
    session_id: str,
    explore_summary: str,
) -> list[SubtaskResult]:
    """
    Run all subtasks in parallel using delegate_task batch mode.
    Injects memdir context into each subtask.
    """
    from agent.memdir import inject_memdir_context

    # Build context with memdir (explore findings + any other known facts)
    base_context = inject_memdir_context(session_id, explore_summary or None)

    if len(subtask_goals) == 1:
        # Single task — run directly, no batch overhead
        return [_run_single_subtask(0, subtask_goals[0], base_context, parent_agent)]

    # Batch mode — parallel execution
    tasks = [
        {
            "goal": sg,
            "context": base_context,
            "toolsets": None,
        }
        for sg in subtask_goals
    ]

    try:
        from tools.delegate_tool import delegate_task
        result_json = delegate_task(
            tasks=tasks,
            parent_agent=parent_agent,
        )
        data = json.loads(result_json)
        results = []
        for r in data.get("results", []):
            results.append(SubtaskResult(
                index=r.get("task_index", 0),
                goal=subtask_goals[r.get("task_index", 0)] if r.get("task_index", 0) < len(subtask_goals) else "",
                status=r.get("status", "failed"),
                summary=r.get("summary", ""),
                duration_seconds=r.get("duration_seconds", 0.0),
            ))
        return results
    except Exception as exc:
        logger.warning("task_graph._run_parallel_subtasks failed: %s", exc)
        return [SubtaskResult(i, g, "failed", str(exc)) for i, g in enumerate(subtask_goals)]


def _run_single_subtask(
    index: int,
    goal: str,
    context: str,
    parent_agent,
) -> SubtaskResult:
    """Run a single subtask and return its result."""
    start = time.monotonic()
    try:
        from tools.delegate_tool import delegate_task
        result_json = delegate_task(
            goal=goal,
            context=context or None,
            parent_agent=parent_agent,
        )
        data = json.loads(result_json)
        r = data.get("results", [{}])[0]
        return SubtaskResult(
            index=index,
            goal=goal,
            status=r.get("status", "failed"),
            summary=r.get("summary", ""),
            duration_seconds=round(time.monotonic() - start, 2),
        )
    except Exception as exc:
        return SubtaskResult(
            index=index,
            goal=goal,
            status="failed",
            summary=str(exc),
            duration_seconds=round(time.monotonic() - start, 2),
        )


def _synthesize(
    goal: str,
    subtask_results: list[SubtaskResult],
    synthesis_instructions: str,
    parent_agent,
) -> str:
    """Ask the model to synthesize multiple subtask results into one answer."""
    if len(subtask_results) == 1:
        return subtask_results[0].summary

    results_text = "\n\n".join(
        f"**Subtask {r.index + 1}:** {r.goal}\n{r.summary}"
        for r in subtask_results
    )

    synthesis_goal = _SYNTHESIS_PROMPT.format(
        n=len(subtask_results),
        goal=goal,
        synthesis_instructions=synthesis_instructions,
        results_text=results_text,
    )

    try:
        from tools.delegate_tool import delegate_task
        result_json = delegate_task(
            goal=synthesis_goal,
            agent_type="general",
            max_iterations=10,
            parent_agent=parent_agent,
        )
        data = json.loads(result_json)
        return data.get("results", [{}])[0].get("summary", results_text)
    except Exception as exc:
        logger.warning("task_graph._synthesize failed: %s", exc)
        return results_text


def _verify_and_heal(
    goal: str,
    synthesis: str,
    parent_agent,
    auto_heal: bool,
) -> tuple[str, list[dict]]:
    """
    Run verify agent on synthesis. If FAIL/PARTIAL and auto_heal,
    run repair agent and re-verify.
    Returns (final_verdict, heal_log).
    """
    from agent.self_heal import _extract_verdict, MAX_HEAL_ATTEMPTS

    heal_log = []

    verify_goal = (
        f"Verify this response to the goal: {goal}\n\n"
        f"**Response to verify:**\n{synthesis[:2000]}\n\n"
        f"Check: correctness, completeness, accuracy.\n"
        f"End with VERDICT: PASS, FAIL, or PARTIAL."
    )

    for attempt in range(1, (MAX_HEAL_ATTEMPTS + 1) if auto_heal else 2):
        try:
            from tools.delegate_tool import delegate_task
            result_json = delegate_task(
                goal=verify_goal,
                agent_type="verify",
                max_iterations=15,
                parent_agent=parent_agent,
            )
            data = json.loads(result_json)
            verify_response = data.get("results", [{}])[0].get("summary", "")
        except Exception as exc:
            logger.debug("task_graph._verify failed: %s", exc)
            break

        verdict = _extract_verdict(verify_response)
        heal_log.append({"attempt": attempt, "verdict": verdict, "response": verify_response[:400]})

        if verdict == "PASS" or not auto_heal or verdict is None:
            return verdict or "UNKNOWN", heal_log

        if attempt >= MAX_HEAL_ATTEMPTS:
            return verdict, heal_log

        # Repair
        try:
            repair_goal = (
                f"Fix these issues with the response to: {goal}\n\n"
                f"**Verify findings:**\n{verify_response}\n\n"
                f"Produce a corrected, complete response."
            )
            r2_json = delegate_task(
                goal=repair_goal,
                agent_type="general",
                max_iterations=30,
                parent_agent=parent_agent,
            )
            r2_data = json.loads(r2_json)
            synthesis = r2_data.get("results", [{}])[0].get("summary", synthesis)
            heal_log[-1]["repair_done"] = True
            # Update verify goal for next round
            verify_goal = (
                f"Verify this revised response to: {goal}\n\n"
                f"**Revised response:**\n{synthesis[:2000]}\n\n"
                f"End with VERDICT: PASS, FAIL, or PARTIAL."
            )
        except Exception as exc:
            logger.debug("task_graph._heal failed: %s", exc)
            break

    return heal_log[-1].get("verdict", "UNKNOWN") if heal_log else "UNKNOWN", heal_log


# ---------------------------------------------------------------------------
# Format for display
# ---------------------------------------------------------------------------

def format_graph_result(result: TaskGraphResult) -> str:
    """Format a TaskGraphResult for display to the user."""
    lines = []

    # Header
    status_icons = {"completed": "✅", "partial": "⚠️", "failed": "❌"}
    icon = status_icons.get(result.status, "❓")
    lines.append(f"{icon} **Task graph complete** ({result.total_duration_seconds}s)")

    # Subtasks
    if len(result.subtasks) > 1:
        lines.append(f"\n**Subtasks:** {len(result.subtasks)} ran in parallel")
        for st in result.subtasks:
            st_icon = "✓" if st.status == "completed" else "✗"
            lines.append(f"  {st_icon} {st.goal[:60]} ({st.duration_seconds}s)")

    # Verify
    if result.verify_verdict:
        v_icons = {"PASS": "✅", "FAIL": "❌", "PARTIAL": "⚠️"}
        v_icon = v_icons.get(result.verify_verdict, "❓")
        lines.append(f"\n**Verification:** {v_icon} {result.verify_verdict}")

    # Summary
    lines.append(f"\n**Result:**\n{result.summary}")

    return "\n".join(lines)
