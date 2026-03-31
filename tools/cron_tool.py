"""
Cron scheduling tools for Hermes.

Enables durable scheduled tasks: cron_create, cron_delete, cron_list.
Tasks are stored in ~/.hermes/scheduled_tasks.json and executed by
a background scheduler started when the agent initialises.
"""
import json
import os
import uuid
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

TASKS_FILE = os.path.expanduser("~/.hermes/scheduled_tasks.json")


# ── Persistence helpers ──────────────────────────────────────────────────────

def _load_tasks() -> list:
    if not os.path.exists(TASKS_FILE):
        return []
    try:
        with open(TASKS_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def _save_tasks(tasks: list) -> None:
    os.makedirs(os.path.dirname(TASKS_FILE), exist_ok=True)
    tmp = TASKS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(tasks, f, indent=2, default=str)
    os.replace(tmp, TASKS_FILE)


# ── Tool handlers ─────────────────────────────────────────────────────────────

def cron_create(
    prompt: str,
    schedule: str,
    label: Optional[str] = None,
) -> str:
    """Create a scheduled recurring task.

    Args:
        prompt: The prompt/command to run on schedule
        schedule: Cron expression (5 fields: min hour day month weekday)
                  OR natural language: "daily", "hourly", "weekly", "every Xm/Xh/Xd"
        label: Optional human-readable name for the task

    Returns JSON with task_id on success.
    """
    # Normalize natural language schedules
    schedule_map = {
        "hourly": "0 * * * *",
        "daily": "0 9 * * *",
        "weekly": "0 9 * * 1",
        "monthly": "0 9 1 * *",
    }
    cron_expr = schedule_map.get(schedule.lower().strip(), schedule)

    task = {
        "id": str(uuid.uuid4())[:8],
        "prompt": prompt,
        "schedule": cron_expr,
        "label": label or prompt[:50],
        "created_at": datetime.utcnow().isoformat(),
        "last_run": None,
        "enabled": True,
    }
    tasks = _load_tasks()
    tasks.append(task)
    _save_tasks(tasks)
    return json.dumps({
        "success": True,
        "task_id": task["id"],
        "schedule": cron_expr,
        "label": task["label"],
    })


def cron_delete(task_id: str) -> str:
    """Delete a scheduled task by ID."""
    tasks = _load_tasks()
    before = len(tasks)
    tasks = [t for t in tasks if t["id"] != task_id]
    if len(tasks) == before:
        return json.dumps({"success": False, "error": f"Task {task_id!r} not found"})
    _save_tasks(tasks)
    return json.dumps({"success": True, "deleted": task_id})


def cron_list() -> str:
    """List all scheduled tasks."""
    tasks = _load_tasks()
    return json.dumps({"tasks": tasks, "count": len(tasks)})


# ── Registration ──────────────────────────────────────────────────────────────

def register_cron_tools() -> None:
    from tools.registry import registry

    # Guard against double-registration
    if "cron_create" in registry.get_all_tool_names():
        return

    registry.register(
        name="cron_create",
        toolset="automation",
        handler=lambda args, **_: cron_create(
            prompt=args.get("prompt", ""),
            schedule=args.get("schedule", "daily"),
            label=args.get("label"),
        ),
        schema={
            "name": "cron_create",
            "description": (
                "Schedule a recurring task. Use for: daily deal reviews, "
                "weekly follow-up reminders, periodic pipeline checks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The task/command to run on schedule",
                    },
                    "schedule": {
                        "type": "string",
                        "description": (
                            "Cron expression (5 fields) or: daily, hourly, weekly, monthly"
                        ),
                    },
                    "label": {
                        "type": "string",
                        "description": "Human-readable name for this scheduled task",
                    },
                },
                "required": ["prompt", "schedule"],
            },
        },
        is_concurrency_safe=True,
        description="Schedule a recurring task",
        emoji="⏰",
    )

    registry.register(
        name="cron_delete",
        toolset="automation",
        handler=lambda args, **_: cron_delete(task_id=args.get("task_id", "")),
        schema={
            "name": "cron_delete",
            "description": "Delete a scheduled recurring task by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Task ID from cron_list",
                    },
                },
                "required": ["task_id"],
            },
        },
        is_concurrency_safe=False,
        description="Delete a scheduled task",
        emoji="🗑️",
    )

    registry.register(
        name="cron_list",
        toolset="automation",
        handler=lambda args, **_: cron_list(),
        schema={
            "name": "cron_list",
            "description": "List all scheduled recurring tasks.",
            "parameters": {"type": "object", "properties": {}},
        },
        is_concurrency_safe=True,
        description="List scheduled tasks",
        emoji="📋",
    )


# Auto-register when module is imported (triggered by _discover_tools)
register_cron_tools()
