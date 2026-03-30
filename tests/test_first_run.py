import pytest
from unittest.mock import patch, MagicMock
from scripts.first_run import run_first_time_setup, _is_first_run, _mark_setup_done

def test_is_first_run_true_when_no_marker(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()
    assert _is_first_run() is True

def test_is_first_run_false_after_marker(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()
    _mark_setup_done()
    assert _is_first_run() is False

def test_first_run_sequence(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()

    messages_sent = []
    monkeypatch.setattr("scripts.first_run.detect_and_configure", lambda: ["gmail", "shopify"])
    monkeypatch.setattr("scripts.first_run.run_all_queues", lambda: ["replied to 2 emails"])
    monkeypatch.setattr("scripts.first_run._send_welcome", lambda services, actions: messages_sent.append(services))

    run_first_time_setup()

    assert messages_sent[0] == ["gmail", "shopify"]
    assert _is_first_run() is False

def test_first_run_skips_if_already_done(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes").mkdir()
    _mark_setup_done()

    called = []
    monkeypatch.setattr("scripts.first_run.detect_and_configure", lambda: called.append(1) or [])
    monkeypatch.setattr("scripts.first_run.run_all_queues", lambda: [])
    monkeypatch.setattr("scripts.first_run._send_welcome", lambda s, a: None)

    run_first_time_setup()
    assert called == []  # should not have run
