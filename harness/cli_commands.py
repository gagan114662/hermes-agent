"""CLI command handlers for the harness and employee subcommands.

These are pure functions that implement the logic for:
  hermes harness run <spec_file>
  hermes employee create <name> <role> <goal>
  hermes employee start <name>
  hermes employee status

Each function returns an integer exit code (0 = success).

Integration
-----------
These functions are wired into hermes_cli/main.py's argparse dispatch.
See the block that handles args.command == "harness" and "employee".
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Module-level import so tests can patch harness.cli_commands.SessionOrchestrator
from harness.session_orchestrator import SessionOrchestrator  # noqa: E402


def _get_employees_dir(employees_dir: Optional[Path] = None) -> Path:
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

    Returns 0 on success, 1 on error.
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
    """Create a new AI employee config."""
    from harness.employee import Employee

    dir_ = _get_employees_dir(employees_dir)
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
    """Start a shift for an employee."""
    from harness.employee import Employee

    dir_ = _get_employees_dir(employees_dir)
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

    dir_ = _get_employees_dir(employees_dir)
    employees = Employee.list_all(employees_dir=dir_)

    if not employees:
        print("No employees found. Create one with: hermes employee create <name> <role> <goal>")
        return 0

    print(f"{'NAME':<15} {'ROLE':<25} {'STATUS':<12} GOAL")
    print("-" * 80)
    for emp in employees:
        print(f"{emp.name:<15} {emp.role:<25} {emp.status:<12} {emp.goal[:40]}")
    return 0


# ── argparse wrapper functions (for set_defaults(func=...)) ──────────

def cmd_harness(args) -> None:
    """Top-level dispatcher for `hermes harness` subcommands."""
    if args.harness_command == "run":
        sys.exit(cmd_harness_run(spec_file=args.spec_file))
    else:
        # Print help: the parser is stored on args via set_defaults
        if hasattr(args, "_harness_parser"):
            args._harness_parser.print_help()
        sys.exit(1)


def cmd_employee(args) -> None:
    """Top-level dispatcher for `hermes employee` subcommands."""
    if args.employee_command == "create":
        sys.exit(cmd_employee_create(name=args.name, role=args.role, goal=args.goal))
    elif args.employee_command == "start":
        sys.exit(cmd_employee_start(
            name=args.name,
            project_dir=getattr(args, "project_dir", None),
        ))
    elif args.employee_command == "status":
        sys.exit(cmd_employee_status())
    else:
        if hasattr(args, "_employee_parser"):
            args._employee_parser.print_help()
        sys.exit(1)
