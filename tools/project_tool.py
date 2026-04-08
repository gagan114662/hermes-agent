"""
Project Management Tool — Daily Deadlines, Not Weekly Surprises

Weekly deadlines turn into surprises at the end of the week.
Daily deadlines surface problems in hours, not days.

Every task broken down to the single-day level. When a task is that
granular, you know at 6pm whether you're on track.
"""

import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from tools.registry import registry


def _projects_dir(client: str) -> Path:
    safe = client.lower().replace(" ", "_").replace("/", "_")
    d = Path(os.path.expanduser(f"~/.hermes/projects/{safe}"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_tasks(client: str) -> dict:
    path = _projects_dir(client) / "tasks.json"
    if path.exists():
        return json.loads(path.read_text())
    return {"tasks": [], "created_at": datetime.now().isoformat()}


def _save_tasks(client: str, data: dict) -> None:
    path = _projects_dir(client) / "tasks.json"
    path.write_text(json.dumps(data, indent=2))


def project_create(client_name: str, phases: str) -> str:
    """
    Create a project with phases and daily-level tasks.

    Args:
        client_name: Client name
        phases: JSON string of phases, each with name and tasks. Example:
                '[{"name": "Phase 1: Core", "tasks": ["Set up database schema", "Build API layer", "Configure auth"]},
                  {"name": "Phase 2: Integrations", "tasks": ["Connect Apollo API", "Build scoring function", "Set up Slack notifications"]}]'
    """
    try:
        phase_list = json.loads(phases)
    except json.JSONDecodeError:
        # Try comma-separated phase names as fallback
        phase_names = [p.strip() for p in phases.split(",")]
        phase_list = [{"name": p, "tasks": []} for p in phase_names]

    data = _load_tasks(client_name)
    data["tasks"] = []
    data["client"] = client_name
    data["created_at"] = datetime.now().isoformat()

    task_date = datetime.now()
    total_tasks = 0

    for phase in phase_list:
        phase_name = phase.get("name", "Unnamed Phase")
        phase_tasks = phase.get("tasks", [])

        for task_name in phase_tasks:
            task_id = str(uuid.uuid4())[:8]
            data["tasks"].append({
                "id": task_id,
                "phase": phase_name,
                "name": task_name,
                "status": "todo",
                "due": task_date.strftime("%Y-%m-%d"),
                "created_at": datetime.now().isoformat(),
                "completed_at": None,
                "notes": "",
            })
            task_date += timedelta(days=1)
            # Skip weekends
            while task_date.weekday() >= 5:
                task_date += timedelta(days=1)
            total_tasks += 1

    _save_tasks(client_name, data)

    lines = [f"Project created for {client_name}: {total_tasks} tasks across {len(phase_list)} phases.\n"]
    current_phase = None
    for task in data["tasks"]:
        if task["phase"] != current_phase:
            current_phase = task["phase"]
            lines.append(f"\n{current_phase}:")
        lines.append(f"  [{task['id']}] {task['due']} — {task['name']}")

    lines.append(f"\nUse project_standup('{client_name}') for daily check-ins.")
    return "\n".join(lines)


def project_standup(client_name: str) -> str:
    """
    Run the daily standup: what's done, what's today, any blockers.
    Three questions. Ten minutes. Every blocker surfaces before it becomes a delay.
    """
    data = _load_tasks(client_name)
    tasks = data.get("tasks", [])
    if not tasks:
        return f"No tasks found for '{client_name}'. Run project_create first."

    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    completed_yesterday = [t for t in tasks if t.get("completed_at", "")[:10] == yesterday]
    due_today = [t for t in tasks if t["due"] == today and t["status"] != "done"]
    blocked = [t for t in tasks if t["status"] == "blocked"]
    overdue = [t for t in tasks if t["due"] < today and t["status"] not in ("done", "blocked")]

    lines = [f"Daily Standup — {client_name} — {today}\n"]

    lines.append("✅ Completed yesterday:")
    if completed_yesterday:
        for t in completed_yesterday:
            lines.append(f"  [{t['id']}] {t['name']}")
    else:
        lines.append("  (none)")

    lines.append("\n📋 Due today:")
    if due_today:
        for t in due_today:
            lines.append(f"  [{t['id']}] {t['name']} — {t['phase']}")
    else:
        lines.append("  (nothing scheduled for today)")

    if blocked:
        lines.append("\n🚫 BLOCKED:")
        for t in blocked:
            lines.append(f"  [{t['id']}] {t['name']}{' — ' + t['notes'] if t['notes'] else ''}")

    if overdue:
        lines.append(f"\n⚠️  OVERDUE ({len(overdue)} tasks):")
        for t in overdue[:5]:
            lines.append(f"  [{t['id']}] {t['name']} (was due {t['due']})")

    # Progress summary
    done_count = sum(1 for t in tasks if t["status"] == "done")
    lines.append(f"\nProgress: {done_count}/{len(tasks)} tasks done ({int(done_count/len(tasks)*100)}%)")

    lines.append(f"\nUse project_update('{client_name}', task_id, status) to update tasks.")
    return "\n".join(lines)


def project_update(client_name: str, task_id: str, status: str, notes: str = "") -> str:
    """
    Update a task's status. Status options: todo, in_progress, done, blocked.
    """
    valid = ("todo", "in_progress", "done", "blocked")
    if status not in valid:
        return f"Invalid status '{status}'. Use one of: {', '.join(valid)}"

    data = _load_tasks(client_name)
    for task in data["tasks"]:
        if task["id"] == task_id:
            task["status"] = status
            if notes:
                task["notes"] = notes
            if status == "done":
                task["completed_at"] = datetime.now().isoformat()
            _save_tasks(client_name, data)
            return f"Task [{task_id}] '{task['name']}' → {status}"

    return f"Task '{task_id}' not found for '{client_name}'."


def project_milestone_check(client_name: str) -> str:
    """
    Check if the project is on track vs. its planned timeline.
    Flags slipping milestones before they become delays.
    """
    data = _load_tasks(client_name)
    tasks = data.get("tasks", [])
    if not tasks:
        return f"No tasks found for '{client_name}'."

    today = datetime.now().strftime("%Y-%m-%d")
    overdue = [t for t in tasks if t["due"] < today and t["status"] not in ("done", "blocked")]
    done = [t for t in tasks if t["status"] == "done"]
    total = len(tasks)
    pct = int(len(done) / total * 100) if total else 0

    # Group by phase
    phases: dict = {}
    for t in tasks:
        phases.setdefault(t["phase"], {"total": 0, "done": 0, "overdue": 0})
        phases[t["phase"]]["total"] += 1
        if t["status"] == "done":
            phases[t["phase"]]["done"] += 1
        if t["due"] < today and t["status"] not in ("done", "blocked"):
            phases[t["phase"]]["overdue"] += 1

    lines = [f"Milestone check — {client_name} — {today}", f"Overall: {pct}% complete ({len(done)}/{total} tasks)\n"]

    for phase, stats in phases.items():
        phase_pct = int(stats["done"] / stats["total"] * 100) if stats["total"] else 0
        flag = " ⚠️ SLIPPING" if stats["overdue"] > 0 else " ✅"
        lines.append(f"{phase}: {phase_pct}% ({stats['done']}/{stats['total']}){flag}")
        if stats["overdue"]:
            lines.append(f"  → {stats['overdue']} overdue tasks")

    if overdue:
        lines.append(f"\n{len(overdue)} overdue tasks need attention. Run project_standup for details.")
    else:
        lines.append("\nAll milestones on track.")

    return "\n".join(lines)


def project_list(client_name: str) -> str:
    """List all tasks for a client project."""
    data = _load_tasks(client_name)
    tasks = data.get("tasks", [])
    if not tasks:
        return f"No tasks found for '{client_name}'."

    lines = [f"Tasks for {client_name}:\n"]
    current_phase = None
    for t in tasks:
        if t["phase"] != current_phase:
            current_phase = t["phase"]
            lines.append(f"\n{current_phase}:")
        status_icon = {"done": "✅", "in_progress": "🔄", "blocked": "🚫", "todo": "⬜"}.get(t["status"], "⬜")
        lines.append(f"  {status_icon} [{t['id']}] {t['due']} — {t['name']}")
    return "\n".join(lines)


registry.register(
    name="project_create",
    toolset="crm",
    schema={
        "name": "project_create",
        "description": "Create a project with phases and daily-level tasks. Break work down to single-day tasks so blockers surface in hours, not days.",
        "parameters": {
            "type": "object",
            "properties": {
                "client_name": {"type": "string", "description": "Client name"},
                "phases": {"type": "string", "description": 'JSON array of phases with tasks. Example: [{"name": "Phase 1: Core", "tasks": ["Set up database", "Build API layer"]}, {"name": "Phase 2: UI", "tasks": ["Build dashboard", "Add auth"]}]'},
            },
            "required": ["client_name", "phases"],
        },
    },
    handler=lambda args, **kw: project_create(
        client_name=args["client_name"],
        phases=args["phases"],
    ),
)

registry.register(
    name="project_standup",
    toolset="crm",
    schema={
        "name": "project_standup",
        "description": "Run the daily standup for a client project: what completed yesterday, what's due today, any blockers. Run this every morning to catch problems before they become delays.",
        "parameters": {
            "type": "object",
            "properties": {
                "client_name": {"type": "string", "description": "Client name"},
            },
            "required": ["client_name"],
        },
    },
    handler=lambda args, **kw: project_standup(client_name=args["client_name"]),
)

registry.register(
    name="project_update",
    toolset="crm",
    schema={
        "name": "project_update",
        "description": "Update a task status. Status: todo, in_progress, done, blocked.",
        "parameters": {
            "type": "object",
            "properties": {
                "client_name": {"type": "string", "description": "Client name"},
                "task_id": {"type": "string", "description": "8-character task ID from project_standup or project_list"},
                "status": {"type": "string", "enum": ["todo", "in_progress", "done", "blocked"], "description": "New status"},
                "notes": {"type": "string", "description": "Notes (required if blocked — explain what's blocking)"},
            },
            "required": ["client_name", "task_id", "status"],
        },
    },
    handler=lambda args, **kw: project_update(
        client_name=args["client_name"],
        task_id=args["task_id"],
        status=args["status"],
        notes=args.get("notes", ""),
    ),
)

registry.register(
    name="project_milestone_check",
    toolset="crm",
    schema={
        "name": "project_milestone_check",
        "description": "Check if a project is on track against its planned timeline. Flags slipping phases before they become delays.",
        "parameters": {
            "type": "object",
            "properties": {
                "client_name": {"type": "string", "description": "Client name"},
            },
            "required": ["client_name"],
        },
    },
    handler=lambda args, **kw: project_milestone_check(client_name=args["client_name"]),
)

registry.register(
    name="project_list",
    toolset="crm",
    schema={
        "name": "project_list",
        "description": "List all tasks for a client project with their status.",
        "parameters": {
            "type": "object",
            "properties": {
                "client_name": {"type": "string", "description": "Client name"},
            },
            "required": ["client_name"],
        },
    },
    handler=lambda args, **kw: project_list(client_name=args["client_name"]),
)
