# tests/test_harness/test_cli_commands.py
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from harness.cli_commands import (
    cmd_harness_run,
    cmd_employee_create,
    cmd_employee_status,
)


def test_cmd_harness_run_missing_spec(tmp_path, capsys):
    rc = cmd_harness_run(spec_file=str(tmp_path / "missing.yaml"))
    assert rc != 0
    captured = capsys.readouterr()
    assert "not found" in captured.out.lower() or "error" in captured.out.lower()


def test_cmd_harness_run_valid_spec(tmp_path):
    spec = tmp_path / "spec.yaml"
    spec.write_text(f"""
project_dir: {tmp_path}
task_spec: Build a hello world script
max_sessions: 1
""")
    with patch("harness.cli_commands.SessionOrchestrator") as MockOrch:
        instance = MagicMock()
        instance.run_harness.return_value = {"status": "completed", "sessions_run": 1,
                                             "total_cost_usd": 0.0, "message": "done"}
        MockOrch.return_value = instance
        rc = cmd_harness_run(spec_file=str(spec))
    assert rc == 0


def test_cmd_employee_create(tmp_path, capsys):
    rc = cmd_employee_create(
        name="ada",
        role="backend engineer",
        goal="Build auth API",
        employees_dir=tmp_path,
    )
    assert rc == 0
    assert (tmp_path / "ada.yaml").exists()


def test_cmd_employee_status_empty(tmp_path, capsys):
    rc = cmd_employee_status(employees_dir=tmp_path)
    captured = capsys.readouterr()
    assert rc == 0
    assert "no employees" in captured.out.lower() or captured.out.strip() != ""
