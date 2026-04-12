"""HarnessConfig — complete specification for one harness run.

A harness run is a while-loop of AIAgent sessions that all work toward
the same task_spec until features.json is complete or a cost/session
limit is hit.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class HarnessConfig:
    """Full configuration for one harness run.

    Required fields
    ---------------
    project_dir : Path
        Root of the project the agent will work in.  All relative paths
        (progress_file, features_file, init_script) default to here.
    task_spec : str
        One-paragraph description of the goal for this run.  Injected
        verbatim into the agent system prompt every session.

    Limits
    ------
    max_sessions : int
        Hard cap on the number of agent sessions before the harness stops.
    max_cost_dollars : float
        Cumulative spend cap across all sessions (USD).
    max_session_duration_seconds : int
        Per-session wall-clock timeout.  Session is killed and marked
        failed if it exceeds this.

    Model / connection
    ------------------
    model : str
        OpenRouter-style provider/model string passed to AIAgent.
    gateway_url : str | None
        If set, AIAgent connects to this base_url instead of calling the
        AI API directly.  Useful when a running Hermes gateway is available
        for credential pooling + rate limiting.

    File paths
    ----------
    progress_file : Path
        Markdown file where session summaries are appended.
    features_file : Path
        JSON file tracking feature completion state.
    init_script : Path | None
        Optional shell script run once before the first session (e.g. to
        set up the environment, install deps).

    Tool control
    ------------
    allowed_tools : list[str] | None
        Whitelist of tool names passed to AIAgent.  None = all tools.
    forbidden_paths : list[str] | None
        Filesystem paths the agent must never write to.  Enforced by
        CommandGuard in harness/guardrails.py.
    approval_required_commands : list[str] | None
        Shell command prefixes that require human approval before running
        (on top of the defaults in tools/approval.py).
    """

    # ── Required ──────────────────────────────────────────────────────
    project_dir: Path
    task_spec: str

    # ── Limits ────────────────────────────────────────────────────────
    max_sessions: int = 50
    max_cost_dollars: float = 100.0
    max_session_duration_seconds: int = 7200  # 2 hours

    # ── Model / connection ─────────────────────────────────────────────
    model: str = "anthropic/claude-sonnet-4-6"
    gateway_url: Optional[str] = None

    # ── File paths ────────────────────────────────────────────────────
    progress_file: Optional[Path] = None
    features_file: Optional[Path] = None
    init_script: Optional[Path] = None

    # ── Tool control ──────────────────────────────────────────────────
    allowed_tools: Optional[list[str]] = None
    forbidden_paths: Optional[list[str]] = None
    approval_required_commands: Optional[list[str]] = None

    def __post_init__(self) -> None:
        self.project_dir = Path(self.project_dir)
        if self.progress_file is None:
            self.progress_file = self.project_dir / "hermes_progress.md"
        if self.features_file is None:
            self.features_file = self.project_dir / "hermes_features.json"
        if self.init_script is not None:
            self.init_script = Path(self.init_script)

    @classmethod
    def from_dict(cls, data: dict) -> "HarnessConfig":
        """Build from a plain dict (e.g. parsed from YAML/JSON spec file)."""
        data = dict(data)
        for path_key in ("project_dir", "progress_file", "features_file", "init_script"):
            if data.get(path_key):
                data[path_key] = Path(data[path_key])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
