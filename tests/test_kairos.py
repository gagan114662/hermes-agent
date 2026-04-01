"""Tests for Kairos always-on autonomous agent mode."""
import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent.kairos import (
    KairosSettings,
    get_kairos_prompt_addendum,
    is_kairos_active,
    set_kairos_active,
    load_kairos_settings,
    CronExecutor,
    get_due_tasks,
    mark_task_fired,
)


@pytest.fixture(autouse=True)
def reset_kairos_state():
    yield
    set_kairos_active(False)


class TestKairosSettings:
    def test_load_from_json(self, tmp_path):
        settings_file = tmp_path / "settings.json"
        settings_file.write_text(json.dumps({"assistant": True, "assistantName": "Aria"}))
        s = load_kairos_settings(settings_path=str(settings_file))
        assert s.assistant is True
        assert s.assistant_name == "Aria"

    def test_defaults_when_missing(self, tmp_path):
        settings_file = tmp_path / "settings.json"
        s = load_kairos_settings(settings_path=str(settings_file))
        assert s.assistant is False
        assert s.assistant_name == "Assistant"

    def test_assistant_false_disables(self, tmp_path):
        settings_file = tmp_path / "settings.json"
        settings_file.write_text(json.dumps({"assistant": False}))
        s = load_kairos_settings(settings_path=str(settings_file))
        assert s.assistant is False


class TestKairosState:
    def test_set_and_get_active(self):
        set_kairos_active(True)
        assert is_kairos_active() is True
        set_kairos_active(False)
        assert is_kairos_active() is False


class TestKairosPrompt:
    def test_addendum_when_active(self):
        set_kairos_active(True)
        addendum = get_kairos_prompt_addendum()
        assert "assistant mode" in addendum.lower()
        assert "concise" in addendum.lower()
        set_kairos_active(False)

    def test_no_addendum_when_inactive(self):
        set_kairos_active(False)
        addendum = get_kairos_prompt_addendum()
        assert addendum == ""


class TestGetDueTasks:
    def test_returns_overdue_tasks(self, tmp_path):
        tasks_file = tmp_path / "scheduled_tasks.json"
        past_time = int(time.time()) - 3600  # 1 hour ago
        tasks = {
            "tasks": [
                {
                    "id": "t1",
                    "cron": "0 * * * *",
                    "prompt": "Do hourly check",
                    "createdAt": past_time,
                    "recurring": True,
                    "next_run": past_time,
                }
            ]
        }
        tasks_file.write_text(json.dumps(tasks))
        due = get_due_tasks(tasks_path=str(tasks_file))
        assert len(due) == 1
        assert due[0]["id"] == "t1"

    def test_skips_future_tasks(self, tmp_path):
        tasks_file = tmp_path / "scheduled_tasks.json"
        future_time = int(time.time()) + 3600  # 1 hour from now
        tasks = {
            "tasks": [
                {
                    "id": "t2",
                    "cron": "0 * * * *",
                    "prompt": "Future task",
                    "createdAt": int(time.time()),
                    "recurring": True,
                    "next_run": future_time,
                }
            ]
        }
        tasks_file.write_text(json.dumps(tasks))
        due = get_due_tasks(tasks_path=str(tasks_file))
        assert len(due) == 0

    def test_empty_file_returns_empty(self, tmp_path):
        tasks_file = tmp_path / "scheduled_tasks.json"
        due = get_due_tasks(tasks_path=str(tasks_file))
        assert due == []


class TestMarkTaskFired:
    def test_recurring_task_gets_new_next_run(self, tmp_path):
        tasks_file = tmp_path / "scheduled_tasks.json"
        now = int(time.time())
        tasks = {
            "tasks": [
                {
                    "id": "t1",
                    "cron": "0 * * * *",
                    "prompt": "hourly",
                    "createdAt": now,
                    "recurring": True,
                    "next_run": now - 100,
                }
            ]
        }
        tasks_file.write_text(json.dumps(tasks))
        mark_task_fired("t1", tasks_path=str(tasks_file))
        updated = json.loads(tasks_file.read_text())
        task = updated["tasks"][0]
        assert task["next_run"] > now  # pushed into future

    def test_one_shot_task_is_removed(self, tmp_path):
        tasks_file = tmp_path / "scheduled_tasks.json"
        now = int(time.time())
        tasks = {
            "tasks": [
                {
                    "id": "t2",
                    "cron": "0 9 * * 1",
                    "prompt": "once",
                    "createdAt": now,
                    "recurring": False,
                    "next_run": now - 100,
                }
            ]
        }
        tasks_file.write_text(json.dumps(tasks))
        mark_task_fired("t2", tasks_path=str(tasks_file))
        updated = json.loads(tasks_file.read_text())
        assert len(updated["tasks"]) == 0
