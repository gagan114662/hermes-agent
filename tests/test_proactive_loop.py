import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from scripts.proactive_loop import (
    log_action,
    load_action_log,
    run_inbox_queue,
    run_leads_queue,
    run_money_queue,
    run_prospecting_queue,
    run_reputation_queue,
    run_all_queues,
)

def test_log_action_appends_to_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()
    log_action("replied to Maria G. email")
    log = load_action_log()
    assert len(log) == 1
    assert log[0]["action"] == "replied to Maria G. email"
    assert "timestamp" in log[0]

def test_log_action_multiple(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()
    log_action("action 1")
    log_action("action 2")
    assert len(load_action_log()) == 2

def test_run_leads_queue_follows_up_stale_prospects(monkeypatch):
    monkeypatch.setattr("scripts.proactive_loop._list_stale_prospects", lambda: [
        {"id": "abc123", "name": "Jake Miller", "contact_hint": "+14155550101"}
    ])
    sent = []
    monkeypatch.setattr("scripts.proactive_loop._send_followup", lambda prospect: sent.append(prospect["name"]))
    actions = run_leads_queue()
    assert len(actions) == 1
    assert "Jake Miller" in actions[0]

def test_run_all_queues_returns_all_actions(monkeypatch):
    monkeypatch.setattr("scripts.proactive_loop.run_inbox_queue", lambda: ["replied to email"])
    monkeypatch.setattr("scripts.proactive_loop.run_leads_queue", lambda: ["followed up Jake"])
    monkeypatch.setattr("scripts.proactive_loop.run_money_queue", lambda: [])
    monkeypatch.setattr("scripts.proactive_loop.run_prospecting_queue", lambda: ["found lead on reddit"])
    monkeypatch.setattr("scripts.proactive_loop.run_reputation_queue", lambda: [])
    monkeypatch.setattr("scripts.proactive_loop._notify_if_actions", lambda actions: None)
    actions = run_all_queues()
    assert len(actions) == 3

def test_load_action_log_returns_empty_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()
    assert load_action_log() == []

def test_run_money_queue_returns_list(monkeypatch):
    monkeypatch.setattr("scripts.proactive_loop._list_overdue_invoices", lambda: [])
    actions = run_money_queue()
    assert isinstance(actions, list)
