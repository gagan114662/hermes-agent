"""Kairos: always-on autonomous agent mode for Hermes."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------
_DEFAULT_SETTINGS_PATH = os.path.expanduser("~/.hermes/settings.json")
_DEFAULT_TASKS_PATH = os.path.expanduser("~/.hermes/scheduled_tasks.json")

# ---------------------------------------------------------------------------
# Global mutable state (module-level singletons)
# ---------------------------------------------------------------------------
_kairos_active: bool = False
_kairos_settings: Optional["KairosSettings"] = None


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
@dataclass
class KairosSettings:
    assistant: bool = False
    assistant_name: str = "Assistant"


def load_kairos_settings(settings_path: str = _DEFAULT_SETTINGS_PATH) -> KairosSettings:
    """Load Kairos settings from ~/.hermes/settings.json."""
    global _kairos_settings
    try:
        with open(settings_path) as f:
            data = json.load(f)
        _kairos_settings = KairosSettings(
            assistant=bool(data.get("assistant", False)),
            assistant_name=str(data.get("assistantName", "Assistant")),
        )
    except (FileNotFoundError, json.JSONDecodeError):
        _kairos_settings = KairosSettings()
    return _kairos_settings


# ---------------------------------------------------------------------------
# State accessors
# ---------------------------------------------------------------------------
def is_kairos_active() -> bool:
    return _kairos_active


def set_kairos_active(value: bool) -> None:
    global _kairos_active
    _kairos_active = value


# ---------------------------------------------------------------------------
# System prompt addendum
# ---------------------------------------------------------------------------
_KAIROS_PROMPT_ADDENDUM = """
# Assistant Mode
You are running in assistant mode. Apply these behaviours:
- Prefer concise, action-oriented responses. Skip lengthy preambles.
- Maintain continuity across restarts; reference prior context when relevant.
- Use proactive check-ins: surface blockers, deadlines, and status updates unprompted.
- When delegating, use async delegation so you can continue working in parallel.
- Keep ownership of follow-ups — don't wait to be asked; drive tasks to completion.
""".strip()


def get_kairos_prompt_addendum() -> str:
    """Return system prompt addendum when Kairos is active, empty string otherwise."""
    if not _kairos_active:
        return ""
    return _KAIROS_PROMPT_ADDENDUM


# ---------------------------------------------------------------------------
# Cron helper: next-run calculation
# ---------------------------------------------------------------------------
def _next_run_from_cron(cron_expr: str, after: Optional[int] = None) -> int:
    """
    Compute the next Unix timestamp for a cron expression.
    Falls back to 1 hour from now if croniter is unavailable.
    """
    if after is None:
        after = int(time.time())
    try:
        from croniter import croniter  # type: ignore
        itr = croniter(cron_expr, after)
        return int(itr.get_next(float))
    except ImportError:
        logger.warning("croniter not installed; defaulting next_run to +1 hour")
        return after + 3600
    except Exception as exc:
        logger.warning("Invalid cron expression %r: %s; defaulting to +1 hour", cron_expr, exc)
        return after + 3600


# ---------------------------------------------------------------------------
# Due-task helpers
# ---------------------------------------------------------------------------
def get_due_tasks(tasks_path: str = _DEFAULT_TASKS_PATH) -> list:
    """Return tasks whose next_run is <= now."""
    now = int(time.time())
    try:
        with open(tasks_path) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    due = []
    for task in data.get("tasks", []):
        next_run = task.get("next_run")
        if next_run is None:
            # Legacy task without next_run: use createdAt as seed
            next_run = _next_run_from_cron(task.get("cron", "0 * * * *"), task.get("createdAt"))
        if next_run <= now:
            due.append(task)
    return due


def mark_task_fired(task_id: str, tasks_path: str = _DEFAULT_TASKS_PATH) -> None:
    """
    For recurring tasks: advance next_run.
    For one-shot tasks: remove from the list.
    Atomic JSON rewrite with a temp file.
    """
    try:
        with open(tasks_path) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return

    now = int(time.time())
    updated_tasks = []
    for task in data.get("tasks", []):
        if task.get("id") != task_id:
            updated_tasks.append(task)
            continue
        if task.get("recurring", True):
            task["next_run"] = _next_run_from_cron(task.get("cron", "0 * * * *"), now)
            updated_tasks.append(task)
        # one-shot: drop by not appending

    data["tasks"] = updated_tasks
    tmp = tasks_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, tasks_path)


# ---------------------------------------------------------------------------
# CronExecutor — background scheduler
# ---------------------------------------------------------------------------
class CronExecutor:
    """
    Background thread that polls scheduled_tasks.json every `interval` seconds.
    When a task is due it calls `run_fn(prompt)` in a daemon thread.
    """

    def __init__(
        self,
        run_fn,  # Callable[[str], None]
        tasks_path: str = _DEFAULT_TASKS_PATH,
        interval: int = 60,
    ) -> None:
        self._run_fn = run_fn
        self._tasks_path = tasks_path
        self._interval = interval
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="kairos-cron")
        self._thread.start()
        logger.info("Kairos CronExecutor started (interval=%ds)", self._interval)

    def stop(self) -> None:
        self._stop_event.set()

    def _loop(self) -> None:
        while not self._stop_event.wait(timeout=self._interval):
            self._tick()

    def _tick(self) -> None:
        due = get_due_tasks(self._tasks_path)
        for task in due:
            task_id = task.get("id", "")
            prompt = task.get("prompt", "")
            if not prompt:
                continue
            logger.info("Kairos firing task %s: %.60s", task_id, prompt)
            mark_task_fired(task_id, self._tasks_path)
            t = threading.Thread(
                target=self._safe_run,
                args=(prompt,),
                daemon=True,
                name=f"kairos-task-{task_id[:8]}",
            )
            t.start()

    def _safe_run(self, prompt: str) -> None:
        try:
            self._run_fn(prompt)
        except Exception:
            logger.exception("Kairos task raised an exception")


# ---------------------------------------------------------------------------
# Initialisation helper
# ---------------------------------------------------------------------------
_cron_executor: Optional[CronExecutor] = None


def init_kairos(agent, settings_path: str = _DEFAULT_SETTINGS_PATH) -> bool:
    """
    Load settings; if assistant=true, activate Kairos and start the CronExecutor.
    Returns True if Kairos is now active.
    """
    global _cron_executor
    settings = load_kairos_settings(settings_path)
    if not settings.assistant:
        set_kairos_active(False)
        return False

    set_kairos_active(True)
    logger.info("Kairos activated (assistantName=%s)", settings.assistant_name)

    def _run_task(prompt: str) -> None:
        agent.run_conversation(
            conversation_history=[{"role": "user", "content": prompt}],
            task_id=None,
        )

    _cron_executor = CronExecutor(_run_task)
    _cron_executor.start()
    return True
