"""Experiment Loop — Karpathy autoresearch pattern for employee strategies.

Employees don't just execute; they EXPERIMENT.  Each employee maintains a
strategy file (~/.hermes/experiments/{employee_name}.jsonl) that tracks:

    hypothesis → action → metric_before → metric_after → kept/discarded

The loop:
    1. Employee picks a strategy variant (e.g. different email subject lines,
       different outreach timing, different content angles)
    2. Runs it for a fixed window (1 shift = 1 experiment)
    3. Measures the KPI delta (reply rate, open rate, leads generated, etc.)
    4. If improved → keep the strategy, update the employee's playbook
    5. If worse → discard, revert to previous best
    6. Log everything for Henry's morning review

This is what makes Hermes learn without babysitting.  Over days and weeks,
each employee converges on what actually works for THIS specific business.

Usage
-----
    loop = ExperimentLoop(employee_name="alex_outreach")
    experiment = loop.propose_experiment()
    # ... employee runs shift with this strategy ...
    loop.record_result(experiment["id"], metrics={"reply_rate": 0.35})
    loop.evaluate_and_decide(experiment["id"])
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_EXPERIMENTS_DIR = Path.home() / ".hermes" / "experiments"
_PLAYBOOK_DIR = Path.home() / ".hermes" / "playbooks"


class ExperimentLoop:
    """Autoresearch-style experiment engine for employee strategies.

    Each employee gets their own experiment log and playbook.  The playbook
    is the current "best known strategy" — the experiment loop proposes
    variations, measures results, and updates the playbook when something
    works better.
    """

    def __init__(self, employee_name: str = "all") -> None:
        self.employee_name = employee_name
        _EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
        _PLAYBOOK_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def _log_path(self) -> Path:
        return _EXPERIMENTS_DIR / f"{self.employee_name}.jsonl"

    @property
    def _playbook_path(self) -> Path:
        return _PLAYBOOK_DIR / f"{self.employee_name}.json"

    # ── Playbook (current best strategy) ─────────────────────────────

    def load_playbook(self) -> dict:
        """Load the employee's current best strategy playbook."""
        if self._playbook_path.exists():
            try:
                return json.loads(self._playbook_path.read_text())
            except Exception:
                pass
        return {
            "employee": self.employee_name,
            "version": 0,
            "strategy": {},
            "baseline_metrics": {},
            "updated_at": None,
        }

    def save_playbook(self, playbook: dict) -> None:
        """Persist the playbook to disk."""
        playbook["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._playbook_path.write_text(json.dumps(playbook, indent=2))

    # ── Experiment proposal ──────────────────────────────────────────

    def propose_experiment(self, hypothesis: str = "", strategy_variant: dict = None) -> dict:
        """Create a new experiment to test a strategy variation.

        Parameters
        ----------
        hypothesis       : What we think will happen (e.g. "shorter subject
                           lines will increase open rates").
        strategy_variant : The specific changes to try (e.g. {"subject_style":
                           "short", "send_time": "7am"}).

        Returns
        -------
        Experiment dict with id, hypothesis, variant, status="running".
        """
        playbook = self.load_playbook()

        experiment = {
            "id": f"exp-{uuid.uuid4().hex[:8]}",
            "employee": self.employee_name,
            "hypothesis": hypothesis,
            "strategy_variant": strategy_variant or {},
            "baseline_strategy": playbook.get("strategy", {}),
            "baseline_metrics": playbook.get("baseline_metrics", {}),
            "result_metrics": {},
            "status": "running",  # running | improved | declined | neutral
            "decision": None,     # kept | discarded
            "created_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
        }

        self._append_log(experiment)
        logger.info(
            "Experiment %s proposed for %s: %s",
            experiment["id"], self.employee_name, hypothesis or "strategy variant test"
        )
        return experiment

    def propose_with_llm(self, employee_goal: str, kpis: list[str],
                         history: list[dict] = None) -> dict:
        """Use the LLM to propose the next experiment based on past results.

        This is the smart part — the LLM looks at what's been tried, what
        worked, what didn't, and proposes the next thing to try.
        """
        history = history or self.load_experiment_history()

        # Build a prompt for the LLM
        past_summary = ""
        for exp in history[-10:]:  # last 10 experiments
            status = exp.get("status", "unknown")
            hyp = exp.get("hypothesis", "")
            variant = json.dumps(exp.get("strategy_variant", {}))
            metrics = json.dumps(exp.get("result_metrics", {}))
            past_summary += f"  - [{status}] {hyp} | variant={variant} | result={metrics}\n"

        if not past_summary:
            past_summary = "  No experiments run yet — this is the first one.\n"

        prompt = f"""You are an experiment designer for an AI employee.

Employee goal: {employee_goal}
KPIs: {', '.join(kpis)}

Past experiments:
{past_summary}

Based on what's been tried and what worked/didn't, propose the NEXT experiment.
Think like a growth hacker — what's the highest-leverage thing to test next?

Respond in JSON:
{{
    "hypothesis": "what you think will happen",
    "strategy_variant": {{"key": "value pairs of what to change"}},
    "reasoning": "why this is the best next experiment"
}}"""

        try:
            import httpx

            api_key = os.environ.get("GLM_API_KEY", "")
            base_url = os.environ.get("GLM_BASE_URL", "https://api.z.ai/api/paas/v4")
            model = os.environ.get("GLM_MODEL", "glm-4.5-flash")

            if not api_key:
                logger.warning("No GLM_API_KEY — using random experiment proposal")
                return self.propose_experiment(
                    hypothesis="baseline test — measure current performance",
                    strategy_variant={"mode": "baseline"},
                )

            resp = httpx.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                },
                timeout=30,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]

            # Parse JSON from response (handle markdown code blocks)
            if "```" in content:
                content = content.split("```json")[-1].split("```")[0]
            proposal = json.loads(content.strip())

            return self.propose_experiment(
                hypothesis=proposal.get("hypothesis", "LLM-proposed experiment"),
                strategy_variant=proposal.get("strategy_variant", {}),
            )

        except Exception as exc:
            logger.warning("LLM experiment proposal failed: %s — using baseline", exc)
            return self.propose_experiment(
                hypothesis="baseline measurement",
                strategy_variant={"mode": "baseline"},
            )

    # ── Recording results ────────────────────────────────────────────

    def record_result(self, experiment_id: str, metrics: dict) -> None:
        """Record the outcome metrics for a running experiment.

        Parameters
        ----------
        experiment_id : The experiment ID from propose_experiment().
        metrics       : KPI measurements (e.g. {"reply_rate": 0.35, "leads": 12}).
        """
        experiments = self.load_experiment_history()
        for exp in experiments:
            if exp["id"] == experiment_id:
                exp["result_metrics"] = metrics
                exp["completed_at"] = datetime.now(timezone.utc).isoformat()
                break

        # Rewrite the log
        self._rewrite_log(experiments)
        logger.info("Recorded results for %s: %s", experiment_id, metrics)

    def evaluate_and_decide(self, experiment_id: str) -> str:
        """Compare experiment results to baseline and decide: keep or discard.

        Returns "kept" or "discarded".
        """
        experiments = self.load_experiment_history()
        exp = next((e for e in experiments if e["id"] == experiment_id), None)

        if not exp:
            logger.warning("Experiment %s not found", experiment_id)
            return "not_found"

        baseline = exp.get("baseline_metrics", {})
        result = exp.get("result_metrics", {})

        if not result:
            exp["status"] = "neutral"
            exp["decision"] = "discarded"
            self._rewrite_log(experiments)
            return "discarded"

        # Compare: count how many metrics improved vs declined
        improved = 0
        declined = 0
        for key in result:
            if key in baseline:
                try:
                    if float(result[key]) > float(baseline[key]):
                        improved += 1
                    elif float(result[key]) < float(baseline[key]):
                        declined += 1
                except (ValueError, TypeError):
                    pass

        # Decision: if net positive (or first experiment), keep it
        if improved > declined or not baseline:
            exp["status"] = "improved"
            exp["decision"] = "kept"

            # Update the playbook with the winning strategy
            playbook = self.load_playbook()
            playbook["version"] = playbook.get("version", 0) + 1
            playbook["strategy"].update(exp.get("strategy_variant", {}))
            playbook["baseline_metrics"] = result
            playbook["last_experiment"] = experiment_id
            self.save_playbook(playbook)

            logger.info("Experiment %s KEPT — strategy updated (v%d)", experiment_id, playbook["version"])
            decision = "kept"
        elif improved == declined:
            exp["status"] = "neutral"
            exp["decision"] = "discarded"
            logger.info("Experiment %s NEUTRAL — no change, discarding", experiment_id)
            decision = "discarded"
        else:
            exp["status"] = "declined"
            exp["decision"] = "discarded"
            logger.info("Experiment %s DISCARDED — metrics declined", experiment_id)
            decision = "discarded"

        self._rewrite_log(experiments)
        return decision

    # ── Batch operations (for Henry's morning review) ────────────────

    def apply_overnight_results(self) -> list[dict]:
        """Review all completed-but-undecided experiments and apply decisions.

        Called by Henry during morning briefing to process overnight results.
        Returns list of decisions made.
        """
        experiments = self.load_experiment_history()
        decisions = []

        for exp in experiments:
            if exp.get("completed_at") and not exp.get("decision"):
                decision = self.evaluate_and_decide(exp["id"])
                decisions.append({
                    "experiment": exp["id"],
                    "employee": exp.get("employee"),
                    "hypothesis": exp.get("hypothesis"),
                    "decision": decision,
                })

        return decisions

    def get_win_rate(self) -> dict:
        """Calculate the experiment win rate for this employee."""
        experiments = self.load_experiment_history()
        total = len([e for e in experiments if e.get("decision")])
        kept = len([e for e in experiments if e.get("decision") == "kept"])
        discarded = len([e for e in experiments if e.get("decision") == "discarded"])

        return {
            "employee": self.employee_name,
            "total_experiments": total,
            "kept": kept,
            "discarded": discarded,
            "win_rate": kept / total if total > 0 else 0.0,
        }

    def summarize_for_henry(self) -> str:
        """Human-readable summary of recent experiments for Henry's digest."""
        experiments = self.load_experiment_history()
        recent = [e for e in experiments if e.get("decision")][-5:]

        if not recent:
            return f"{self.employee_name}: No experiments run yet."

        stats = self.get_win_rate()
        lines = [
            f"{self.employee_name}: {stats['total_experiments']} experiments, "
            f"{stats['win_rate']:.0%} win rate"
        ]
        for exp in recent:
            status_icon = "✅" if exp["decision"] == "kept" else "❌"
            lines.append(f"  {status_icon} {exp.get('hypothesis', 'N/A')[:60]}")

        return "\n".join(lines)

    # ── Log persistence ──────────────────────────────────────────────

    def load_experiment_history(self) -> list[dict]:
        """Load all experiments from the JSONL log."""
        if not self._log_path.exists():
            return []
        experiments = []
        for line in self._log_path.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    experiments.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return experiments

    def _append_log(self, entry: dict) -> None:
        """Append one experiment entry to the log."""
        with open(self._log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def _rewrite_log(self, experiments: list[dict]) -> None:
        """Rewrite the entire experiment log (after updates)."""
        with open(self._log_path, "w") as f:
            for exp in experiments:
                f.write(json.dumps(exp) + "\n")


def integrate_with_employee_shift(employee_name: str, employee_goal: str,
                                   kpis: list[str]) -> dict:
    """Hook called at the START of an employee shift to set up an experiment.

    Returns the experiment dict so the employee's session orchestrator
    can include the strategy variant in its system prompt.
    """
    loop = ExperimentLoop(employee_name)

    # Use LLM to propose smart experiment based on history
    experiment = loop.propose_with_llm(employee_goal, kpis)

    return experiment


def finalize_employee_shift(employee_name: str, experiment_id: str,
                             metrics: dict) -> str:
    """Hook called at the END of an employee shift to record and evaluate.

    Returns "kept" or "discarded".
    """
    loop = ExperimentLoop(employee_name)
    loop.record_result(experiment_id, metrics)
    return loop.evaluate_and_decide(experiment_id)
