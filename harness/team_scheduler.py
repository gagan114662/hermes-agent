"""Team Scheduler — Register and run employee work shifts via system cron.

Converts each employee's cron schedule into a real crontab entry that
invokes their shift autonomously. Henry PM gets his own briefing command.

Usage
-----
    from harness.team_scheduler import register_team_schedules, run_employee_shift

    # Register all employees' schedules in cron
    summary = register_team_schedules(
        employees_dir=Path("~/.hermes/employees"),
        project_dir=Path("./my_project"),
    )

    # Run a specific employee's shift
    result = run_employee_shift(
        employee_name="alex_outreach",
        project_dir=Path("./my_project"),
    )

    # Remove all Hermes cron entries
    from harness.team_scheduler import unregister_team_schedules
    unregister_team_schedules()
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

from harness.employee import Employee

logger = logging.getLogger(__name__)

HERMES_CRON_MARKER = "# HERMES-AGENT"


def _find_python() -> str:
    """Return the best Python path for cron commands."""
    venv_python = Path.home() / ".hermes" / "venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return "python3"


def _build_shift_command(employee_name: str, project_dir: Path) -> str:
    """Build the shell command cron will execute for an employee shift."""
    python = _find_python()
    log_dir = Path.home() / ".hermes" / "logs"
    return (
        f"cd {project_dir} && {python} -c "
        f"\"import asyncio; from harness.team_scheduler import run_employee_shift; "
        f"asyncio.run(run_employee_shift('{employee_name}', '{project_dir}'))\" "
        f">> {log_dir}/{employee_name}.log 2>&1"
    )


def _build_henry_command(project_dir: Path, user_contact: str) -> str:
    """Build the cron command for Henry PM's briefing/report shifts."""
    python = _find_python()
    profile = Path.home() / ".hermes" / "business_profile.json"
    log_dir = Path.home() / ".hermes" / "logs"
    return (
        f"cd {project_dir} && {python} -c "
        f"\"import asyncio; from harness.henry import run_henry_shift; "
        f"asyncio.run(run_henry_shift('{profile}', '{user_contact}'))\" "
        f">> {log_dir}/henry.log 2>&1"
    )


def _read_existing_crontab() -> str:
    """Read current crontab, returning empty string if none exists."""
    try:
        result = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True, timeout=5
        )
        return result.stdout if result.returncode == 0 else ""
    except Exception:
        return ""


def _install_crontab(content: str) -> bool:
    """Write new crontab content. Returns True on success."""
    try:
        proc = subprocess.run(
            ["crontab", "-"],
            input=content,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode != 0:
            logger.error("Failed to install crontab: %s", proc.stderr)
            return False
        return True
    except Exception as exc:
        logger.error("Could not install crontab: %s", exc)
        return False


def register_team_schedules(
    employees_dir: Path,
    project_dir: Path,
    user_contact: str = "owner",
) -> dict:
    """Register real crontab entries for all employees.

    Reads all employee YAML configs, builds cron commands, and installs
    them into the system crontab. Existing Hermes entries are replaced.

    Parameters
    ----------
    employees_dir : Path
        Directory containing employee YAML configs.
    project_dir : Path
        Project working directory (passed to shifts).
    user_contact : str
        Owner contact info for Henry PM's communications.

    Returns
    -------
    dict
        Summary with keys:
        - registered_count: int
        - schedules: list of {name, schedule} dicts
        - skipped: list of {name, reason}
        - summary: str
    """
    employees_dir = Path(employees_dir).expanduser()
    project_dir = Path(project_dir).expanduser()

    # Ensure log directory exists
    log_dir = Path.home() / ".hermes" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    if not employees_dir.exists():
        logger.warning("Employees directory not found: %s", employees_dir)
        return {"registered_count": 0, "schedules": [], "skipped": [], "summary": "No employees found."}

    employees = Employee.list_all(employees_dir=employees_dir)
    if not employees:
        logger.warning("No employees found to register")
        return {"registered_count": 0, "schedules": [], "skipped": [], "summary": "No employees found."}

    # Read existing crontab and strip old Hermes entries
    existing = _read_existing_crontab()
    cleaned_lines = [
        line for line in existing.splitlines()
        if HERMES_CRON_MARKER not in line
    ]

    registered = []
    skipped = []
    new_entries = []

    for emp in employees:
        if not emp.schedule:
            skipped.append({"name": emp.name, "reason": "no schedule defined"})
            continue

        if emp.name == "henry":
            cmd = _build_henry_command(project_dir, user_contact)
        else:
            cmd = _build_shift_command(emp.name, project_dir)

        cron_line = f"{emp.schedule} {cmd} {HERMES_CRON_MARKER} [{emp.name}]"
        new_entries.append(cron_line)
        registered.append({"name": emp.name, "schedule": emp.schedule})
        logger.info("Registered schedule for %s: %s", emp.name, emp.schedule)

    # Install new crontab
    if new_entries:
        full_cron = "\n".join(cleaned_lines + new_entries) + "\n"
        _install_crontab(full_cron)

    summary = (
        f"Registered {len(registered)} employee schedules "
        f"({len(skipped)} skipped). "
        f"Employees: {', '.join(s['name'] for s in registered)}."
    )

    return {
        "registered_count": len(registered),
        "schedules": registered,
        "skipped": skipped,
        "summary": summary,
    }


def unregister_team_schedules() -> int:
    """Remove all Hermes cron entries. Returns count of removed entries."""
    existing = _read_existing_crontab()
    lines = existing.splitlines()
    cleaned = [l for l in lines if HERMES_CRON_MARKER not in l]
    removed_count = len(lines) - len(cleaned)

    if removed_count > 0:
        _install_crontab("\n".join(cleaned) + "\n")
        logger.info("Removed %d Hermes cron entries", removed_count)

    return removed_count


async def run_employee_shift(
    employee_name: str,
    project_dir: Path,
    employees_dir: Optional[Path] = None,
) -> dict:
    """Start an autonomous work shift for a specific employee.

    Loads the employee, builds their harness config, and runs
    their assigned task (goal) using SessionOrchestrator.

    Parameters
    ----------
    employee_name : str
        Name of the employee (slug, e.g., "alex_outreach").
    project_dir : Path
        Project working directory for the shift.
    employees_dir : Optional[Path]
        Directory containing employee YAML. Defaults to ~/.hermes/employees.

    Returns
    -------
    dict
        Shift result from SessionOrchestrator:
        - status: str (completed, blocked, error, etc.)
        - message: str
        - sessions_run: int
        - total_cost_usd: float
    """
    project_dir = Path(project_dir).expanduser()

    try:
        employee = Employee.load(employee_name, employees_dir=employees_dir)
        logger.info("Starting shift for %s (%s)", employee_name, employee.role)

        result = employee.start_shift(project_dir=project_dir)
        logger.info("Shift completed for %s: %s", employee_name, result.get("status"))
        return result

    except FileNotFoundError:
        logger.error("Employee not found: %s", employee_name)
        return {"status": "error", "message": f"Employee {employee_name} not found"}
    except Exception as exc:
        logger.error("Shift failed for %s: %s", employee_name, exc)
        return {
            "status": "error",
            "message": str(exc),
            "sessions_run": 0,
            "total_cost_usd": 0.0,
        }


async def run_henry_briefing(
    briefing_type: str = "auto",
    user_contact: str = "owner",
) -> dict:
    """Run Henry PM's morning briefing or evening report.

    Parameters
    ----------
    briefing_type : str
        "morning", "evening", or "auto" (picks based on current hour).
    user_contact : str
        Owner contact for Henry PM's communications.

    Returns
    -------
    dict
        Briefing result with:
        - status: str
        - briefing_text: str
        - message: str
    """
    try:
        from harness.henry import HenryPM

        profile_path = Path.home() / ".hermes" / "business_profile.json"
        if not profile_path.exists():
            return {
                "status": "error",
                "message": "Business profile not found",
                "briefing_text": "",
            }

        henry = HenryPM(
            business_profile_path=profile_path,
            user_contact=user_contact,
        )

        if briefing_type == "auto":
            from datetime import datetime
            hour = datetime.now().hour
            briefing_type = "morning" if hour < 14 else "evening"

        if briefing_type == "morning":
            await henry.morning_briefing()
            standup = await henry.run_daily_standup()
            return {
                "status": "success",
                "briefing_text": str(standup),
                "message": "Morning briefing complete",
            }
        else:
            digest = await henry.compile_daily_digest()
            await henry.send_update_to_owner(digest)
            return {
                "status": "success",
                "briefing_text": digest,
                "message": "Evening report sent",
            }

    except Exception as exc:
        logger.error("Henry briefing failed: %s", exc)
        return {
            "status": "error",
            "message": str(exc),
            "briefing_text": "",
        }
