"""Tests for harness.onboard_pipeline.

Covers the happy path and error/partial-failure cases using mocks so
that no real network calls, LLM calls, or cron changes are made.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_PROFILE = {
    "business_name": "Acme Corp",
    "website_url": "https://acme.example.com",
    "industry": "saas",
    "description": "SaaS platform for widgets",
    "services": ["Widget API", "Dashboard"],
    "target_customer": "SMBs",
    "tone": "professional",
    "competitors": [],
    "team_size_estimate": "small",
    "social_media": {},
    "contact_info": {},
    "pain_points": ["user onboarding", "retention"],
}

FAKE_TEAM_RESULT = {
    "business_name": "Acme Corp",
    "employee_count": 3,
    "employees": [
        {"name": "alex_support", "role": "Customer Support", "status": "idle"},
        {"name": "jordan_sales", "role": "Sales Agent", "status": "idle"},
        {"name": "henry", "role": "Project Manager", "status": "idle"},
    ],
    "henry_included": True,
    "summary": "Provisioned 3 employees for Acme Corp.",
}

FAKE_VAPI_RESULT = {
    "status": "success",
    "message": "Provisioned Vapi assistant asst_abc123",
    "assistant_id": "asst_abc123",
    "phone_number": "+15550001234",
}


# ---------------------------------------------------------------------------
# Helper to run async tests
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Tests: happy path
# ---------------------------------------------------------------------------

class TestRunOnboardingHappyPath:
    @patch("harness.onboard_pipeline._step_install_crons")
    @patch("harness.onboard_pipeline._step_write_welcome_message")
    @patch("harness.onboard_pipeline._step_provision_vapi", new_callable=AsyncMock)
    @patch("harness.onboard_pipeline._step_create_henry")
    @patch("harness.onboard_pipeline._step_provision_team", new_callable=AsyncMock)
    @patch("harness.onboard_pipeline._step_analyze_website", new_callable=AsyncMock)
    def test_full_success(
        self,
        mock_analyze,
        mock_provision_team,
        mock_create_henry,
        mock_provision_vapi,
        mock_welcome,
        mock_crons,
        tmp_path,
    ):
        """Happy path: all steps succeed → status=success."""
        profile_path = tmp_path / "business_profile.json"
        profile_path.write_text(json.dumps(FAKE_PROFILE))

        mock_analyze.return_value = (FAKE_PROFILE, profile_path)
        mock_provision_team.return_value = FAKE_TEAM_RESULT
        mock_create_henry.return_value = {"name": "henry", "role": "Project Manager", "status": "idle"}
        mock_provision_vapi.return_value = FAKE_VAPI_RESULT
        mock_crons.return_value = ["Morning digest (8am)", "Henry shifts (9am + 5pm)", "Proactive loop (every 15min)"]
        mock_welcome.return_value = None

        from harness.onboard_pipeline import run_onboarding

        result = _run(run_onboarding(
            website_url="https://acme.example.com",
            user_contact="@owner",
        ))

        assert result["status"] == "success"
        assert result["business_name"] == "Acme Corp"
        assert result["team_size"] == 3
        assert result["vapi_assistant_id"] == "asst_abc123"
        assert len(result["crons_installed"]) == 3
        assert result["errors"] == []

    @patch("harness.onboard_pipeline._step_install_crons")
    @patch("harness.onboard_pipeline._step_write_welcome_message")
    @patch("harness.onboard_pipeline._step_provision_vapi", new_callable=AsyncMock)
    @patch("harness.onboard_pipeline._step_create_henry")
    @patch("harness.onboard_pipeline._step_provision_team", new_callable=AsyncMock)
    @patch("harness.onboard_pipeline._step_analyze_website", new_callable=AsyncMock)
    def test_employees_includes_henry(
        self,
        mock_analyze,
        mock_provision_team,
        mock_create_henry,
        mock_provision_vapi,
        mock_welcome,
        mock_crons,
        tmp_path,
    ):
        """Henry is always in the employees list (not duplicated)."""
        profile_path = tmp_path / "business_profile.json"
        profile_path.write_text(json.dumps(FAKE_PROFILE))

        mock_analyze.return_value = (FAKE_PROFILE, profile_path)
        mock_provision_team.return_value = FAKE_TEAM_RESULT  # already includes henry
        mock_create_henry.return_value = {"name": "henry", "role": "Project Manager", "status": "idle"}
        mock_provision_vapi.return_value = FAKE_VAPI_RESULT
        mock_crons.return_value = []
        mock_welcome.return_value = None

        from harness.onboard_pipeline import run_onboarding

        result = _run(run_onboarding("https://acme.example.com", "@owner"))
        henry_entries = [e for e in result["employees"] if e["name"] == "henry"]
        assert len(henry_entries) == 1, "Henry should appear exactly once"


# ---------------------------------------------------------------------------
# Tests: error/partial-failure cases
# ---------------------------------------------------------------------------

class TestRunOnboardingErrorCases:
    @patch("harness.onboard_pipeline._step_analyze_website", new_callable=AsyncMock)
    def test_website_analysis_failure_returns_error(self, mock_analyze):
        """If website analysis fails, status=error and pipeline aborts."""
        mock_analyze.side_effect = RuntimeError("Network timeout")

        from harness.onboard_pipeline import run_onboarding

        result = _run(run_onboarding("https://broken.example.com", "@owner"))

        assert result["status"] == "error"
        assert any("Website analysis failed" in e for e in result["errors"])
        assert result["business_name"] == "Unknown"

    @patch("harness.onboard_pipeline._step_install_crons")
    @patch("harness.onboard_pipeline._step_write_welcome_message")
    @patch("harness.onboard_pipeline._step_provision_vapi", new_callable=AsyncMock)
    @patch("harness.onboard_pipeline._step_create_henry")
    @patch("harness.onboard_pipeline._step_provision_team", new_callable=AsyncMock)
    @patch("harness.onboard_pipeline._step_analyze_website", new_callable=AsyncMock)
    def test_vapi_failure_is_partial(
        self,
        mock_analyze,
        mock_provision_team,
        mock_create_henry,
        mock_provision_vapi,
        mock_welcome,
        mock_crons,
        tmp_path,
    ):
        """Vapi failure → status=partial, team is still provisioned."""
        profile_path = tmp_path / "business_profile.json"
        profile_path.write_text(json.dumps(FAKE_PROFILE))

        mock_analyze.return_value = (FAKE_PROFILE, profile_path)
        mock_provision_team.return_value = FAKE_TEAM_RESULT
        mock_create_henry.return_value = {"name": "henry", "role": "Project Manager", "status": "idle"}
        mock_provision_vapi.side_effect = RuntimeError("VAPI_API_KEY not set")
        mock_crons.return_value = ["Morning digest (8am)"]
        mock_welcome.return_value = None

        from harness.onboard_pipeline import run_onboarding

        result = _run(run_onboarding("https://acme.example.com", "@owner"))

        assert result["status"] == "partial"
        assert result["vapi_assistant_id"] is None
        assert result["team_size"] == 3
        assert any("Vapi" in e for e in result["errors"])

    @patch("harness.onboard_pipeline._step_install_crons")
    @patch("harness.onboard_pipeline._step_write_welcome_message")
    @patch("harness.onboard_pipeline._step_provision_vapi", new_callable=AsyncMock)
    @patch("harness.onboard_pipeline._step_create_henry")
    @patch("harness.onboard_pipeline._step_provision_team", new_callable=AsyncMock)
    @patch("harness.onboard_pipeline._step_analyze_website", new_callable=AsyncMock)
    def test_team_provision_failure_is_partial(
        self,
        mock_analyze,
        mock_provision_team,
        mock_create_henry,
        mock_provision_vapi,
        mock_welcome,
        mock_crons,
        tmp_path,
    ):
        """Team provisioning failure → status=partial, Vapi still attempted."""
        profile_path = tmp_path / "business_profile.json"
        profile_path.write_text(json.dumps(FAKE_PROFILE))

        mock_analyze.return_value = (FAKE_PROFILE, profile_path)
        mock_provision_team.side_effect = RuntimeError("GLM_API_KEY not set")
        mock_create_henry.return_value = {"name": "henry", "role": "Project Manager", "status": "idle"}
        mock_provision_vapi.return_value = FAKE_VAPI_RESULT
        mock_crons.return_value = []
        mock_welcome.return_value = None

        from harness.onboard_pipeline import run_onboarding

        result = _run(run_onboarding("https://acme.example.com", "@owner"))

        assert result["status"] == "partial"
        # Henry was still created by _step_create_henry
        assert any(e["name"] == "henry" for e in result["employees"])
        assert any("Team provisioning failed" in e for e in result["errors"])

    @patch("harness.onboard_pipeline._step_install_crons")
    @patch("harness.onboard_pipeline._step_write_welcome_message")
    @patch("harness.onboard_pipeline._step_provision_vapi", new_callable=AsyncMock)
    @patch("harness.onboard_pipeline._step_create_henry")
    @patch("harness.onboard_pipeline._step_provision_team", new_callable=AsyncMock)
    @patch("harness.onboard_pipeline._step_analyze_website", new_callable=AsyncMock)
    def test_cron_failure_is_partial(
        self,
        mock_analyze,
        mock_provision_team,
        mock_create_henry,
        mock_provision_vapi,
        mock_welcome,
        mock_crons,
        tmp_path,
    ):
        """Cron installation failure → status=partial but team and Vapi are ok."""
        profile_path = tmp_path / "business_profile.json"
        profile_path.write_text(json.dumps(FAKE_PROFILE))

        mock_analyze.return_value = (FAKE_PROFILE, profile_path)
        mock_provision_team.return_value = FAKE_TEAM_RESULT
        mock_create_henry.return_value = {"name": "henry", "role": "Project Manager", "status": "idle"}
        mock_provision_vapi.return_value = FAKE_VAPI_RESULT
        mock_crons.side_effect = PermissionError("crontab not available")
        mock_welcome.return_value = None

        from harness.onboard_pipeline import run_onboarding

        result = _run(run_onboarding("https://acme.example.com", "@owner"))

        assert result["status"] == "partial"
        assert result["vapi_assistant_id"] == "asst_abc123"
        assert result["crons_installed"] == []
        assert any("Cron" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# Tests: step-level unit tests
# ---------------------------------------------------------------------------

class TestInstallCronEntry:
    def test_new_entry_added(self):
        """A new cron entry is written to crontab."""
        from harness.onboard_pipeline import _install_cron_entry

        with patch("subprocess.run") as mock_sub:
            # First call: crontab -l returns empty
            mock_sub.side_effect = [
                MagicMock(returncode=0, stdout=""),  # crontab -l
                MagicMock(returncode=0, stdout=""),  # crontab -
            ]
            result = _install_cron_entry("0 8 * * *", "/usr/bin/python3 /some/script.py")
            assert result is True

    def test_duplicate_entry_skipped(self):
        """An already-present cron entry is not duplicated."""
        from harness.onboard_pipeline import _install_cron_entry

        existing = "0 8 * * * /usr/bin/python3 /some/script.py\n"
        with patch("subprocess.run") as mock_sub:
            mock_sub.return_value = MagicMock(returncode=0, stdout=existing)
            result = _install_cron_entry("0 8 * * *", "/usr/bin/python3 /some/script.py")
            assert result is True
            # crontab - should NOT have been called (only crontab -l)
            assert mock_sub.call_count == 1

    def test_subprocess_error_returns_false(self):
        """If crontab write fails, _install_cron_entry returns False."""
        from harness.onboard_pipeline import _install_cron_entry

        with patch("subprocess.run") as mock_sub:
            mock_sub.side_effect = [
                MagicMock(returncode=0, stdout=""),     # crontab -l
                MagicMock(returncode=1, stderr="Permission denied"),  # crontab -
            ]
            result = _install_cron_entry("0 8 * * *", "/some/script.py")
            assert result is False


class TestWriteWelcomeMessage:
    def test_welcome_message_written(self, tmp_path):
        """Welcome message is appended to team_updates.jsonl."""
        updates_path = tmp_path / "team_updates.jsonl"

        with patch("harness.onboard_pipeline.HERMES_DIR", tmp_path):
            from harness.onboard_pipeline import _step_write_welcome_message
            _step_write_welcome_message("Acme Corp", 4)

        assert updates_path.exists()
        entry = json.loads(updates_path.read_text().strip())
        assert entry["employee"] == "henry"
        assert "Acme Corp" in entry["message"]
        assert "4" in entry["message"]
