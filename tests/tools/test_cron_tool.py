"""Tests for cron scheduling tools."""
import json
import os
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def temp_tasks_file(tmp_path):
    tasks_file = str(tmp_path / "scheduled_tasks.json")
    with patch("tools.cron_tool.TASKS_FILE", tasks_file):
        yield tasks_file


from tools.cron_tool import cron_create, cron_delete, cron_list


def test_cron_create_returns_task_id():
    result = json.loads(cron_create("check pipeline", "daily"))
    assert result["success"] is True
    assert "task_id" in result
    assert len(result["task_id"]) == 8


def test_cron_create_natural_language_daily():
    result = json.loads(cron_create("morning standup", "daily"))
    assert result["schedule"] == "0 9 * * *"


def test_cron_create_natural_language_hourly():
    result = json.loads(cron_create("check email", "hourly"))
    assert result["schedule"] == "0 * * * *"


def test_cron_create_raw_cron_expression():
    result = json.loads(cron_create("weekly report", "0 8 * * 1"))
    assert result["schedule"] == "0 8 * * 1"


def test_cron_list_returns_created_tasks():
    cron_create("task 1", "daily", label="Task One")
    cron_create("task 2", "weekly")
    result = json.loads(cron_list())
    assert result["count"] == 2
    assert result["tasks"][0]["label"] == "Task One"


def test_cron_delete_removes_task():
    r = json.loads(cron_create("to delete", "daily"))
    task_id = r["task_id"]
    del_result = json.loads(cron_delete(task_id))
    assert del_result["success"] is True
    list_result = json.loads(cron_list())
    assert list_result["count"] == 0


def test_cron_delete_nonexistent_returns_error():
    result = json.loads(cron_delete("nonexistent-id"))
    assert result["success"] is False
    assert "not found" in result["error"]


def test_cron_list_empty():
    result = json.loads(cron_list())
    assert result["count"] == 0
    assert result["tasks"] == []
