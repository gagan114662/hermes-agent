# tests/test_harness/test_employee.py
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from harness.employee import Employee


def test_employee_create_and_save(tmp_path):
    emp = Employee(
        name="ada",
        role="backend engineer",
        goal="Build a REST API for the user service",
        kpis=["All endpoints return 200", "Test coverage > 80%"],
        memory_scope="ada",
        employees_dir=tmp_path,
    )
    emp.save()
    config_file = tmp_path / "ada.yaml"
    assert config_file.exists()
    content = config_file.read_text()
    assert "ada" in content
    assert "backend engineer" in content


def test_employee_load_from_yaml(tmp_path):
    emp = Employee(
        name="bob",
        role="qa engineer",
        goal="Write tests for the auth module",
        kpis=[],
        employees_dir=tmp_path,
    )
    emp.save()
    loaded = Employee.load("bob", employees_dir=tmp_path)
    assert loaded.name == "bob"
    assert loaded.role == "qa engineer"
    assert loaded.goal == "Write tests for the auth module"


def test_employee_load_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        Employee.load("nonexistent", employees_dir=tmp_path)


def test_employee_default_status():
    emp = Employee(name="x", role="y", goal="z")
    assert emp.status == "idle"


def test_employee_to_harness_config(tmp_path):
    emp = Employee(
        name="ada",
        role="engineer",
        goal="Build REST API",
        kpis=["All tests pass"],
        employees_dir=tmp_path,
    )
    cfg = emp.to_harness_config(project_dir=tmp_path)
    assert cfg.task_spec == "Build REST API\n\nSuccess criteria:\n- All tests pass"
    assert cfg.project_dir == tmp_path


def test_employee_list_all(tmp_path):
    Employee(name="ada", role="eng", goal="X", employees_dir=tmp_path).save()
    Employee(name="bob", role="qa", goal="Y", employees_dir=tmp_path).save()
    employees = Employee.list_all(employees_dir=tmp_path)
    names = [e.name for e in employees]
    assert "ada" in names
    assert "bob" in names
