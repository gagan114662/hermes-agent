"""Henry — Project Manager orchestration engine.

Henry is the PM employee who manages all other employees, delegates work,
tracks progress, and reports to the business owner. Henry runs on a schedule
(9am and 5pm daily), executes standups, compiles digests, and escalates blockers.

Key responsibilities:
  • Morning standup (9am): Check employee status, plan the day, delegate tasks
  • Evening report (5pm): Compile daily digest, send update to owner via voice or text
  • Escalation: When employees are blocked, Henry decides: fix, reassign, or escalate
  • Delegation: Analyze tasks and pick the best employee based on role match

Usage
-----
    henry = HenryPM(business_profile_path=Path("~/.hermes/business.yaml"), user_contact="+1-555-0100")
    await henry.morning_briefing()
    await henry.evening_report()

Or use the entry point directly:
    await run_henry_shift(business_profile_path, user_contact)
"""
from __future__ import annotations

import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def create_henry(business_name: str, user_contact: str) -> "Employee":
    """Factory to create the Henry Project Manager employee."""
    from harness.employee import Employee

    henry = Employee(
        name="henry",
        role="Project Manager",
        goal=f"Manage the {business_name} AI team. Delegate tasks to specialist employees, "
        f"track their progress, compile daily digests, and keep the business owner informed. "
        f"Proactively identify opportunities and blockers.",
        kpis=[
            "All employees completing assigned tasks on schedule",
            "Daily progress digest sent to owner",
            "Blockers identified and escalated within 1 hour",
            "Zero missed customer interactions",
        ],
        schedule="0 9,17 * * *",  # 9am and 5pm daily
    )
    return henry


class HenryPM:
    """Project Manager orchestration engine.

    Loads business profile and all employees, runs standups, delegates tasks,
    compiles digests, and communicates with the business owner.

    Attributes
    ----------
    business_profile_path : Path to business profile YAML.
    user_contact          : Owner's phone number or messaging handle for updates.
    business_profile      : Loaded business metadata (name, description, etc).
    employees             : All loaded Employee instances.
    """

    def __init__(self, business_profile_path: Path, user_contact: str) -> None:
        """Initialize Henry with business profile and user contact info.

        Parameters
        ----------
        business_profile_path : Path to ~/.hermes/business.yaml or similar.
        user_contact          : Phone number (+1-555-0100) or handle for updates.
        """
        self.business_profile_path = Path(business_profile_path)
        self.user_contact = user_contact
        self.business_profile = self._load_business_profile()

        from harness.employee import Employee

        # Load all employees from disk
        self.employees = Employee.list_all()

    def _load_business_profile(self) -> dict:
        """Load business profile from YAML. Returns empty dict if missing."""
        if not self.business_profile_path.exists():
            logger.warning("Business profile not found: %s", self.business_profile_path)
            return {}

        try:
            import yaml

            content = self.business_profile_path.read_text()
            profile = yaml.safe_load(content) or {}
            return profile
        except Exception as exc:
            logger.error("Could not load business profile: %s", exc)
            return {}

    async def run_daily_standup(self) -> dict:
        """Check each employee's status and compile a standup summary.

        Returns
        -------
        dict with keys:
          - employee_statuses: list of {"name": str, "status": str, "goal": str}
          - blockers: list of {"employee": str, "issue": str}
          - opportunities: list of {"description": str}
        """
        statuses = []
        blockers = []
        opportunities = []

        for emp in self.employees:
            if emp.name == "henry":
                # Skip Henry's own status
                continue

            status_entry = {
                "name": emp.name,
                "status": emp.status,
                "role": emp.role,
                "goal": emp.goal,
            }
            statuses.append(status_entry)

            # Detect blockers (employee status is 'blocked')
            if emp.status == "blocked":
                blockers.append(
                    {
                        "employee": emp.name,
                        "issue": f"{emp.name} ({emp.role}) is blocked",
                    }
                )

        # TODO: Add opportunity detection based on employee output and market data
        return {
            "employee_statuses": statuses,
            "blockers": blockers,
            "opportunities": opportunities,
        }

    async def delegate_task(
        self, task_description: str, preferred_employee: str = None
    ) -> dict:
        """Analyze task and delegate to the best matching employee.

        Parameters
        ----------
        task_description      : What needs to be done.
        preferred_employee    : Optional name to prefer (if available).

        Returns
        -------
        dict with keys:
          - delegated_to: str (employee name)
          - task: str (description)
          - status: str (success or error)
        """
        # Filter out Henry from candidate pool
        candidates = [e for e in self.employees if e.name != "henry"]

        if not candidates:
            logger.warning("No employees available to delegate to")
            return {
                "delegated_to": None,
                "task": task_description,
                "status": "error",
                "reason": "No available employees",
            }

        # If preferred employee is specified and available, use them
        if preferred_employee:
            matched = [e for e in candidates if e.name == preferred_employee]
            if matched and matched[0].status != "blocked":
                selected = matched[0]
                return {
                    "delegated_to": selected.name,
                    "task": task_description,
                    "status": "delegated",
                    "reason": f"Assigned to preferred employee {selected.name} ({selected.role})",
                }

        # Otherwise pick best match based on role keywords in task description
        task_lower = task_description.lower()
        best_match = None
        best_score = 0

        for emp in candidates:
            if emp.status == "blocked":
                continue  # Skip blocked employees

            role_lower = emp.role.lower()
            score = 0

            # Simple keyword matching between task and employee role
            keywords = ["backend", "frontend", "api", "database", "design", "qa", "devops"]
            for kw in keywords:
                if kw in task_lower and kw in role_lower:
                    score += 1

            # Prefer idle employees over working ones
            if emp.status == "idle":
                score += 10

            if score > best_score:
                best_score = score
                best_match = emp

        # Fallback to first idle/working employee if no keywords matched
        if not best_match:
            best_match = next(
                (e for e in candidates if e.status in ("idle", "working")),
                candidates[0],
            )

        return {
            "delegated_to": best_match.name,
            "task": task_description,
            "status": "delegated",
            "reason": f"Assigned to {best_match.name} ({best_match.role})",
        }

    async def compile_daily_digest(self) -> str:
        """Build a human-readable summary of all employee work for the day.

        Returns
        -------
        str: Formatted digest ready to send to owner.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d")
        business_name = self.business_profile.get("name", "Your Business")

        lines = [f"Hey there, here's what your {business_name} team did today ({timestamp}):\n"]

        # Summarize each employee's status
        for emp in self.employees:
            if emp.name == "henry":
                continue

            status_emoji = {
                "idle": "⏸",
                "working": "🔄",
                "completed": "✅",
                "blocked": "🚨",
            }.get(emp.status, "❓")

            lines.append(f"{status_emoji} {emp.name.title()} ({emp.role})")
            lines.append(f"   Goal: {emp.goal}")
            lines.append(f"   Status: {emp.status}")

        # Add any blockers detected
        standup = await self.run_daily_standup()
        if standup.get("blockers"):
            lines.append("\n⚠️ Active Blockers:")
            for blocker in standup["blockers"]:
                lines.append(f"  • {blocker['employee']}: {blocker['issue']}")

        # Sign off
        lines.append(
            "\nLet me know if you want to dive deeper into any area or need adjustments to the team's priorities."
        )

        return "\n".join(lines)

    async def send_update_to_owner(self, message: str, voice: bool = False) -> None:
        """Send an update to the business owner via voice or text.

        Parameters
        ----------
        message : The update text to send.
        voice   : If True, initiate a voice call. Otherwise send via text.
        """
        if voice:
            await self._send_voice_update(message)
        else:
            await self._send_text_update(message)

    async def _send_voice_update(self, message: str) -> None:
        """Initiate a voice call to the owner via Vapi."""
        try:
            from tools.vapi_tool import vapi_outbound_call_tool

            # Ensure phone number is in E.164 format
            phone = self.user_contact
            if not phone.startswith("+"):
                # Assume US if no country code
                phone = f"+1{phone.replace('-', '').replace(' ', '')}"

            result = vapi_outbound_call_tool(phone, message)
            logger.info("Voice update initiated: %s", result)
        except ImportError:
            logger.warning("Vapi tool not available; falling back to text update")
            await self._send_text_update(message)
        except Exception as exc:
            logger.error("Could not send voice update: %s", exc)

    async def _send_text_update(self, message: str) -> None:
        """Send a text update via send_message_tool."""
        try:
            from tools.send_message_tool import send_message_tool

            # Determine platform from contact format
            platform = "telegram"  # Default
            if self.user_contact.startswith("+"):
                platform = "whatsapp"
            elif "@" in self.user_contact:
                platform = "email"

            args = {
                "action": "send",
                "target": f"{platform}:{self.user_contact}",
                "message": message,
            }

            # send_message_tool is sync but uses async internally
            result_json = send_message_tool(args)
            result = json.loads(result_json) if isinstance(result_json, str) else result_json
            if result.get("success"):
                logger.info("Text update sent to owner")
            else:
                logger.warning("Text update failed: %s", result.get("error"))
        except ImportError:
            logger.warning("send_message tool not available")
        except Exception as exc:
            logger.error("Could not send text update: %s", exc)

    async def morning_briefing(self) -> None:
        """Run at 9am: standup, plan the day, delegate initial tasks."""
        logger.info("🌅 Morning briefing starting...")

        # Run standup and capture status
        standup = await self.run_daily_standup()

        # Escalate any blockers immediately
        for blocker in standup.get("blockers", []):
            await self.handle_escalation(blocker["employee"], blocker["issue"])

        # If we have a task queue or opportunity pipeline, delegate early-day tasks
        # (This would integrate with a task queue system in a real implementation)

        logger.info("✅ Morning briefing complete")

    async def evening_report(self) -> None:
        """Run at 5pm: compile digest and send to owner."""
        logger.info("🌆 Evening report starting...")

        # Compile the day's work summary
        digest = await self.compile_daily_digest()

        # Decide whether to send voice or text
        # (For now, default to text; could be smarter based on time/context)
        voice = False
        await self.send_update_to_owner(digest, voice=voice)

        logger.info("✅ Evening report complete")

    async def handle_escalation(self, employee_name: str, issue: str) -> None:
        """When an employee is blocked, decide: fix, reassign, or escalate to owner.

        Parameters
        ----------
        employee_name : Name of the blocked employee.
        issue         : Description of the blocker.
        """
        logger.warning("🚨 Escalation: %s - %s", employee_name, issue)

        # Find the employee
        emp = next((e for e in self.employees if e.name == employee_name), None)
        if not emp:
            logger.error("Employee not found: %s", employee_name)
            return

        # Strategy: Try to reassign to a colleague with similar role, or escalate to owner
        candidates = [
            e
            for e in self.employees
            if e.name != employee_name
            and e.status != "blocked"
            and e.role == emp.role
        ]

        if candidates:
            # Reassign to a colleague with the same role
            reassign_to = candidates[0]
            logger.info(
                "Reassigning %s's work to %s", employee_name, reassign_to.name
            )
            # In a real system, we'd move tasks from emp to reassign_to
        else:
            # Escalate to the owner
            escalation_msg = (
                f"🚨 ESCALATION NEEDED\n\n"
                f"Employee: {employee_name}\n"
                f"Role: {emp.role}\n"
                f"Issue: {issue}\n\n"
                f"I couldn't find a colleague to reassign their work to. "
                f"You may need to step in or provide guidance."
            )
            await self.send_update_to_owner(escalation_msg, voice=False)


async def run_henry_shift(
    business_profile_path: Path, user_contact: str
) -> None:
    """Entry point: create HenryPM and run the appropriate shift.

    Checks the time of day and runs morning briefing (9am) or evening report (5pm).

    Parameters
    ----------
    business_profile_path : Path to business profile YAML.
    user_contact          : Owner's phone or messaging handle.
    """
    henry = HenryPM(business_profile_path=business_profile_path, user_contact=user_contact)

    now = datetime.now()
    hour = now.hour

    if 8 <= hour < 12:
        # Morning hours: run briefing
        await henry.morning_briefing()
    elif 17 <= hour < 20:
        # Evening hours: run report
        await henry.evening_report()
    else:
        # Off-hours: just log
        logger.info("Henry is off-duty (outside 9am-12pm and 5pm-8pm)")
