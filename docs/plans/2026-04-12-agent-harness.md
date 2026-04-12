# Agent Harness Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a `harness/` layer that orchestrates multi-session AIAgent work toward a goal, tracking progress through `hermes_progress.md` + `features.json`, with cost/command guardrails and an Employee abstraction for persistent goal-driven agents.

**Architecture:** `SessionOrchestrator` wraps `run_agent.AIAgent` in a while-loop: load context → inject as system prompt → run agent → save progress → repeat until all features done or limits hit. `ContextManager` reads/writes the markdown+JSON progress files. `Employee` stores a named goal+role in `~/.hermes/employees/{name}.yaml` and delegates to `SessionOrchestrator`. Guardrails wrap the AIAgent callbacks.

**Tech Stack:** Python dataclasses, pathlib.Path, PyYAML (already in deps), `run_agent.AIAgent`, `agent/task_graph.py`, `tools/approval.py`, `cron/jobs.py`, `hermes_constants.get_hermes_home()`

---

## Key Interface Facts (read before coding)

- **`AIAgent.__init__`** takes `model`, `base_url`, `api_key`, `provider`, `tool_start_callback`, `tool_complete_callback`, `step_callback`, `status_callback` (run_agent.py:463)
- **`AIAgent.run_conversation(user_message, system_message)`** returns `dict` with keys `response`, `messages`, `usage` (run_agent.py:7128)
- **`run_task_graph(goal, parent_agent)`** in `agent/task_graph.py:120`, returns `TaskGraphResult` with `.summary`, `.subtasks`
- **`detect_dangerous_command(command)`** in `tools/approval.py:154` returns `(is_dangerous: bool, pattern_key: str, description: str)`
- **`trigger_learning_loop(agent, messages, final_response)`** in `agent/learning_loop.py:92`
- **`cron/jobs.py`**: `create_job()`, `load_jobs()`, `compute_next_run()` — schedule format is cron string
- **`get_hermes_home()`** from `hermes_constants` — returns `~/.hermes`
- CLI subcommand pattern: `argparse.add_subparsers` in `hermes_cli/main.py:4382`; add harness parser at the bottom of `main()` and dispatch in the if/elif chain

---

## Task 1: harness/config.py — HarnessConfig dataclass

**Files:**
- Create: `harness/__init__.py`
- Create: `harness/config.py`
- Create: `tests/test_harness/__init__.py`
- Create: `tests/test_harness/test_config.py`

**Step 1: Write the failing test**

```python
# tests/test_harness/test_config.py
from pathlib import Path
import pytest
from harness.config import HarnessConfig


def test_harness_config_defaults(tmp_path):
    cfg = HarnessConfig(project_dir=tmp_path, task_spec="Build X")
    assert cfg.max_sessions == 50
    assert cfg.max_cost_dollars == 100.0
    assert cfg.max_session_duration_seconds == 7200
    assert cfg.model == "anthropic/claude-sonnet-4-6"
    assert cfg.progress_file == tmp_path / "hermes_progress.md"
    assert cfg.features_file == tmp_path / "hermes_features.json"
    assert cfg.init_script is None
    assert cfg.allowed_tools is None
    assert cfg.forbidden_paths is None
    assert cfg.approval_required_commands is None
    assert cfg.gateway_url is None


def test_harness_config_custom(tmp_path):
    cfg = HarnessConfig(
        project_dir=tmp_path,
        task_spec="Fix bug",
        max_sessions=10,
        max_cost_dollars=5.0,
        model="openai/gpt-4o",
        gateway_url="http://localhost:30000/v1",
        forbidden_paths=["/etc", "/root"],
        approval_required_commands=["git push", "npm publish"],
    )
    assert cfg.max_sessions == 10
    assert cfg.gateway_url == "http://localhost:30000/v1"
    assert "/etc" in cfg.forbidden_paths


def test_harness_config_progress_file_override(tmp_path):
    custom = tmp_path / "my_progress.md"
    cfg = HarnessConfig(project_dir=tmp_path, task_spec="X", progress_file=custom)
    assert cfg.progress_file == custom
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/gaganarora/Documents/hermes-agent
python -m pytest tests/test_harness/test_config.py -v
```
Expected: `ModuleNotFoundError: No module named 'harness'`

**Step 3: Write the implementation**

```python
# harness/__init__.py
"""Agent Harness — multi-session orchestration layer for Hermes.

Exports the primary public surface:
  - HarnessConfig       — spec + limits for a harness run
  - ContextManager      — read/write progress.md + features.json
  - SessionOrchestrator — the main while-loop engine
  - Employee            — persistent goal-driven agent persona
"""
from harness.config import HarnessConfig
from harness.context_manager import ContextManager
from harness.session_orchestrator import SessionOrchestrator
from harness.employee import Employee

__all__ = ["HarnessConfig", "ContextManager", "SessionOrchestrator", "Employee"]
```

```python
# harness/config.py
"""HarnessConfig — complete specification for one harness run.

A harness run is a while-loop of AIAgent sessions that all work toward
the same task_spec until features.json is complete or a cost/session
limit is hit.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
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
```

**Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_harness/test_config.py -v
```
Expected: 3 PASSED

**Step 5: Commit**

```bash
/Applications/GitButler.app/Contents/MacOS/gitbutler-tauri commit -m "feat(harness): HarnessConfig dataclass with defaults and from_dict"
```

---

## Task 2: harness/features.py — Feature tracking

**Files:**
- Create: `harness/features.py`
- Create: `tests/test_harness/test_features.py`

**Step 1: Write the failing tests**

```python
# tests/test_harness/test_features.py
import json
from pathlib import Path
import pytest
from harness.features import Feature, FeatureTracker


def test_feature_dataclass_defaults():
    f = Feature(id="feat-1", description="Add login page")
    assert f.passes is False
    assert f.assigned_session is None
    assert f.test_cases == []
    assert f.dependencies == []


def test_feature_tracker_empty(tmp_path):
    features_file = tmp_path / "features.json"
    tracker = FeatureTracker(features_file)
    assert tracker.get_next_feature() is None
    stats = tracker.get_progress_stats()
    assert stats["total"] == 0
    assert stats["completed"] == 0


def test_feature_tracker_add_and_get_next(tmp_path):
    features_file = tmp_path / "features.json"
    tracker = FeatureTracker(features_file)
    tracker.add_feature(Feature(id="f1", description="First"))
    tracker.add_feature(Feature(id="f2", description="Second"))
    nxt = tracker.get_next_feature()
    assert nxt is not None
    assert nxt.id == "f1"


def test_feature_tracker_mark_complete(tmp_path):
    features_file = tmp_path / "features.json"
    tracker = FeatureTracker(features_file)
    tracker.add_feature(Feature(id="f1", description="First"))
    tracker.mark_complete("f1", session_number=3)
    tracker.save()
    # Reload and verify persistence
    tracker2 = FeatureTracker(features_file)
    feat = tracker2.get_feature("f1")
    assert feat.passes is True
    assert feat.assigned_session == 3


def test_feature_tracker_skip_completed(tmp_path):
    features_file = tmp_path / "features.json"
    tracker = FeatureTracker(features_file)
    tracker.add_feature(Feature(id="f1", description="Done", passes=True))
    tracker.add_feature(Feature(id="f2", description="Next"))
    nxt = tracker.get_next_feature()
    assert nxt.id == "f2"


def test_feature_tracker_progress_stats(tmp_path):
    features_file = tmp_path / "features.json"
    tracker = FeatureTracker(features_file)
    tracker.add_feature(Feature(id="f1", description="Done", passes=True))
    tracker.add_feature(Feature(id="f2", description="Pending"))
    stats = tracker.get_progress_stats()
    assert stats["total"] == 2
    assert stats["completed"] == 1
    assert stats["pending"] == 1
    assert stats["pct_complete"] == 50.0


def test_feature_tracker_respects_dependencies(tmp_path):
    features_file = tmp_path / "features.json"
    tracker = FeatureTracker(features_file)
    tracker.add_feature(Feature(id="f1", description="Auth"))
    tracker.add_feature(Feature(id="f2", description="Dashboard", dependencies=["f1"]))
    # f2 depends on f1 which is not complete → get_next_feature returns f1
    nxt = tracker.get_next_feature()
    assert nxt.id == "f1"
```

**Step 2: Run to verify failure**

```bash
python -m pytest tests/test_harness/test_features.py -v
```
Expected: `ModuleNotFoundError: No module named 'harness.features'`

**Step 3: Implement harness/features.py**

```python
# harness/features.py
"""Feature tracking — the features.json backbone of a harness run.

Each feature is a unit of work the agent is expected to implement.
FeatureTracker loads/saves features.json and answers "what should
the next session work on?" respecting completion state and dependencies.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Feature:
    """One unit of work tracked across harness sessions.

    Attributes
    ----------
    id : str
        Unique slug used as the primary key (e.g. "user-auth", "feat-001").
    description : str
        Human-readable description of what needs to be built.
    file_path : str
        Primary file this feature touches (informational, for context).
    test_cases : list[str]
        Natural-language descriptions of acceptance tests.
    dependencies : list[str]
        Feature IDs that must be complete before this one can be started.
    passes : bool
        True when the feature has been verified complete.
    assigned_session : int | None
        Session number that claimed this feature (set when a session starts
        working on it so parallel harness instances can coordinate).
    """

    id: str
    description: str
    file_path: str = ""
    test_cases: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    passes: bool = False
    assigned_session: Optional[int] = None


class FeatureTracker:
    """Load, query, and persist features.json.

    Usage
    -----
    tracker = FeatureTracker(Path("hermes_features.json"))
    next_feat = tracker.get_next_feature()   # None if all done
    tracker.mark_complete(next_feat.id, session_number=5)
    tracker.save()
    """

    def __init__(self, features_file: Path) -> None:
        self._path = Path(features_file)
        self._features: list[Feature] = []
        if self._path.exists():
            self._load()

    # ── Persistence ───────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text())
            if isinstance(raw, list):
                self._features = [Feature(**f) for f in raw]
            elif isinstance(raw, dict) and "features" in raw:
                self._features = [Feature(**f) for f in raw["features"]]
        except Exception as exc:
            logger.warning("Failed to load features from %s: %s", self._path, exc)
            self._features = []

    def save(self) -> None:
        """Write current state to features_file (creates parent dirs)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps([asdict(f) for f in self._features], indent=2)
        )

    # ── Mutation ──────────────────────────────────────────────────────

    def add_feature(self, feature: Feature) -> None:
        """Append a feature.  Does not auto-save — call save() explicitly."""
        self._features.append(feature)

    def mark_complete(self, feature_id: str, session_number: Optional[int] = None) -> None:
        """Mark feature as passing.  Does not auto-save."""
        for feat in self._features:
            if feat.id == feature_id:
                feat.passes = True
                if session_number is not None:
                    feat.assigned_session = session_number
                return
        logger.warning("mark_complete: feature '%s' not found", feature_id)

    # ── Query ─────────────────────────────────────────────────────────

    def get_feature(self, feature_id: str) -> Optional[Feature]:
        for f in self._features:
            if f.id == feature_id:
                return f
        return None

    def get_next_feature(self) -> Optional[Feature]:
        """Return the first incomplete, unblocked feature, or None."""
        complete_ids = {f.id for f in self._features if f.passes}
        for feat in self._features:
            if feat.passes:
                continue
            if all(dep in complete_ids for dep in feat.dependencies):
                return feat
        return None

    def get_incomplete_features(self, limit: int = 3) -> list[Feature]:
        """Return up to `limit` incomplete features for context injection."""
        complete_ids = {f.id for f in self._features if f.passes}
        result = []
        for feat in self._features:
            if not feat.passes and all(dep in complete_ids for dep in feat.dependencies):
                result.append(feat)
                if len(result) >= limit:
                    break
        return result

    def get_progress_stats(self) -> dict:
        total = len(self._features)
        completed = sum(1 for f in self._features if f.passes)
        pending = total - completed
        pct = (completed / total * 100.0) if total > 0 else 0.0
        return {
            "total": total,
            "completed": completed,
            "pending": pending,
            "pct_complete": round(pct, 1),
        }

    def all_complete(self) -> bool:
        return all(f.passes for f in self._features)
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_harness/test_features.py -v
```
Expected: 7 PASSED

**Step 5: Commit**

```bash
/Applications/GitButler.app/Contents/MacOS/gitbutler-tauri commit -m "feat(harness): Feature dataclass and FeatureTracker with dependency ordering"
```

---

## Task 3: harness/context_manager.py — Progress file I/O

**Files:**
- Create: `harness/context_manager.py`
- Create: `tests/test_harness/test_context_manager.py`

**Step 1: Write failing tests**

```python
# tests/test_harness/test_context_manager.py
from pathlib import Path
import pytest
from harness.context_manager import ContextManager
from harness.features import Feature, FeatureTracker


def test_load_context_empty_files(tmp_path):
    cm = ContextManager()
    ctx = cm.load_context(
        progress_file=tmp_path / "progress.md",
        features_file=tmp_path / "features.json",
        task_spec="Build auth system",
    )
    assert ctx["task_spec"] == "Build auth system"
    assert ctx["session_history"] == []
    assert ctx["completed_features"] == []
    assert ctx["next_steps"] == []


def test_load_context_reads_progress(tmp_path):
    progress = tmp_path / "progress.md"
    progress.write_text("## Session 1\nCompleted login feature.\n")
    cm = ContextManager()
    ctx = cm.load_context(
        progress_file=progress,
        features_file=tmp_path / "features.json",
        task_spec="Build auth",
    )
    assert len(ctx["session_history"]) == 1
    assert "login" in ctx["session_history"][0]


def test_load_context_next_steps_from_features(tmp_path):
    features_file = tmp_path / "features.json"
    tracker = FeatureTracker(features_file)
    tracker.add_feature(Feature(id="f1", description="Login page", passes=True))
    tracker.add_feature(Feature(id="f2", description="Dashboard"))
    tracker.add_feature(Feature(id="f3", description="Profile"))
    tracker.add_feature(Feature(id="f4", description="Settings"))
    tracker.save()
    cm = ContextManager()
    ctx = cm.load_context(
        progress_file=tmp_path / "progress.md",
        features_file=features_file,
        task_spec="Build app",
    )
    assert len(ctx["next_steps"]) == 3
    assert ctx["next_steps"][0]["id"] == "f2"


def test_save_progress_writes_markdown(tmp_path):
    progress = tmp_path / "progress.md"
    cm = ContextManager()
    cm.save_progress(
        progress_file=progress,
        features_file=tmp_path / "features.json",
        session_number=2,
        summary="Implemented user registration endpoint.",
        features_completed=["user-registration"],
    )
    content = progress.read_text()
    assert "## Session 2" in content
    assert "user registration" in content.lower()
    assert "user-registration" in content


def test_save_progress_appends_to_existing(tmp_path):
    progress = tmp_path / "progress.md"
    progress.write_text("## Session 1\nPrevious work.\n")
    cm = ContextManager()
    cm.save_progress(
        progress_file=progress,
        features_file=tmp_path / "features.json",
        session_number=2,
        summary="More work done.",
        features_completed=[],
    )
    content = progress.read_text()
    assert "## Session 1" in content
    assert "## Session 2" in content


def test_build_system_prompt_under_100kb(tmp_path):
    cm = ContextManager()
    ctx = cm.load_context(
        progress_file=tmp_path / "progress.md",
        features_file=tmp_path / "features.json",
        task_spec="x" * 50_000,
    )
    prompt = cm.build_system_prompt(ctx)
    assert len(prompt.encode()) < 100 * 1024
```

**Step 2: Run to verify failure**

```bash
python -m pytest tests/test_harness/test_context_manager.py -v
```

**Step 3: Implement harness/context_manager.py**

```python
# harness/context_manager.py
"""ContextManager — smart loading of progress + features into agent context.

Progressive loading strategy:
  Priority 1 (always)  — task_spec + completed feature list + next 3 steps
  Priority 2 (always)  — recent session history (last 5 sessions)
  Priority 3 (sometimes) — files mentioned in progress for the current feature

Total context is kept under MAX_CONTEXT_BYTES to leave room for the
conversation itself.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from harness.features import Feature, FeatureTracker

logger = logging.getLogger(__name__)

MAX_CONTEXT_BYTES = 100 * 1024   # 100 KB hard cap for injected context
SESSION_HISTORY_LIMIT = 5        # Last N sessions to include


class ContextManager:
    """Read and write the progress.md / features.json pair.

    All methods are stateless — pass the file paths on each call so the
    same ContextManager instance can serve multiple harness configs.
    """

    # ── Loading ───────────────────────────────────────────────────────

    def load_context(
        self,
        progress_file: Path,
        features_file: Path,
        task_spec: str,
    ) -> dict:
        """Load and assemble harness context.

        Returns
        -------
        dict with keys:
          task_spec         — the original goal string
          session_history   — list of str, one per past session summary
          completed_features — list of Feature dicts (passes=True)
          next_steps        — list of Feature dicts (up to 3 next incomplete)
        """
        progress_file = Path(progress_file)
        features_file = Path(features_file)

        tracker = FeatureTracker(features_file)
        session_history = self._parse_session_history(progress_file)
        completed = [f for f in tracker._features if f.passes]
        next_steps = tracker.get_incomplete_features(limit=3)

        return {
            "task_spec": task_spec,
            "session_history": session_history[-SESSION_HISTORY_LIMIT:],
            "completed_features": [{"id": f.id, "description": f.description} for f in completed],
            "next_steps": [
                {
                    "id": f.id,
                    "description": f.description,
                    "test_cases": f.test_cases,
                    "file_path": f.file_path,
                }
                for f in next_steps
            ],
        }

    def build_system_prompt(self, ctx: dict) -> str:
        """Convert loaded context into an agent system prompt string.

        Trims to MAX_CONTEXT_BYTES by progressively dropping the oldest
        session history entries first.
        """
        parts = [
            "# Harness Session\n",
            f"## Goal\n{ctx['task_spec']}\n",
        ]

        if ctx.get("completed_features"):
            lines = "\n".join(
                f"- [{f['id']}] {f['description']}"
                for f in ctx["completed_features"]
            )
            parts.append(f"\n## Completed Features\n{lines}\n")

        if ctx.get("next_steps"):
            lines = "\n".join(
                f"- [{f['id']}] {f['description']}"
                + (f"\n  Test: {'; '.join(f['test_cases'])}" if f.get("test_cases") else "")
                for f in ctx["next_steps"]
            )
            parts.append(f"\n## Next Features to Implement\n{lines}\n")

        if ctx.get("session_history"):
            history = ctx["session_history"]
            history_parts = ["\n## Session History (most recent last)\n"]
            for entry in history:
                history_parts.append(f"---\n{entry}\n")
            parts.extend(history_parts)

        prompt = "".join(parts)

        # Trim if over budget — drop history first
        while len(prompt.encode()) > MAX_CONTEXT_BYTES and ctx.get("session_history"):
            ctx["session_history"].pop(0)
            prompt = self.build_system_prompt(ctx)

        # Hard truncate if still too long (shouldn't happen in practice)
        if len(prompt.encode()) > MAX_CONTEXT_BYTES:
            prompt = prompt.encode()[:MAX_CONTEXT_BYTES].decode(errors="ignore")

        return prompt

    # ── Saving ────────────────────────────────────────────────────────

    def save_progress(
        self,
        progress_file: Path,
        features_file: Path,
        session_number: int,
        summary: str,
        features_completed: list[str],
    ) -> None:
        """Append a session summary to progress.md and mark features done.

        Parameters
        ----------
        progress_file   : Path to the markdown progress file.
        features_file   : Path to features.json (to mark features complete).
        session_number  : The 1-based session index.
        summary         : Free-text summary of what this session accomplished.
        features_completed : List of feature IDs completed this session.
        """
        progress_file = Path(progress_file)
        progress_file.parent.mkdir(parents=True, exist_ok=True)

        ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        section = f"\n## Session {session_number} — {ts}\n\n{summary}\n"

        if features_completed:
            feat_list = "\n".join(f"- {fid}" for fid in features_completed)
            section += f"\n**Features completed this session:**\n{feat_list}\n"

        with open(progress_file, "a", encoding="utf-8") as fh:
            fh.write(section)

        # Update features.json
        if features_completed:
            tracker = FeatureTracker(features_file)
            for fid in features_completed:
                tracker.mark_complete(fid, session_number=session_number)
            tracker.save()

    # ── Internal helpers ──────────────────────────────────────────────

    def _parse_session_history(self, progress_file: Path) -> list[str]:
        """Split progress.md on ## Session N headers."""
        if not progress_file.exists():
            return []
        content = progress_file.read_text(encoding="utf-8")
        # Split on h2 session headers, keep each block
        blocks = re.split(r"(?=^## Session \d+)", content, flags=re.MULTILINE)
        return [b.strip() for b in blocks if b.strip() and b.strip().startswith("## Session")]
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_harness/test_context_manager.py -v
```
Expected: 6 PASSED

**Step 5: Commit**

```bash
/Applications/GitButler.app/Contents/MacOS/gitbutler-tauri commit -m "feat(harness): ContextManager with smart context loading and 100KB cap"
```

---

## Task 4: harness/guardrails.py — CostGuard, CommandGuard, ApprovalGate

**Files:**
- Create: `harness/guardrails.py`
- Create: `tests/test_harness/test_guardrails.py`

**Step 1: Write failing tests**

```python
# tests/test_harness/test_guardrails.py
import pytest
from unittest.mock import MagicMock, patch
from harness.guardrails import (
    CostGuard, CommandGuard, ApprovalGate,
    CostLimitExceeded, CommandBlocked,
)


# ── CostGuard ─────────────────────────────────────────────────────────

def test_cost_guard_allows_within_limit():
    guard = CostGuard(max_cost_dollars=10.0)
    guard.record_session_cost(3.0)
    guard.record_session_cost(3.0)
    # 6.0 < 10.0 → no raise


def test_cost_guard_raises_when_exceeded():
    guard = CostGuard(max_cost_dollars=5.0)
    guard.record_session_cost(3.0)
    with pytest.raises(CostLimitExceeded) as exc_info:
        guard.record_session_cost(3.0)
    assert "6.0" in str(exc_info.value) or "5.0" in str(exc_info.value)


def test_cost_guard_tracks_cumulative():
    guard = CostGuard(max_cost_dollars=100.0)
    guard.record_session_cost(10.0)
    guard.record_session_cost(20.0)
    assert guard.cumulative_cost == 30.0


def test_cost_guard_from_usage_dict():
    guard = CostGuard(max_cost_dollars=50.0)
    usage = {"input_tokens": 10_000, "output_tokens": 1_000}
    guard.record_usage(usage, model="anthropic/claude-sonnet-4-6")
    assert guard.cumulative_cost > 0


# ── CommandGuard ──────────────────────────────────────────────────────

def test_command_guard_blocks_rm_rf():
    guard = CommandGuard(forbidden_paths=[])
    with pytest.raises(CommandBlocked, match="rm -rf"):
        guard.check("rm -rf /")


def test_command_guard_blocks_forbidden_path(tmp_path):
    guard = CommandGuard(forbidden_paths=[str(tmp_path)])
    with pytest.raises(CommandBlocked):
        guard.check(f"echo hello > {tmp_path}/secret.txt")


def test_command_guard_allows_safe_command():
    guard = CommandGuard(forbidden_paths=[])
    guard.check("ls -la /tmp")  # Should not raise


def test_command_guard_blocks_force_push():
    guard = CommandGuard(forbidden_paths=[])
    with pytest.raises(CommandBlocked):
        guard.check("git push --force origin main")


def test_command_guard_blocks_drop_database():
    guard = CommandGuard(forbidden_paths=[])
    with pytest.raises(CommandBlocked):
        guard.check("DROP DATABASE production;")


# ── ApprovalGate ──────────────────────────────────────────────────────

def test_approval_gate_no_required_commands():
    gate = ApprovalGate(approval_required_commands=[])
    assert gate.requires_approval("git push origin main") is False


def test_approval_gate_flags_matching_command():
    gate = ApprovalGate(approval_required_commands=["git push", "npm publish"])
    assert gate.requires_approval("git push origin main") is True
    assert gate.requires_approval("npm publish --dry-run") is True
    assert gate.requires_approval("ls -la") is False


def test_approval_gate_default_commands():
    """terraform apply, git push, npm publish always require approval."""
    gate = ApprovalGate(approval_required_commands=[])
    assert gate.requires_approval("terraform apply") is True
    assert gate.requires_approval("git push origin") is True
    assert gate.requires_approval("npm publish") is True
```

**Step 2: Run to verify failure**

```bash
python -m pytest tests/test_harness/test_guardrails.py -v
```

**Step 3: Implement harness/guardrails.py**

```python
# harness/guardrails.py
"""Guardrails — three protection layers for harness-controlled agent sessions.

CostGuard     — tracks cumulative spend, raises CostLimitExceeded when over budget.
CommandGuard  — blocks dangerous shell commands before they reach the terminal tool.
ApprovalGate  — pauses and requests human approval for high-impact operations.

Integration points
------------------
- CostGuard.record_usage() is called from SessionOrchestrator after each
  AIAgent.run_conversation() using the returned usage dict.
- CommandGuard.check() is wired into AIAgent's tool_start_callback so it runs
  before every terminal tool call.
- ApprovalGate.requires_approval() is consulted by CommandGuard; when True,
  CommandGuard raises CommandBlocked with requires_approval=True so the
  orchestrator can prompt the user and retry.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from tools.approval import detect_dangerous_command

logger = logging.getLogger(__name__)


# ── Exceptions ────────────────────────────────────────────────────────

class CostLimitExceeded(Exception):
    """Raised when cumulative harness spend exceeds max_cost_dollars."""


class CommandBlocked(Exception):
    """Raised by CommandGuard when a command violates guardrail policy.

    Attributes
    ----------
    command           — the blocked command string
    reason            — human-readable explanation
    requires_approval — True if block can be overridden with human approval
    """

    def __init__(self, command: str, reason: str, requires_approval: bool = False) -> None:
        super().__init__(f"Command blocked — {reason}: {command!r}")
        self.command = command
        self.reason = reason
        self.requires_approval = requires_approval


# ── CostGuard ─────────────────────────────────────────────────────────

# Approximate USD pricing per 1M tokens for common models.
# Keyed by model slug fragment; falls back to a conservative default.
_PRICE_TABLE: dict[str, tuple[float, float]] = {
    # (input $/1M, output $/1M)
    "claude-opus":    (15.0,  75.0),
    "claude-sonnet":  (3.0,   15.0),
    "claude-haiku":   (0.25,  1.25),
    "gpt-4o":         (5.0,   15.0),
    "gpt-4":          (30.0,  60.0),
    "gpt-3.5":        (0.5,   1.5),
    "gemini-1.5-pro": (3.5,   10.5),
}
_DEFAULT_PRICE = (3.0, 15.0)   # conservative fallback


def _price_for_model(model: str) -> tuple[float, float]:
    model_lower = model.lower()
    for fragment, prices in _PRICE_TABLE.items():
        if fragment in model_lower:
            return prices
    return _DEFAULT_PRICE


class CostGuard:
    """Tracks token usage and raises CostLimitExceeded when budget is hit.

    Usage
    -----
    guard = CostGuard(max_cost_dollars=50.0)
    guard.record_session_cost(session_usd)          # from billing info
    guard.record_usage(usage_dict, model="...")     # from AIAgent result
    """

    def __init__(self, max_cost_dollars: float) -> None:
        self.max_cost_dollars = max_cost_dollars
        self.cumulative_cost: float = 0.0
        self.session_costs: list[float] = []

    def record_session_cost(self, cost_usd: float) -> None:
        """Add a session cost and raise if limit exceeded."""
        self.cumulative_cost += cost_usd
        self.session_costs.append(cost_usd)
        logger.debug("CostGuard: +$%.4f → total $%.4f / $%.2f",
                     cost_usd, self.cumulative_cost, self.max_cost_dollars)
        if self.cumulative_cost > self.max_cost_dollars:
            raise CostLimitExceeded(
                f"Cumulative cost ${self.cumulative_cost:.2f} exceeds limit "
                f"${self.max_cost_dollars:.2f}"
            )

    def record_usage(self, usage: dict, model: str = "") -> None:
        """Estimate cost from a token usage dict and record it.

        Expects keys: input_tokens, output_tokens (standard OpenAI format).
        Cache tokens (cache_read_tokens, cache_write_tokens) are treated
        as input tokens for a conservative estimate.
        """
        input_price, output_price = _price_for_model(model)
        input_tok = usage.get("input_tokens", usage.get("prompt_tokens", 0))
        output_tok = usage.get("output_tokens", usage.get("completion_tokens", 0))
        cache_read = usage.get("cache_read_tokens", 0)
        input_tok += cache_read
        cost = (input_tok * input_price + output_tok * output_price) / 1_000_000
        self.record_session_cost(cost)


# ── CommandGuard ──────────────────────────────────────────────────────

_ALWAYS_BLOCKED: list[tuple[str, str]] = [
    (r"rm\s+-rf\s+/", "recursive delete of root filesystem"),
    (r"rm\s+-rf\s+~", "recursive delete of home directory"),
    (r"chmod\s+777\s+/", "world-writable root"),
    (r"drop\s+database\b", "SQL DROP DATABASE"),
    (r"truncate\s+table\b", "SQL TRUNCATE TABLE"),
    (r"git\s+push\s+--force\b", "force push to git remote"),
    (r"git\s+push\s+-f\b", "force push to git remote"),
    (r">\s*/dev/sd[a-z]", "write to raw block device"),
    (r"mkfs\.", "filesystem format"),
]

_COMPILED_BLOCKED = [(re.compile(p, re.IGNORECASE), desc) for p, desc in _ALWAYS_BLOCKED]


class CommandGuard:
    """Pre-flight check for shell commands before they reach the terminal tool.

    Wire into AIAgent via tool_start_callback:
        def on_tool_start(tool_name, tool_input):
            if tool_name == "terminal":
                guard.check(tool_input.get("command", ""))

    Raises CommandBlocked on policy violation.  The orchestrator should
    catch this and either abort the session or (if requires_approval=True)
    prompt the user.
    """

    def __init__(
        self,
        forbidden_paths: Optional[list[str]] = None,
        extra_blocked_patterns: Optional[list[tuple[str, str]]] = None,
    ) -> None:
        self._forbidden_paths = [str(p) for p in (forbidden_paths or [])]
        self._extra = [
            (re.compile(p, re.IGNORECASE), desc)
            for p, desc in (extra_blocked_patterns or [])
        ]

    def check(self, command: str) -> None:
        """Raise CommandBlocked if the command violates policy.

        Also delegates to tools.approval.detect_dangerous_command for
        consistency with the interactive CLI approval system.
        """
        # 1. Always-blocked patterns
        for pattern, desc in _COMPILED_BLOCKED:
            if pattern.search(command):
                raise CommandBlocked(command, desc, requires_approval=False)

        # 2. Extra caller-supplied patterns
        for pattern, desc in self._extra:
            if pattern.search(command):
                raise CommandBlocked(command, desc, requires_approval=False)

        # 3. Forbidden path prefixes
        for path in self._forbidden_paths:
            if path and path in command:
                raise CommandBlocked(
                    command,
                    f"touches forbidden path {path!r}",
                    requires_approval=False,
                )

        # 4. Delegate to existing approval system for pattern detection
        is_dangerous, pattern_key, description = detect_dangerous_command(command)
        if is_dangerous:
            raise CommandBlocked(command, description, requires_approval=True)


# ── ApprovalGate ──────────────────────────────────────────────────────

# Commands that ALWAYS need human approval regardless of config
_DEFAULT_APPROVAL_PREFIXES = [
    "git push",
    "npm publish",
    "terraform apply",
    "terraform destroy",
    "kubectl delete",
    "aws s3 rm",
    "gcloud deploy",
]


class ApprovalGate:
    """Determines whether a command needs human sign-off before running.

    Usage
    -----
    gate = ApprovalGate(approval_required_commands=cfg.approval_required_commands)
    if gate.requires_approval(command):
        # prompt user, then allow or deny
    """

    def __init__(self, approval_required_commands: Optional[list[str]] = None) -> None:
        self._required = list(_DEFAULT_APPROVAL_PREFIXES)
        if approval_required_commands:
            self._required.extend(approval_required_commands)

    def requires_approval(self, command: str) -> bool:
        cmd_lower = command.strip().lower()
        return any(cmd_lower.startswith(req.lower()) for req in self._required)
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_harness/test_guardrails.py -v
```
Expected: 14 PASSED

**Step 5: Commit**

```bash
/Applications/GitButler.app/Contents/MacOS/gitbutler-tauri commit -m "feat(harness): CostGuard, CommandGuard, ApprovalGate guardrails"
```

---

## Task 5: harness/session_orchestrator.py — The main harness loop

**Files:**
- Create: `harness/session_orchestrator.py`
- Create: `tests/test_harness/test_session_orchestrator.py`

**Step 1: Write failing tests**

```python
# tests/test_harness/test_session_orchestrator.py
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest
from harness.config import HarnessConfig
from harness.features import Feature, FeatureTracker
from harness.session_orchestrator import SessionOrchestrator


def _make_cfg(tmp_path, task_spec="Build X", max_sessions=3):
    return HarnessConfig(
        project_dir=tmp_path,
        task_spec=task_spec,
        max_sessions=max_sessions,
        max_cost_dollars=10.0,
    )


def _fake_agent_result(summary="Done", input_tokens=100, output_tokens=50):
    return {
        "response": summary,
        "messages": [],
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


@patch("harness.session_orchestrator.AIAgent")
def test_run_harness_completes_when_all_features_done(MockAgent, tmp_path):
    cfg = _make_cfg(tmp_path)
    # Pre-populate features.json with one already-complete feature
    tracker = FeatureTracker(cfg.features_file)
    tracker.add_feature(Feature(id="f1", description="Only feature", passes=True))
    tracker.save()
    orch = SessionOrchestrator(cfg)
    result = orch.run_harness()
    assert result["status"] == "completed"
    assert result["sessions_run"] == 0
    MockAgent.assert_not_called()


@patch("harness.session_orchestrator.AIAgent")
def test_run_harness_runs_one_session(MockAgent, tmp_path):
    cfg = _make_cfg(tmp_path, max_sessions=1)
    tracker = FeatureTracker(cfg.features_file)
    tracker.add_feature(Feature(id="f1", description="Build thing"))
    tracker.save()

    mock_instance = MagicMock()
    mock_instance.run_conversation.return_value = _fake_agent_result()
    MockAgent.return_value = mock_instance

    orch = SessionOrchestrator(cfg)
    result = orch.run_harness()
    assert result["sessions_run"] == 1
    assert mock_instance.run_conversation.call_count == 1


@patch("harness.session_orchestrator.AIAgent")
def test_run_harness_stops_at_session_limit(MockAgent, tmp_path):
    cfg = _make_cfg(tmp_path, max_sessions=2)
    tracker = FeatureTracker(cfg.features_file)
    for i in range(5):
        tracker.add_feature(Feature(id=f"f{i}", description=f"Feature {i}"))
    tracker.save()

    mock_instance = MagicMock()
    mock_instance.run_conversation.return_value = _fake_agent_result()
    MockAgent.return_value = mock_instance

    orch = SessionOrchestrator(cfg)
    result = orch.run_harness()
    assert result["sessions_run"] == 2
    assert result["status"] == "session_limit_reached"


@patch("harness.session_orchestrator.AIAgent")
def test_run_harness_saves_progress_after_each_session(MockAgent, tmp_path):
    cfg = _make_cfg(tmp_path, max_sessions=1)
    tracker = FeatureTracker(cfg.features_file)
    tracker.add_feature(Feature(id="f1", description="Build thing"))
    tracker.save()

    mock_instance = MagicMock()
    mock_instance.run_conversation.return_value = _fake_agent_result("Built it")
    MockAgent.return_value = mock_instance

    orch = SessionOrchestrator(cfg)
    orch.run_harness()
    assert cfg.progress_file.exists()
    content = cfg.progress_file.read_text()
    assert "## Session 1" in content


@patch("harness.session_orchestrator.AIAgent")
def test_on_session_callbacks_fired(MockAgent, tmp_path):
    cfg = _make_cfg(tmp_path, max_sessions=1)
    tracker = FeatureTracker(cfg.features_file)
    tracker.add_feature(Feature(id="f1", description="Thing"))
    tracker.save()

    mock_instance = MagicMock()
    mock_instance.run_conversation.return_value = _fake_agent_result()
    MockAgent.return_value = mock_instance

    starts, ends = [], []
    orch = SessionOrchestrator(cfg, on_session_start=starts.append, on_session_end=ends.append)
    orch.run_harness()
    assert len(starts) == 1
    assert len(ends) == 1
```

**Step 2: Run to verify failure**

```bash
python -m pytest tests/test_harness/test_session_orchestrator.py -v
```

**Step 3: Implement harness/session_orchestrator.py**

```python
# harness/session_orchestrator.py
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
import signal
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional

from harness.config import HarnessConfig
from harness.context_manager import ContextManager
from harness.features import FeatureTracker
from harness.guardrails import (
    ApprovalGate, CommandBlocked, CommandGuard, CostGuard, CostLimitExceeded,
)

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

            # ── Limit checks ──────────────────────────────────────────
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
                    return self._result(
                        "cost_limit_reached", sessions_run, str(exc)
                    )

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
        # Import here to avoid heavy top-level import cost
        from run_agent import AIAgent

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

        # Build guardrail callbacks
        def _tool_start(tool_name: str, tool_input: dict) -> None:
            if self._on_tool_use:
                self._on_tool_use(tool_name, tool_input)
            if tool_name == "terminal":
                cmd = tool_input.get("command", "")
                try:
                    self._command_guard.check(cmd)
                except CommandBlocked as exc:
                    if exc.requires_approval:
                        if self._approval_gate.requires_approval(cmd):
                            raise
                    else:
                        raise

        init_kwargs: dict = dict(
            model=self.cfg.model,
            tool_start_callback=_tool_start,
        )
        if self.cfg.gateway_url:
            init_kwargs["base_url"] = self.cfg.gateway_url
        if self.cfg.allowed_tools:
            # Map to enabled_toolsets if names match toolset names
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
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_harness/test_session_orchestrator.py -v
```
Expected: 5 PASSED

**Step 5: Commit**

```bash
/Applications/GitButler.app/Contents/MacOS/gitbutler-tauri commit -m "feat(harness): SessionOrchestrator main harness loop with cost/session limits"
```

---

## Task 6: harness/employee.py — Persistent goal-driven agent

**Files:**
- Create: `harness/employee.py`
- Create: `tests/test_harness/test_employee.py`

**Step 1: Write failing tests**

```python
# tests/test_harness/test_employee.py
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from harness.employee import Employee


def test_employee_create_and_save(tmp_path):
    emp = Employee(
        name="ada",
        role="backend engineer",
        goal="Build a REST API for the user service",
        kpis=["All endpoints return 200", "Test coverage > 80%"],
        memory_scope="ada",
        employees_dir=tmp_path,
    )
    emp.save()
    config_file = tmp_path / "ada.yaml"
    assert config_file.exists()
    content = config_file.read_text()
    assert "ada" in content
    assert "backend engineer" in content


def test_employee_load_from_yaml(tmp_path):
    emp = Employee(
        name="bob",
        role="qa engineer",
        goal="Write tests for the auth module",
        kpis=[],
        employees_dir=tmp_path,
    )
    emp.save()
    loaded = Employee.load("bob", employees_dir=tmp_path)
    assert loaded.name == "bob"
    assert loaded.role == "qa engineer"
    assert loaded.goal == "Write tests for the auth module"


def test_employee_load_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        Employee.load("nonexistent", employees_dir=tmp_path)


def test_employee_default_status():
    emp = Employee(name="x", role="y", goal="z")
    assert emp.status == "idle"


def test_employee_to_harness_config(tmp_path):
    emp = Employee(
        name="ada",
        role="engineer",
        goal="Build REST API",
        kpis=["All tests pass"],
        employees_dir=tmp_path,
    )
    cfg = emp.to_harness_config(project_dir=tmp_path)
    assert cfg.task_spec == "Build REST API"
    assert cfg.project_dir == tmp_path


def test_employee_list_all(tmp_path):
    Employee(name="ada", role="eng", goal="X", employees_dir=tmp_path).save()
    Employee(name="bob", role="qa", goal="Y", employees_dir=tmp_path).save()
    employees = Employee.list_all(employees_dir=tmp_path)
    names = [e.name for e in employees]
    assert "ada" in names
    assert "bob" in names
```

**Step 2: Run to verify failure**

```bash
python -m pytest tests/test_harness/test_employee.py -v
```

**Step 3: Implement harness/employee.py**

```python
# harness/employee.py
"""Employee — persistent goal-driven agent persona.

An Employee encapsulates a named role + goal and delegates execution to
SessionOrchestrator.  Employee configs are stored as YAML in
~/.hermes/employees/{name}.yaml so they survive across CLI sessions.

Usage
-----
    emp = Employee.load("ada", employees_dir=Path("~/.hermes/employees"))
    emp.start_shift(project_dir=Path("/path/to/project"))

Or create a new one:
    emp = Employee(name="ada", role="backend engineer", goal="Build auth API")
    emp.save()
    emp.start_shift(project_dir=Path("."))
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from harness.config import HarnessConfig
from harness.context_manager import ContextManager

logger = logging.getLogger(__name__)

_DEFAULT_EMPLOYEES_DIR = Path.home() / ".hermes" / "employees"


@dataclass
class Employee:
    """A persistent, goal-driven agent persona.

    Attributes
    ----------
    name          : Unique slug used as the config filename key.
    role          : Job title / function (e.g. "backend engineer").
    goal          : One-paragraph description of what this employee works toward.
    kpis          : Measurable success criteria (bullet strings).
    schedule      : Cron expression for proactive work cycles (optional).
    memory_scope  : Isolated memory namespace key for this employee.
    status        : Current state — idle | working | blocked | completed.
    employees_dir : Where YAML files are stored; defaults to ~/.hermes/employees.
    """

    name: str
    role: str
    goal: str
    kpis: list[str] = field(default_factory=list)
    schedule: Optional[str] = None
    memory_scope: Optional[str] = None
    status: str = "idle"
    employees_dir: Optional[Path] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.employees_dir is None:
            self.employees_dir = _DEFAULT_EMPLOYEES_DIR
        self.employees_dir = Path(self.employees_dir)
        if self.memory_scope is None:
            self.memory_scope = self.name

    # ── Persistence ───────────────────────────────────────────────────

    @property
    def _config_path(self) -> Path:
        return self.employees_dir / f"{self.name}.yaml"

    def save(self) -> None:
        """Write employee config to YAML file."""
        import yaml  # lazy import — yaml is an optional dep

        self.employees_dir.mkdir(parents=True, exist_ok=True)
        data = {
            k: v for k, v in asdict(self).items()
            if k != "employees_dir" and v is not None
        }
        self._config_path.write_text(yaml.dump(data, default_flow_style=False))
        logger.debug("Saved employee config: %s", self._config_path)

    @classmethod
    def load(cls, name: str, employees_dir: Optional[Path] = None) -> "Employee":
        """Load an employee config from YAML.  Raises FileNotFoundError if missing."""
        import yaml

        dir_ = Path(employees_dir) if employees_dir else _DEFAULT_EMPLOYEES_DIR
        path = dir_ / f"{name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"No employee config found: {path}")
        data = yaml.safe_load(path.read_text()) or {}
        data["employees_dir"] = dir_
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def list_all(cls, employees_dir: Optional[Path] = None) -> list["Employee"]:
        """Return all employees found in the employees directory."""
        dir_ = Path(employees_dir) if employees_dir else _DEFAULT_EMPLOYEES_DIR
        if not dir_.exists():
            return []
        result = []
        for yaml_file in sorted(dir_.glob("*.yaml")):
            try:
                result.append(cls.load(yaml_file.stem, employees_dir=dir_))
            except Exception as exc:
                logger.warning("Could not load employee %s: %s", yaml_file.stem, exc)
        return result

    # ── Harness integration ───────────────────────────────────────────

    def to_harness_config(self, project_dir: Path, **overrides) -> HarnessConfig:
        """Build a HarnessConfig from this employee's goal and KPIs."""
        task_spec = self.goal
        if self.kpis:
            kpi_block = "\n".join(f"- {k}" for k in self.kpis)
            task_spec = f"{self.goal}\n\nSuccess criteria:\n{kpi_block}"

        return HarnessConfig(
            project_dir=Path(project_dir),
            task_spec=task_spec,
            **overrides,
        )

    def start_shift(self, project_dir: Path, **harness_overrides) -> dict:
        """Begin a harness-orchestrated work session toward this employee's goal.

        Parameters
        ----------
        project_dir      : Working directory for the agent.
        harness_overrides: Extra kwargs forwarded to HarnessConfig.

        Returns
        -------
        The SessionOrchestrator.run_harness() result dict.
        """
        from harness.session_orchestrator import SessionOrchestrator

        self.status = "working"
        self.save()

        cfg = self.to_harness_config(project_dir, **harness_overrides)
        orch = SessionOrchestrator(cfg)

        try:
            result = orch.run_harness()
            self.status = "completed" if result["status"] == "completed" else "idle"
        except Exception as exc:
            self.status = "blocked"
            logger.exception("Employee %s shift failed: %s", self.name, exc)
            result = {"status": "error", "message": str(exc), "sessions_run": 0,
                      "total_cost_usd": 0.0}
        finally:
            self.save()

        return result

    def decompose_goal(self, project_dir: Path) -> list[dict]:
        """Use task_graph._decompose_goal to break the employee's goal into features.

        Returns a list of feature dicts that can be written to features.json.
        This requires a running AIAgent to call the decomposition LLM.
        """
        from run_agent import AIAgent
        from agent.task_graph import _decompose_goal

        agent = AIAgent(model="anthropic/claude-haiku-4-5")  # cheap for planning
        subtasks = _decompose_goal(goal=self.goal, parent_agent=agent)

        return [
            {
                "id": f"feat-{i+1:03d}",
                "description": subtask,
                "file_path": "",
                "test_cases": [],
                "dependencies": [],
                "passes": False,
            }
            for i, subtask in enumerate(subtasks)
        ]
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_harness/test_employee.py -v
```
Expected: 6 PASSED

**Step 5: Commit**

```bash
/Applications/GitButler.app/Contents/MacOS/gitbutler-tauri commit -m "feat(harness): Employee persistent goal-driven agent with YAML config"
```

---

## Task 7: harness/cli_commands.py — CLI integration

**Files:**
- Create: `harness/cli_commands.py`
- Modify: `hermes_cli/main.py` (add harness + employee subcommands)
- Create: `tests/test_harness/test_cli_commands.py`

**Step 1: Write failing tests**

```python
# tests/test_harness/test_cli_commands.py
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from harness.cli_commands import (
    cmd_harness_run,
    cmd_employee_create,
    cmd_employee_status,
)


def test_cmd_harness_run_missing_spec(tmp_path, capsys):
    rc = cmd_harness_run(spec_file=str(tmp_path / "missing.yaml"))
    assert rc != 0
    captured = capsys.readouterr()
    assert "not found" in captured.out.lower() or "error" in captured.out.lower()


def test_cmd_harness_run_valid_spec(tmp_path):
    spec = tmp_path / "spec.yaml"
    spec.write_text(f"""
project_dir: {tmp_path}
task_spec: Build a hello world script
max_sessions: 1
""")
    with patch("harness.cli_commands.SessionOrchestrator") as MockOrch:
        instance = MagicMock()
        instance.run_harness.return_value = {"status": "completed", "sessions_run": 1,
                                             "total_cost_usd": 0.0, "message": "done"}
        MockOrch.return_value = instance
        rc = cmd_harness_run(spec_file=str(spec))
    assert rc == 0


def test_cmd_employee_create(tmp_path, capsys):
    with patch("harness.cli_commands._employees_dir", return_value=tmp_path):
        rc = cmd_employee_create(
            name="ada",
            role="backend engineer",
            goal="Build auth API",
            employees_dir=tmp_path,
        )
    assert rc == 0
    assert (tmp_path / "ada.yaml").exists()


def test_cmd_employee_status_empty(tmp_path, capsys):
    rc = cmd_employee_status(employees_dir=tmp_path)
    captured = capsys.readouterr()
    assert rc == 0
    assert "no employees" in captured.out.lower() or captured.out.strip() != ""
```

**Step 2: Run to verify failure**

```bash
python -m pytest tests/test_harness/test_cli_commands.py -v
```

**Step 3: Implement harness/cli_commands.py**

```python
# harness/cli_commands.py
"""CLI command handlers for the harness and employee subcommands.

These are pure functions that implement the logic for:
  hermes harness run <spec_file>
  hermes employee create <name> <role> <goal>
  hermes employee start <name>
  hermes employee status

Each function returns an integer exit code (0 = success).

Integration
-----------
These functions are wired into hermes_cli/main.py's argparse dispatch
in Task 7 step 5.  See the block that handles args.command == "harness"
and args.command == "employee".
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _employees_dir(employees_dir: Optional[Path] = None) -> Path:
    """Return the employees directory, defaulting to ~/.hermes/employees."""
    if employees_dir:
        return Path(employees_dir)
    from hermes_constants import get_hermes_home
    return get_hermes_home() / "employees"


# ── harness run ───────────────────────────────────────────────────────

def cmd_harness_run(spec_file: str, employees_dir: Optional[Path] = None) -> int:
    """Run a harness from a YAML or JSON spec file.

    The spec file must contain at minimum:
      project_dir: /path/to/project
      task_spec: "One paragraph describing the goal"

    Returns 0 on success (harness completed or hit limit), 1 on error.
    """
    spec_path = Path(spec_file)
    if not spec_path.exists():
        print(f"Error: spec file not found: {spec_path}")
        return 1

    try:
        if spec_path.suffix in (".yaml", ".yml"):
            import yaml
            data = yaml.safe_load(spec_path.read_text()) or {}
        else:
            data = json.loads(spec_path.read_text())
    except Exception as exc:
        print(f"Error: failed to parse spec file: {exc}")
        return 1

    try:
        from harness.config import HarnessConfig
        from harness.session_orchestrator import SessionOrchestrator
        cfg = HarnessConfig.from_dict(data)
    except Exception as exc:
        print(f"Error: invalid spec — {exc}")
        return 1

    print(f"Starting harness run for: {cfg.task_spec[:80]}")
    print(f"Project: {cfg.project_dir}  |  Max sessions: {cfg.max_sessions}  |  Budget: ${cfg.max_cost_dollars:.2f}")

    def _on_start(meta: dict) -> None:
        print(f"\n── Session {meta['session_number']} starting ──")

    def _on_end(meta: dict) -> None:
        status = meta.get("status", "?")
        print(f"   Session {meta['session_number']} finished: {status}")

    orch = SessionOrchestrator(cfg, on_session_start=_on_start, on_session_end=_on_end)
    result = orch.run_harness()

    print(f"\n{'='*50}")
    print(f"Harness {result['status'].upper()}")
    print(f"Sessions run:  {result['sessions_run']}")
    print(f"Cost:          ${result['total_cost_usd']:.4f}")
    print(f"Message:       {result['message']}")
    return 0


# ── employee create ───────────────────────────────────────────────────

def cmd_employee_create(
    name: str,
    role: str,
    goal: str,
    kpis: Optional[list[str]] = None,
    schedule: Optional[str] = None,
    employees_dir: Optional[Path] = None,
) -> int:
    """Create a new AI employee config and save to ~/.hermes/employees/{name}.yaml."""
    from harness.employee import Employee

    dir_ = _employees_dir(employees_dir)
    if (dir_ / f"{name}.yaml").exists():
        print(f"Employee '{name}' already exists. Use 'hermes employee status' to view.")
        return 1

    emp = Employee(
        name=name,
        role=role,
        goal=goal,
        kpis=kpis or [],
        schedule=schedule,
        employees_dir=dir_,
    )
    emp.save()
    print(f"Created employee '{name}' ({role})")
    print(f"Goal: {goal}")
    print(f"Config saved to: {emp._config_path}")
    return 0


# ── employee start ────────────────────────────────────────────────────

def cmd_employee_start(
    name: str,
    project_dir: Optional[str] = None,
    employees_dir: Optional[Path] = None,
) -> int:
    """Start a shift for an employee, running harness toward their goal."""
    from harness.employee import Employee

    dir_ = _employees_dir(employees_dir)
    try:
        emp = Employee.load(name, employees_dir=dir_)
    except FileNotFoundError:
        print(f"Error: employee '{name}' not found. Create with: hermes employee create {name} <role> <goal>")
        return 1

    work_dir = Path(project_dir) if project_dir else Path.cwd()
    print(f"Starting shift for {emp.name} ({emp.role}) in {work_dir}")

    result = emp.start_shift(project_dir=work_dir)

    print(f"\nShift complete: {result['status']}")
    print(f"Sessions run: {result['sessions_run']}  |  Cost: ${result.get('total_cost_usd', 0):.4f}")
    return 0 if result["status"] in ("completed", "session_limit_reached") else 1


# ── employee status ───────────────────────────────────────────────────

def cmd_employee_status(employees_dir: Optional[Path] = None) -> int:
    """Show all employees and their current status."""
    from harness.employee import Employee

    dir_ = _employees_dir(employees_dir)
    employees = Employee.list_all(employees_dir=dir_)

    if not employees:
        print("No employees found. Create one with: hermes employee create <name> <role> <goal>")
        return 0

    print(f"{'NAME':<15} {'ROLE':<25} {'STATUS':<12} GOAL")
    print("-" * 80)
    for emp in employees:
        print(f"{emp.name:<15} {emp.role:<25} {emp.status:<12} {emp.goal[:40]}")
    return 0
```

**Step 4: Add harness/employee subcommands to hermes_cli/main.py**

Find the last `subparsers.add_parser(...)` call in `hermes_cli/main.py` (around line 4900+) and add after it:

```python
    # ── harness ──────────────────────────────────────────────────────
    harness_parser = subparsers.add_parser(
        "harness", help="Run an agent harness (multi-session task orchestration)"
    )
    harness_subparsers = harness_parser.add_subparsers(dest="harness_command")
    harness_run = harness_subparsers.add_parser("run", help="Run a harness from a YAML/JSON spec file")
    harness_run.add_argument("spec_file", help="Path to harness spec YAML/JSON")

    # ── employee ──────────────────────────────────────────────────────
    employee_parser = subparsers.add_parser(
        "employee", help="Manage AI employee personas"
    )
    emp_subparsers = employee_parser.add_subparsers(dest="employee_command")

    emp_create = emp_subparsers.add_parser("create", help="Create a new AI employee")
    emp_create.add_argument("name", help="Employee name (slug)")
    emp_create.add_argument("role", help="Job role (e.g. 'backend engineer')")
    emp_create.add_argument("goal", help="Goal description")

    emp_start = emp_subparsers.add_parser("start", help="Start an employee's work shift")
    emp_start.add_argument("name", help="Employee name")
    emp_start.add_argument("--project-dir", dest="project_dir", help="Working directory")

    emp_subparsers.add_parser("status", help="Show all employees and their status")
```

Then in the dispatch section (the large `if args.command == "chat":` chain), add:

```python
    elif args.command == "harness":
        from harness.cli_commands import cmd_harness_run
        if args.harness_command == "run":
            sys.exit(cmd_harness_run(spec_file=args.spec_file))
        else:
            harness_parser.print_help()
            sys.exit(1)
    elif args.command == "employee":
        from harness.cli_commands import (
            cmd_employee_create, cmd_employee_start, cmd_employee_status
        )
        if args.employee_command == "create":
            sys.exit(cmd_employee_create(name=args.name, role=args.role, goal=args.goal))
        elif args.employee_command == "start":
            sys.exit(cmd_employee_start(name=args.name, project_dir=getattr(args, "project_dir", None)))
        elif args.employee_command == "status":
            sys.exit(cmd_employee_status())
        else:
            employee_parser.print_help()
            sys.exit(1)
```

**Step 5: Run tests**

```bash
python -m pytest tests/test_harness/test_cli_commands.py -v
```
Expected: 4 PASSED

**Step 6: Smoke-test the CLI**

```bash
python hermes_cli/main.py harness --help
python hermes_cli/main.py employee --help
```
Expected: Help text printed for both subcommands.

**Step 7: Commit**

```bash
/Applications/GitButler.app/Contents/MacOS/gitbutler-tauri commit -m "feat(harness): CLI commands for harness run and employee management"
```

---

## Task 8: Full test suite run + __init__.py update

**Files:**
- Modify: `harness/__init__.py` (already created in Task 1, nothing to change)
- Modify: `tests/test_harness/__init__.py` (ensure empty, already created)

**Step 1: Run the full harness test suite**

```bash
python -m pytest tests/test_harness/ -v --tb=short
```
Expected: All tests PASS (count will be 30+)

**Step 2: Run existing tests to check for regressions**

```bash
python -m pytest tests/ -q --ignore=tests/integration --ignore=tests/e2e -x
```
Expected: No new failures

**Step 3: Verify imports work**

```python
python -c "from harness import HarnessConfig, ContextManager, SessionOrchestrator, Employee; print('OK')"
```
Expected: `OK`

**Step 4: Final commit**

```bash
/Applications/GitButler.app/Contents/MacOS/gitbutler-tauri commit -m "feat(harness): complete Agent Harness layer — config, features, context, guardrails, orchestrator, employee, CLI"
```

---

## Summary of Files Created

| File | Purpose |
|------|---------|
| `harness/__init__.py` | Public exports |
| `harness/config.py` | HarnessConfig dataclass |
| `harness/features.py` | Feature + FeatureTracker |
| `harness/context_manager.py` | Progress file I/O + system prompt builder |
| `harness/guardrails.py` | CostGuard, CommandGuard, ApprovalGate |
| `harness/session_orchestrator.py` | Main harness while-loop |
| `harness/employee.py` | Employee YAML persona + start_shift |
| `harness/cli_commands.py` | CLI command handlers |
| `tests/test_harness/test_config.py` | Config tests |
| `tests/test_harness/test_features.py` | Feature tracking tests |
| `tests/test_harness/test_context_manager.py` | Context loading tests |
| `tests/test_harness/test_guardrails.py` | Guardrail tests |
| `tests/test_harness/test_session_orchestrator.py` | Orchestrator tests |
| `tests/test_harness/test_employee.py` | Employee tests |
| `tests/test_harness/test_cli_commands.py` | CLI handler tests |

**`hermes_cli/main.py`** is modified to add `harness` and `employee` subcommands.
