"""CLI command group: `hermes harness`

Provides:
    hermes harness start --website URL [--contact HANDLE] [--chat-id ID]
    hermes harness status
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import click

try:
    from rich.console import Console
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich import print as rprint
    _RICH = True
except ImportError:
    _RICH = False


console = Console() if _RICH else None
HERMES_DIR = Path.home() / ".hermes"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_url(url: str) -> str:
    """Normalize and basic-validate URL."""
    if not url:
        raise click.BadParameter("URL cannot be empty")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return url


def _print_summary_table(summary: dict) -> None:
    """Print a rich table summarising the onboarding result."""
    if not _RICH:
        click.echo(json.dumps(summary, indent=2))
        return

    status = summary.get("status", "unknown")
    color = "green" if status == "success" else ("yellow" if status == "partial" else "red")

    console.print(f"\n[bold {color}]Onboarding status: {status.upper()}[/bold {color}]")
    console.print(f"[bold]Business:[/bold] {summary.get('business_name', 'N/A')}")
    console.print(f"[bold]Vapi Assistant:[/bold] {summary.get('vapi_assistant_id') or 'N/A'}")

    # Employees table
    employees = summary.get("employees", [])
    if employees:
        table = Table(title=f"Team ({len(employees)} members)", show_lines=True)
        table.add_column("Name", style="cyan")
        table.add_column("Role", style="magenta")
        table.add_column("Status", style="green")
        for emp in employees:
            table.add_row(
                emp.get("name", "?"),
                emp.get("role", "?"),
                emp.get("status", "idle"),
            )
        console.print(table)

    # Cron jobs
    crons = summary.get("crons_installed", [])
    if crons:
        console.print(f"\n[bold]Cron jobs installed:[/bold] {len(crons)}")
        for cron in crons:
            console.print(f"  [green]✓[/green] {cron}")

    # Errors
    errors = summary.get("errors", [])
    if errors:
        console.print(f"\n[bold yellow]Warnings ({len(errors)}):[/bold yellow]")
        for err in errors:
            console.print(f"  [yellow]![/yellow] {err}")


def _print_status() -> None:
    """Print current Hermes team status."""
    employees_dir = HERMES_DIR / "employees"
    updates_path = HERMES_DIR / "team_updates.jsonl"

    # Load employees
    employees = []
    if employees_dir.exists():
        try:
            import yaml
            for yaml_file in sorted(employees_dir.glob("*.yaml")):
                try:
                    data = yaml.safe_load(yaml_file.read_text()) or {}
                    employees.append(data)
                except Exception:
                    pass
        except ImportError:
            click.echo("PyYAML not available; cannot read employee configs.")

    if not _RICH:
        if not employees:
            click.echo("No employees found in ~/.hermes/employees/")
        else:
            for emp in employees:
                click.echo(f"  {emp.get('name')} ({emp.get('role')}) — {emp.get('status', 'idle')}")
        return

    if not employees:
        console.print("[yellow]No employees found in ~/.hermes/employees/[/yellow]")
    else:
        table = Table(title="Hermes Team Status", show_lines=True)
        table.add_column("Name", style="cyan")
        table.add_column("Role", style="magenta")
        table.add_column("Status", style="green")
        table.add_column("Goal", style="white", max_width=50)
        for emp in employees:
            status = emp.get("status", "idle")
            status_color = {"working": "blue", "blocked": "red", "completed": "green"}.get(status, "white")
            table.add_row(
                emp.get("name", "?"),
                emp.get("role", "?"),
                f"[{status_color}]{status}[/{status_color}]",
                (emp.get("goal") or "")[:80],
            )
        console.print(table)

    # Last 10 team updates
    if updates_path.exists():
        lines = updates_path.read_text().splitlines()
        recent = lines[-10:]
        if recent:
            console.print("\n[bold]Recent team updates:[/bold]")
            for line in recent:
                try:
                    entry = json.loads(line)
                    ts = entry.get("timestamp", "")[:16]
                    name = entry.get("employee", "?").title()
                    msg = entry.get("message", "")[:120]
                    console.print(f"  [{ts}] [cyan]{name}:[/cyan] {msg}")
                except json.JSONDecodeError:
                    pass


# ---------------------------------------------------------------------------
# Click commands
# ---------------------------------------------------------------------------

@click.group(name="harness")
def harness_group():
    """Manage Hermes harness — onboard a business and monitor the team."""
    pass


@harness_group.command(name="start")
@click.option("--website", required=True, help="Business website URL to analyze")
@click.option("--contact", default="owner", show_default=True,
              help="Owner contact: Telegram @handle, phone +1234567890, or email")
@click.option("--chat-id", "chat_id", default=None, type=int,
              help="Telegram chat ID for gateway notifications")
def cmd_start(website: str, contact: str, chat_id: Optional[int]) -> None:
    """Onboard a business: analyze website, build team, install crons.

    Example:\n
        hermes harness start --website https://example.com --contact @mybusiness
    """
    try:
        website = _validate_url(website)
    except click.BadParameter as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Starting Hermes onboarding for {website}")
    click.echo(f"Contact: {contact}")
    if chat_id:
        click.echo(f"Chat ID: {chat_id}")

    # Run the pipeline
    try:
        from harness.onboard_pipeline import run_onboarding
    except ImportError as exc:
        click.echo(f"Error: Could not import onboard_pipeline: {exc}", err=True)
        sys.exit(1)

    if _RICH:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Running onboarding pipeline...", total=None)
            summary = asyncio.run(run_onboarding(
                website_url=website,
                user_contact=contact,
                gateway_chat_id=chat_id,
            ))
            progress.update(task, completed=True)
    else:
        summary = asyncio.run(run_onboarding(
            website_url=website,
            user_contact=contact,
            gateway_chat_id=chat_id,
        ))

    _print_summary_table(summary)

    exit_code = 0 if summary.get("status") in ("success", "partial") else 1
    sys.exit(exit_code)


@harness_group.command(name="status")
def cmd_status() -> None:
    """Show current team status and recent activity.

    Reads ~/.hermes/employees/*.yaml and ~/.hermes/team_updates.jsonl.
    """
    _print_status()
