"""Unified onboarding pipeline for Hermes AI agent platform.

Wires together website analysis, team generation, Henry PM creation,
Vapi provisioning, cron installation, and welcome message in a single
async function.

Usage
-----
    from harness.onboard_pipeline import run_onboarding

    summary = await run_onboarding(
        website_url="https://example.com",
        user_contact="@owner_handle",
        gateway_chat_id=12345,
    )
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

HERMES_DIR = Path.home() / ".hermes"


# ---------------------------------------------------------------------------
# Step helpers
# ---------------------------------------------------------------------------

async def _step_analyze_website(website_url: str) -> tuple[dict, Path]:
    """Analyze website and save profile to ~/.hermes/business_profile.json.

    Returns the profile dict and the saved path.
    """
    from scripts.website_analyzer import analyze_website

    logger.info("Analyzing website: %s", website_url)
    profile = await analyze_website(website_url)
    profile_dict = asdict(profile)

    HERMES_DIR.mkdir(parents=True, exist_ok=True)
    profile_path = HERMES_DIR / "business_profile.json"
    profile_path.write_text(json.dumps(profile_dict, indent=2))
    logger.info("Business profile saved to %s", profile_path)

    # Also save a YAML copy as business.yaml (used by HenryPM)
    try:
        import yaml
        yaml_path = HERMES_DIR / "business.yaml"
        yaml_path.write_text(yaml.dump(profile_dict, default_flow_style=False))
        logger.info("YAML profile saved to %s", yaml_path)
    except ImportError:
        logger.warning("PyYAML not available; skipping business.yaml")

    return profile_dict, profile_path


async def _step_provision_team(
    profile_path: Path,
    user_contact: str,
) -> dict:
    """Generate team with LLM and provision employees (including Henry)."""
    from harness.team_factory import provision_team

    logger.info("Provisioning team from profile: %s", profile_path)
    result = await provision_team(
        profile_path=profile_path,
        project_dir=HERMES_DIR,
        employees_dir=HERMES_DIR / "employees",
        user_contact=user_contact,
        auto_start=False,
    )
    logger.info("Team provisioned: %s", result.get("summary", ""))
    return result


def _step_create_henry(business_name: str, user_contact: str) -> dict:
    """Create Henry PM config and save to ~/.hermes/employees/henry.yaml."""
    from harness.henry import create_henry

    logger.info("Creating Henry PM for %s", business_name)
    henry = create_henry(business_name=business_name, user_contact=user_contact)
    henry.employees_dir = HERMES_DIR / "employees"
    henry.save()
    logger.info("Henry saved to %s", henry._config_path)
    return {"name": henry.name, "role": henry.role, "status": henry.status}


async def _step_provision_vapi(business_name: str) -> dict:
    """Provision Vapi assistant and save config to ~/.hermes/vapi_config.json."""
    from scripts.provision_vapi_assistant import provision_vapi_assistant

    logger.info("Provisioning Vapi assistant for %s", business_name)
    result = await provision_vapi_assistant(business_name=business_name)

    vapi_config_path = HERMES_DIR / "vapi_config.json"
    vapi_config_path.write_text(json.dumps(result, indent=2))
    logger.info("Vapi config saved to %s", vapi_config_path)

    return result


def _install_cron_entry(cron_expr: str, command: str) -> bool:
    """Add a cron entry if it's not already present.

    Returns True if successfully added (or already present), False on error.
    """
    try:
        # Read existing crontab (ignore error if crontab is empty)
        existing = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
        )
        current = existing.stdout if existing.returncode == 0 else ""

        full_entry = f"{cron_expr} {command}"
        if full_entry in current:
            logger.info("Cron entry already present: %s", full_entry)
            return True

        new_crontab = current.rstrip("\n") + "\n" + full_entry + "\n"
        proc = subprocess.run(
            ["crontab", "-"],
            input=new_crontab,
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            logger.warning("crontab install failed: %s", proc.stderr)
            return False

        logger.info("Cron entry installed: %s", full_entry)
        return True
    except Exception as exc:
        logger.warning("Could not install cron entry: %s", exc)
        return False


def _step_install_crons() -> list[str]:
    """Install all Hermes cron jobs. Returns list of installed entry descriptions."""
    python = sys.executable
    scripts_dir = Path(__file__).parent.parent / "scripts"
    harness_dir = Path(__file__).parent

    jobs = [
        # (cron_expression, description, command)
        (
            "0 8 * * *",
            "Morning digest (8am)",
            f"{python} {scripts_dir / 'morning_digest.py'}",
        ),
        (
            "0 9,17 * * *",
            "Henry shifts (9am + 5pm)",
            f"{python} {harness_dir / 'henry.py'}",
        ),
        (
            "*/15 * * * *",
            "Proactive loop (every 15min)",
            f"{python} {scripts_dir / 'proactive_loop.py'}",
        ),
    ]

    installed = []
    for cron_expr, description, command in jobs:
        ok = _install_cron_entry(cron_expr, command)
        if ok:
            installed.append(description)
        else:
            logger.warning("Failed to install cron: %s", description)

    return installed


def _step_write_welcome_message(business_name: str, team_size: int) -> None:
    """Write Henry's welcome message to ~/.hermes/team_updates.jsonl."""
    updates_path = HERMES_DIR / "team_updates.jsonl"
    updates_path.parent.mkdir(parents=True, exist_ok=True)

    welcome = (
        f"Hey! I'm Henry, your AI Project Manager. "
        f"I've just assembled a team of {team_size} AI agents for {business_name}. "
        f"I'll check in with you every morning at 9am and evening at 5pm with updates. "
        f"Your team is ready to get to work!"
    )

    entry = json.dumps({
        "employee": "henry",
        "role": "Project Manager",
        "message": welcome,
        "channel": "team",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    with open(updates_path, "a") as f:
        f.write(entry + "\n")

    logger.info("Welcome message written to %s", updates_path)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

async def run_onboarding(
    website_url: str,
    user_contact: str,
    gateway_chat_id: Optional[int] = None,
) -> dict:
    """Run the complete Hermes onboarding pipeline.

    Steps:
    1. Analyze website → save business_profile.json + business.yaml
    2. Provision team (LLM-generated employees)
    3. Create Henry PM config
    4. Provision Vapi voice assistant
    5. Install cron jobs
    6. Write Henry's welcome message

    Parameters
    ----------
    website_url : str
        The business website to analyze.
    user_contact : str
        Owner's contact (Telegram handle, phone, email).
    gateway_chat_id : int, optional
        Telegram chat ID for gateway notifications.

    Returns
    -------
    dict
        Summary with keys: status, business_name, team_size, employees,
        vapi_assistant_id, crons_installed, errors.
    """
    errors: list[str] = []
    summary: dict = {
        "status": "partial",
        "business_name": "Unknown",
        "team_size": 0,
        "employees": [],
        "vapi_assistant_id": None,
        "crons_installed": [],
        "errors": errors,
    }

    # ── Step 1: Analyze website ───────────────────────────────────────
    profile_dict: dict = {}
    profile_path: Optional[Path] = None
    try:
        profile_dict, profile_path = await _step_analyze_website(website_url)
        summary["business_name"] = profile_dict.get("business_name", "Unknown")
        logger.info("Website analysis complete: %s", summary["business_name"])
    except Exception as exc:
        msg = f"Website analysis failed: {exc}"
        logger.error(msg)
        errors.append(msg)
        # Can't continue without a profile
        summary["status"] = "error"
        return summary

    business_name = summary["business_name"]

    # ── Step 2: Provision team ────────────────────────────────────────
    team_result: dict = {}
    try:
        team_result = await _step_provision_team(profile_path, user_contact)
        summary["team_size"] = team_result.get("employee_count", 0)
        summary["employees"] = team_result.get("employees", [])
    except Exception as exc:
        msg = f"Team provisioning failed: {exc}"
        logger.error(msg)
        errors.append(msg)

    # ── Step 3: Create Henry ──────────────────────────────────────────
    try:
        # provision_team already adds Henry, but ensure we have a fresh config
        henry_info = _step_create_henry(business_name, user_contact)
        # Upsert henry into employees list if not already there
        henry_names = {e.get("name") for e in summary["employees"]}
        if "henry" not in henry_names:
            summary["employees"].append(henry_info)
            summary["team_size"] = len(summary["employees"])
    except Exception as exc:
        msg = f"Henry PM creation failed: {exc}"
        logger.error(msg)
        errors.append(msg)

    # ── Step 4: Provision Vapi ────────────────────────────────────────
    try:
        vapi_result = await _step_provision_vapi(business_name)
        summary["vapi_assistant_id"] = vapi_result.get("assistant_id")
        if vapi_result.get("status") == "error":
            errors.append(f"Vapi provisioning: {vapi_result.get('message', 'unknown error')}")
    except Exception as exc:
        msg = f"Vapi provisioning failed: {exc}"
        logger.warning(msg)
        errors.append(msg)

    # ── Step 5: Install cron jobs ─────────────────────────────────────
    try:
        installed_crons = _step_install_crons()
        summary["crons_installed"] = installed_crons
    except Exception as exc:
        msg = f"Cron installation failed: {exc}"
        logger.warning(msg)
        errors.append(msg)

    # ── Step 6: Welcome message ───────────────────────────────────────
    try:
        _step_write_welcome_message(business_name, summary["team_size"])
    except Exception as exc:
        msg = f"Welcome message failed: {exc}"
        logger.warning(msg)
        errors.append(msg)

    # ── Finalize ──────────────────────────────────────────────────────
    summary["status"] = "success" if not errors else "partial"
    logger.info(
        "Onboarding complete for %s — %d employees, %d crons, status=%s",
        business_name,
        summary["team_size"],
        len(summary["crons_installed"]),
        summary["status"],
    )
    return summary
