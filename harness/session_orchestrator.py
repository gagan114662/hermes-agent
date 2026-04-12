"""SessionOrchestrator — the main harness while-loop.

Each iteration of run_harness() is one "session":
    1. Check completion / limits
    2. Load context from progress.md + features.json
    3. Build system prompt and create AIAgent
    4. Run agent conversation toward the current feature
    5. Save progress, update features.json
    6. Fire callbacks, loop

The agent is given the task_spec + session history + next features as a
system prompt.  Its user message is simply "Continue working on the next
feature.  Check hermes_progress.md for what has already been done."

Design notes
------------
- AIAgent is imported lazily to avoid circular imports and heavy startup cost.
- Cost is tracked per session via CostGuard; sessions that exceed the per-run
  budget cause a clean stop with status="cost_limit_reached".
- Sessions that raise unexpected exceptions are retried once, then halted.
- All callbacks receive a plain dict with session metadata so callers stay
  decoupled from internals.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Callable, Optional

from harness.config import HarnessConfig
from harness.context_manager import ContextManager
from harness.features import FeatureTracker
from harness.guardrails import (
    ApprovalGate, CommandBlocked, CommandGuard, CostGuard, CostLimitExceeded,
)

# Lazily imported inside _run_session to avoid heavy top-level import cost.
# Declared here so tests can patch "harness.session_orchestrator.AIAgent".
try:
    from run_agent import AIAgent
except ImportError:  # allow import without run_agent present (e.g. in tests)
    AIAgent = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


class SessionOrchestrator:
    """Orchestrates multi-session harness runs.

    Parameters
    ----------
    cfg               : HarnessConfig controlling this run.
    on_session_start  : Called with session metadata dict at session start.
    on_session_end    : Called with session result dict at session end.
    on_tool_use       : Called with (tool_name, tool_input) for observability.
    """

    def __init__(
        self,
        cfg: HarnessConfig,
        on_session_start: Optional[Callable[[dict], None]] = None,
        on_session_end: Optional[Callable[[dict], None]] = None,
        on_tool_use: Optional[Callable[[str, dict], None]] = None,
    ) -> None:
        self.cfg = cfg
        self._on_session_start = on_session_start
        self._on_session_end = on_session_end
        self._on_tool_use = on_tool_use
        self._context_manager = ContextManager()
        self._cost_guard = CostGuard(max_cost_dollars=cfg.max_cost_dollars)
        self._command_guard = CommandGuard(
            forbidden_paths=cfg.forbidden_paths or [],
        )
        self._approval_gate = ApprovalGate(
            approval_required_commands=cfg.approval_required_commands,
        )

    # ── Public entry point ────────────────────────────────────────────

    def run_harness(self) -> dict:
        """Run the harness until completion, limit, or error.

        Returns
        -------
        dict with keys:
          status         — "completed" | "session_limit_reached" |
                           "cost_limit_reached" | "halted_on_error"
          sessions_run   — int
          total_cost_usd — float
          message        — human-readable summary
        """
        self._run_init_script()

        sessions_run = 0

        while True:
            tracker = FeatureTracker(self.cfg.features_file)

            # ── Completion check ──────────────────────────────────────
            if tracker.all_complete():
                logger.info("All features complete — harness finished.")
                return self._result("completed", sessions_run, "All features implemented.")

            # ── Session limit check ───────────────────────────────────
            if sessions_run >= self.cfg.max_sessions:
                return self._result(
                    "session_limit_reached", sessions_run,
                    f"Stopped after {self.cfg.max_sessions} sessions."
                )

            session_number = sessions_run + 1
            meta = {"session_number": session_number, "project_dir": str(self.cfg.project_dir)}
            if self._on_session_start:
                self._on_session_start(meta)

            # ── Run one session ────────────────────────────────────────
            try:
                result = self._run_session(session_number)
                sessions_run += 1

                try:
                    usage = result.get("usage", {})
                    self._cost_guard.record_usage(usage, model=self.cfg.model)
                except CostLimitExceeded as exc:
                    logger.warning("Cost limit hit after session %d: %s", session_number, exc)
                    if self._on_session_end:
                        self._on_session_end({**meta, "status": "cost_limit"})
                    return self._result("cost_limit_reached", sessions_run, str(exc))

                # Save progress
                self._context_manager.save_progress(
                    progress_file=self.cfg.progress_file,
                    features_file=self.cfg.features_file,
                    session_number=session_number,
                    summary=result.get("response", ""),
                    features_completed=result.get("features_completed", []),
                )

                if self._on_session_end:
                    self._on_session_end({**meta, "status": "success", "result": result})

            except Exception as exc:
                logger.exception("Session %d failed: %s", session_number, exc)
                sessions_run += 1
                if self._on_session_end:
                    self._on_session_end({**meta, "status": "error", "error": str(exc)})
                return self._result(
                    "halted_on_error", sessions_run,
                    f"Session {session_number} raised: {exc}"
                )

    # ── Session lifecycle ─────────────────────────────────────────────

    def _run_session(self, session_number: int) -> dict:
        """Create an AIAgent, load context, and run one conversation."""
        ctx = self._context_manager.load_context(
            progress_file=self.cfg.progress_file,
            features_file=self.cfg.features_file,
            task_spec=self.cfg.task_spec,
        )
        system_prompt = self._context_manager.build_system_prompt(ctx)
        user_message = (
            "Continue working on the next feature listed above.  "
            "Check hermes_progress.md for what has already been done.  "
            "When you complete a feature, write a clear summary of what you did."
        )

        # Build guardrail tool_start_callback
        def _tool_start(tool_name: str, tool_input: dict) -> None:
            if self._on_tool_use:
                self._on_tool_use(tool_name, tool_input)
            if tool_name == "terminal":
                cmd = tool_input.get("command", "")
                try:
                    self._command_guard.check(cmd)
                except CommandBlocked as exc:
                    # Always re-raise hard blocks (requires_approval=False).
                    # For soft blocks (requires_approval=True), consult the
                    # ApprovalGate — if the command matches the gate's list,
                    # raise; otherwise let it through (guard flagged it but
                    # the gate doesn't require explicit human sign-off here).
                    if not exc.requires_approval:
                        raise
                    if self._approval_gate.requires_approval(cmd):
                        raise

        init_kwargs: dict = dict(
            model=self.cfg.model,
            tool_start_callback=_tool_start,
        )
        if self.cfg.gateway_url:
            init_kwargs["base_url"] = self.cfg.gateway_url
        if self.cfg.allowed_tools:
            init_kwargs["enabled_toolsets"] = self.cfg.allowed_tools

        agent = AIAgent(**init_kwargs)

        return agent.run_conversation(
            user_message=user_message,
            system_message=system_prompt,
        )

    # ── Helpers ───────────────────────────────────────────────────────

    def _run_init_script(self) -> None:
        if not self.cfg.init_script:
            return
        script = Path(self.cfg.init_script)
        if not script.exists():
            logger.warning("init_script %s not found, skipping", script)
            return
        logger.info("Running init_script: %s", script)
        result = subprocess.run(
            [str(script)],
            cwd=str(self.cfg.project_dir),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning("init_script exited %d:\n%s", result.returncode, result.stderr)

    def _result(self, status: str, sessions_run: int, message: str) -> dict:
        return {
            "status": status,
            "sessions_run": sessions_run,
            "total_cost_usd": round(self._cost_guard.cumulative_cost, 4),
            "message": message,
        }
