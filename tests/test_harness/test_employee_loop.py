# tests/test_harness/test_employee_loop.py
"""Tests for EmployeeLoop — autonomous shift runner."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from harness.employee import Employee
from harness.employee_loop import EmployeeLoop


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def tmp_employee(tmp_path) -> Employee:
    """Create a temporary employee config on disk and return it."""
    emp = Employee(
        name="alex_outreach",
        role="Sales Development Representative",
        goal="Generate qualified leads for our SaaS product",
        kpis=[
            "Send 20+ cold emails per day",
            "Maintain reply rate above 15%",
            "Book 2 demos per week",
        ],
        employees_dir=tmp_path,
    )
    emp.save()
    return emp


@pytest.fixture
def employee_loop(tmp_employee, tmp_path) -> EmployeeLoop:
    """EmployeeLoop backed by the tmp_employee fixture."""
    loop = EmployeeLoop.__new__(EmployeeLoop)
    loop.employee_name = tmp_employee.name
    loop.employee = tmp_employee
    from harness.experiment_loop import ExperimentLoop
    loop.experiment_loop = ExperimentLoop(tmp_employee.name)
    return loop


# ── _extract_metrics tests ────────────────────────────────────────────


class TestExtractMetrics:
    def test_extracts_emails_sent(self, employee_loop):
        output = "Today I sent 25 emails and got 4 replies (16% reply rate)."
        metrics = employee_loop._extract_metrics(output)
        assert metrics["emails_sent"] == 25.0

    def test_extracts_replies(self, employee_loop):
        output = "Sent 10 emails, received 3 replies."
        metrics = employee_loop._extract_metrics(output)
        assert metrics["replies"] == 3.0

    def test_derives_reply_rate(self, employee_loop):
        output = "Sent 20 emails and got 4 replies."
        metrics = employee_loop._extract_metrics(output)
        # Derived reply rate = 4/20 * 100 = 20.0
        assert metrics.get("reply_rate_pct") == pytest.approx(20.0)

    def test_extracts_leads(self, employee_loop):
        output = "Identified 7 new leads from LinkedIn today."
        metrics = employee_loop._extract_metrics(output)
        assert metrics["leads"] == 7.0

    def test_extracts_meetings_booked(self, employee_loop):
        output = "Booked 3 meetings with decision makers this afternoon."
        metrics = employee_loop._extract_metrics(output)
        assert metrics["meetings_booked"] == 3.0

    def test_extracts_open_rate(self, employee_loop):
        output = "The campaign had a 35% open rate which is above our benchmark."
        metrics = employee_loop._extract_metrics(output)
        assert metrics["open_rate_pct"] == 35.0

    def test_empty_output_returns_empty(self, employee_loop):
        assert employee_loop._extract_metrics("") == {}

    def test_no_numbers_returns_empty(self, employee_loop):
        output = "Sent emails and got some replies."
        metrics = employee_loop._extract_metrics(output)
        # No numeric values → empty dict
        assert isinstance(metrics, dict)

    def test_extracts_blog_posts(self, employee_loop):
        output = "Wrote 2 blog posts and published 1 article today."
        metrics = employee_loop._extract_metrics(output)
        assert metrics.get("posts_written") == 2.0
        assert metrics.get("posts_published") == 1.0


# ── _build_shift_prompt tests ─────────────────────────────────────────


class TestBuildShiftPrompt:
    def test_includes_role_and_goal(self, employee_loop):
        experiment = {"id": "exp-abc", "hypothesis": "", "strategy_variant": {}}
        prompt = employee_loop._build_shift_prompt(experiment)
        assert "Sales Development Representative" in prompt
        assert "Generate qualified leads" in prompt

    def test_includes_kpis(self, employee_loop):
        experiment = {"id": "exp-abc", "hypothesis": "", "strategy_variant": {}}
        prompt = employee_loop._build_shift_prompt(experiment)
        assert "20+ cold emails" in prompt
        assert "reply rate above 15%" in prompt

    def test_includes_today_date(self, employee_loop):
        experiment = {"id": "exp-abc", "hypothesis": "", "strategy_variant": {}}
        prompt = employee_loop._build_shift_prompt(experiment)
        assert "Today is" in prompt

    def test_includes_hypothesis_when_set(self, employee_loop):
        experiment = {
            "id": "exp-abc",
            "hypothesis": "Shorter subject lines will increase open rates",
            "strategy_variant": {"subject_style": "short"},
        }
        prompt = employee_loop._build_shift_prompt(experiment)
        assert "Shorter subject lines" in prompt

    def test_prompts_for_numbers(self, employee_loop):
        experiment = {"id": "exp-abc", "hypothesis": "", "strategy_variant": {}}
        prompt = employee_loop._build_shift_prompt(experiment)
        assert "NUMBERS" in prompt or "numbers" in prompt.lower()


# ── _report_to_team tests ─────────────────────────────────────────────


class TestReportToTeam:
    def test_calls_post_update(self, employee_loop):
        with patch("gateway.team_chat.post_update") as mock_post:
            asyncio.run(employee_loop._report_to_team("Sent 10 emails, got 2 replies!"))
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args
            # Check employee name is passed somewhere in the call
            args = call_kwargs[1] if call_kwargs[1] else {}
            all_args = list(call_kwargs[0]) + list(args.values())
            assert any("alex_outreach" in str(a) for a in all_args)

    def test_trims_long_output(self, employee_loop):
        """Long outputs should be trimmed to a chat-friendly length."""
        long_output = "paragraph one\n\n" + ("x " * 300) + "\n\nFinal summary line."
        with patch("gateway.team_chat.post_update") as mock_post:
            asyncio.run(employee_loop._report_to_team(long_output))
            mock_post.assert_called_once()
            message_arg = mock_post.call_args[1].get("message", "")
            assert len(message_arg) <= 600  # within reasonable chat length

    def test_handles_post_update_failure_gracefully(self, employee_loop):
        """If team_chat is unavailable, _report_to_team should not raise."""
        with patch("gateway.team_chat.post_update", side_effect=RuntimeError("network error")):
            # Should not raise
            asyncio.run(employee_loop._report_to_team("Some result"))


# ── run_shift integration test ────────────────────────────────────────


class TestRunShift:
    def test_run_shift_calls_experiment_loop_methods(self, employee_loop, tmp_path):
        """run_shift should call propose_experiment, record_result, evaluate_and_decide."""
        fake_agent_output = (
            "Today I sent 18 cold emails and got 3 replies (17% reply rate). "
            "Identified 5 new leads on LinkedIn. Booked 1 meeting for Thursday."
        )

        with patch.object(
            employee_loop.experiment_loop, "propose_experiment",
            wraps=employee_loop.experiment_loop.propose_experiment,
        ) as mock_propose, \
        patch.object(
            employee_loop.experiment_loop, "record_result",
            wraps=employee_loop.experiment_loop.record_result,
        ) as mock_record, \
        patch.object(
            employee_loop.experiment_loop, "evaluate_and_decide",
            return_value="kept",
        ) as mock_evaluate, \
        patch.object(
            employee_loop, "_run_as_agent",
            new=AsyncMock(return_value=fake_agent_output),
        ), \
        patch("gateway.team_chat.post_update") as mock_post:

            result = asyncio.run(employee_loop.run_shift())

        # ExperimentLoop methods called
        mock_propose.assert_called_once()
        mock_record.assert_called_once()
        mock_evaluate.assert_called_once()

        # team_chat broadcast called
        mock_post.assert_called_once()

        # Result has the expected keys
        assert "employee" in result
        assert "shift_start" in result
        assert "shift_end" in result
        assert "metrics" in result
        assert "experiment_id" in result

        # Metrics extracted from the agent output
        assert result["metrics"].get("emails_sent") == 18.0
        assert result["metrics"].get("replies") == 3.0
        assert result["metrics"].get("leads") == 5.0

    def test_run_shift_handles_agent_failure(self, employee_loop):
        """If the agent raises, run_shift should still post to team_chat and return."""
        with patch.object(
            employee_loop, "_run_as_agent",
            new=AsyncMock(side_effect=RuntimeError("API timeout")),
        ), \
        patch("gateway.team_chat.post_update") as mock_post, \
        patch.object(
            employee_loop.experiment_loop, "evaluate_and_decide",
            return_value="discarded",
        ):
            result = asyncio.run(employee_loop.run_shift())

        # Should still return a result dict
        assert "employee" in result
        assert result["employee"] == "alex_outreach"
        # team_chat is still notified even on failure
        mock_post.assert_called_once()

    def test_run_shift_returns_experiment_id(self, employee_loop):
        """The returned dict must include the experiment_id used this shift."""
        with patch.object(
            employee_loop, "_run_as_agent",
            new=AsyncMock(return_value="Did some work."),
        ), \
        patch("gateway.team_chat.post_update"):
            result = asyncio.run(employee_loop.run_shift())

        assert result["experiment_id"].startswith("exp-")
