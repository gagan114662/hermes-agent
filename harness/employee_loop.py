"""Employee Loop — autonomous shift runner for each Hermes employee.

Each employee is driven by a cron-scheduled shift.  This module handles:

    1. Load the employee's current best strategy from the experiment playbook
    2. Propose a new experiment variant to try this shift
    3. Build a shift prompt that feels like a real worker's briefing
    4. Run the employee as an AIAgent with their assigned toolsets
    5. Parse KPI metrics from the agent's natural-language output
    6. Post a human-readable update to the team chat feed
    7. Record experiment results and decide: keep or discard the strategy

The key design goal: employees should feel like real workers who say
"Sent 12 emails today, got 3 replies" — not "API call returned 200".
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

from harness.employee import Employee
from harness.experiment_loop import ExperimentLoop

logger = logging.getLogger(__name__)


class EmployeeLoop:
    """Autonomous shift runner for a single Hermes employee.

    Orchestrates the full experiment loop for one work shift:
    propose strategy → build prompt → run agent → extract metrics
    → post to team chat → record result → evaluate experiment.

    Parameters
    ----------
    employee_name : Slug matching ~/.hermes/employees/{name}.yaml
    """

    def __init__(self, employee_name: str) -> None:
        self.employee_name = employee_name
        self.employee = Employee.load(employee_name)
        self.experiment_loop = ExperimentLoop(employee_name)

    # ── Public API ────────────────────────────────────────────────────

    async def run_shift(self) -> dict:
        """Run one work shift for this employee.

        Called by cron (or manually via run_employee_shift.py).

        Returns
        -------
        Summary dict with employee, shift timing, actions taken, metrics,
        and the experiment ID that was run this shift.
        """
        shift_start = datetime.now(timezone.utc).isoformat()
        logger.info("Starting shift for employee: %s", self.employee_name)

        # 1. Load playbook (current best strategy)
        playbook = self.experiment_loop.load_playbook()

        # 2. Propose a new experiment variant
        experiment = self.experiment_loop.propose_experiment(
            hypothesis=f"Shift experiment for {self.employee_name}",
            strategy_variant={"shift_date": shift_start[:10]},
        )
        experiment_id = experiment["id"]
        logger.info("Running experiment %s for %s", experiment_id, self.employee_name)

        # 3. Build the shift prompt
        prompt = self._build_shift_prompt(experiment)

        # 4. Run the employee as an agent
        agent_output = ""
        actions_taken = []
        try:
            agent_output = await self._run_as_agent(prompt)
            actions_taken = [line.strip() for line in agent_output.splitlines()
                             if line.strip() and len(line.strip()) > 10][:10]
        except Exception as exc:
            logger.warning("Agent run failed for %s: %s", self.employee_name, exc)
            agent_output = f"[Agent error: {exc}]"
            actions_taken = ["Shift attempted but agent encountered an error"]

        # 5. Parse KPI metrics from agent output
        metrics = self._extract_metrics(agent_output)

        # 6. Post a summary to team_chat
        await self._report_to_team(agent_output)

        # 7. Record experiment result
        self.experiment_loop.record_result(experiment_id, metrics)

        # 8. Evaluate and decide: keep or discard strategy
        decision = self.experiment_loop.evaluate_and_decide(experiment_id)
        logger.info("Experiment %s decision: %s", experiment_id, decision)

        shift_end = datetime.now(timezone.utc).isoformat()

        return {
            "employee": self.employee_name,
            "shift_start": shift_start,
            "shift_end": shift_end,
            "actions_taken": actions_taken,
            "metrics": metrics,
            "experiment_id": experiment_id,
            "experiment_decision": decision,
        }

    def _build_shift_prompt(self, experiment: dict) -> str:
        """Build the shift briefing prompt for the employee agent.

        Includes role, goal, KPIs, current strategy, today's date,
        and the experiment variant to try this shift.
        """
        emp = self.employee
        today = datetime.now(timezone.utc).strftime("%A, %B %d %Y")

        # Format KPIs as bullet list
        kpi_block = "\n".join(f"  - {k}" for k in (emp.kpis or []))
        if not kpi_block:
            kpi_block = "  - Do your best work and report results"

        # Current strategy from playbook
        playbook = self.experiment_loop.load_playbook()
        strategy = playbook.get("strategy", {})
        strategy_text = ""
        if strategy:
            strategy_items = "\n".join(f"  - {k}: {v}" for k, v in strategy.items())
            strategy_text = f"\nYour current winning strategy:\n{strategy_items}\n"

        # Experiment hint for this shift
        hypothesis = experiment.get("hypothesis", "")
        variant = experiment.get("strategy_variant", {})
        experiment_text = ""
        if hypothesis and hypothesis != f"Shift experiment for {emp.name}":
            experiment_text = f"\nThis shift, experiment with: {hypothesis}\n"
        if variant:
            variant_items = ", ".join(f"{k}={v}" for k, v in variant.items()
                                      if k != "shift_date")
            if variant_items:
                experiment_text += f"Try adjusting: {variant_items}\n"

        prompt = f"""Today is {today}.

You are {emp.name.replace('_', ' ').title()}, {emp.role}.

Your goal: {emp.goal}

Your KPIs (what success looks like):
{kpi_block}
{strategy_text}{experiment_text}
Now go do your work for today's shift. Be proactive. Take real action.

At the end of your shift, report back with a brief, human-readable summary like:
"Today I sent 15 outreach emails, got 3 replies (20% rate). Wrote 2 blog posts,
 published 1. Identified 5 new leads. Tomorrow I'll focus on the warm replies."

Report NUMBERS wherever possible — that's what makes your KPIs measurable.
"""
        return prompt.strip()

    async def _run_as_agent(self, prompt: str) -> str:
        """Run the employee as an AIAgent and return their shift output.

        Uses the employee's toolsets if defined, otherwise uses a default set.
        Runs the synchronous AIAgent.run_conversation() in an executor to avoid
        blocking the event loop.
        """
        import asyncio
        from run_agent import AIAgent

        model = os.getenv("HERMES_MODEL", "claude-haiku-4-5-20251001")
        api_key = os.getenv("ANTHROPIC_TOKEN") or os.getenv("ANTHROPIC_API_KEY")

        # Build a concise system prompt that positions the employee
        emp = self.employee
        system_prompt = (
            f"You are {emp.name.replace('_', ' ').title()}, a {emp.role} at this company. "
            f"Your goal: {emp.goal}. "
            "You work autonomously and report results in plain language. "
            "Always lead with numbers and outcomes, not process."
        )

        # Employee toolsets — use what's in their profile, fall back to safe defaults
        employee_toolsets: list[str] = getattr(emp, "toolsets", None) or []
        enabled_toolsets = employee_toolsets if employee_toolsets else None

        agent = AIAgent(
            model=model,
            api_key=api_key,
            ephemeral_system_prompt=system_prompt,
            enabled_toolsets=enabled_toolsets,
            quiet_mode=True,
            skip_memory=True,
            skip_context_files=True,
        )

        # run_conversation is synchronous; run in executor to not block async loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: agent.run_conversation(prompt),
        )

        # Extract the text response
        if isinstance(result, dict):
            return result.get("response", result.get("content", str(result)))
        return str(result)

    async def _report_to_team(self, result: str) -> None:
        """Post a human-friendly shift summary to the team chat feed.

        Summarises the agent output to a single message — employees should
        feel like real workers posting to a group chat, not log files.
        """
        from gateway.team_chat import post_update

        emp = self.employee

        # Trim to a reasonable chat message length
        message = result.strip()
        if len(message) > 500:
            # Keep the last paragraph which usually has the summary
            paragraphs = [p.strip() for p in message.split("\n\n") if p.strip()]
            message = paragraphs[-1] if paragraphs else message[:500]

        if not message:
            message = "Completed my shift — no notable output to report."

        try:
            post_update(
                employee_name=emp.name,
                role=emp.role,
                message=message,
                channel="team",
            )
            logger.info("[team_chat] %s posted shift update", emp.name)
        except Exception as exc:
            logger.warning("team_chat.post_update failed for %s: %s", emp.name, exc)

    def _extract_metrics(self, result: str) -> dict:
        """Parse agent output for KPI-relevant numeric metrics.

        Looks for natural-language numbers like "sent 12 emails", "3 replies",
        "20% open rate", "5 new leads" — and converts them to a metrics dict.

        Returns a dict suitable for ExperimentLoop.record_result().
        """
        if not result:
            return {}

        metrics: dict = {}
        text = result.lower()

        # Generic number extraction patterns — covers most business KPIs
        patterns = [
            # "sent 12 emails" / "sent 12 cold emails" / "12 emails sent"
            (r"sent\s+(\d+(?:\.\d+)?)\s+(?:\w+\s+)?emails?", "emails_sent"),
            (r"(\d+(?:\.\d+)?)\s+(?:\w+\s+)?emails?\s+sent", "emails_sent"),
            # "3 replies" / "got 3 replies" / "received 3 replies"
            (r"(?:got|received|got back)\s+(\d+(?:\.\d+)?)\s+repl(?:y|ies)", "replies"),
            (r"(\d+(?:\.\d+)?)\s+repl(?:y|ies)", "replies"),
            # "20% open rate" / "open rate of 20%"
            (r"(\d+(?:\.\d+)?)\s*%\s+open\s+rate", "open_rate_pct"),
            (r"open\s+rate\s+(?:of\s+)?(\d+(?:\.\d+)?)\s*%", "open_rate_pct"),
            # "reply rate" / "conversion rate"
            (r"(\d+(?:\.\d+)?)\s*%\s+reply\s+rate", "reply_rate_pct"),
            (r"reply\s+rate\s+(?:of\s+)?(\d+(?:\.\d+)?)\s*%", "reply_rate_pct"),
            (r"(\d+(?:\.\d+)?)\s*%\s+conversion", "conversion_rate_pct"),
            # "5 new leads" / "identified 5 leads"
            (r"(\d+(?:\.\d+)?)\s+new\s+leads?", "leads"),
            (r"identified\s+(\d+(?:\.\d+)?)\s+leads?", "leads"),
            (r"(\d+(?:\.\d+)?)\s+leads?\s+(?:identified|found|generated)", "leads"),
            # "wrote 2 blog posts" / "published 1 article"
            (r"wrote\s+(\d+(?:\.\d+)?)\s+(?:blog\s+posts?|articles?|posts?)", "posts_written"),
            (r"published\s+(\d+(?:\.\d+)?)\s+(?:blog\s+posts?|articles?|posts?)", "posts_published"),
            # "made 8 calls" / "8 phone calls"
            (r"made\s+(\d+(?:\.\d+)?)\s+calls?", "calls_made"),
            (r"(\d+(?:\.\d+)?)\s+(?:phone\s+)?calls?\s+made", "calls_made"),
            # "booked 2 meetings" / "2 demos scheduled"
            (r"booked\s+(\d+(?:\.\d+)?)\s+meetings?", "meetings_booked"),
            (r"(\d+(?:\.\d+)?)\s+(?:meetings?|demos?)\s+(?:booked|scheduled)", "meetings_booked"),
            # Revenue / deals
            (r"\$(\d+(?:,\d{3})*(?:\.\d+)?)\s+(?:in\s+)?(?:revenue|arr|mrr|sales)", "revenue_usd"),
            (r"(\d+(?:\.\d+)?)\s+deals?\s+(?:closed|won)", "deals_closed"),
            # Generic "completed X tasks"
            (r"completed\s+(\d+(?:\.\d+)?)\s+tasks?", "tasks_completed"),
        ]

        for pattern, key in patterns:
            match = re.search(pattern, text)
            if match and key not in metrics:
                raw = match.group(1).replace(",", "")
                try:
                    metrics[key] = float(raw)
                except ValueError:
                    pass

        # Derived: reply rate if we have both emails and replies
        if "emails_sent" in metrics and "replies" in metrics and metrics["emails_sent"] > 0:
            metrics.setdefault(
                "reply_rate_pct",
                round(metrics["replies"] / metrics["emails_sent"] * 100, 1),
            )

        return metrics
