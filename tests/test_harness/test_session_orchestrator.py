# tests/test_harness/test_session_orchestrator.py
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest
from harness.config import HarnessConfig
from harness.features import Feature, FeatureTracker
from harness.session_orchestrator import SessionOrchestrator


def _make_cfg(tmp_path, task_spec="Build X", max_sessions=3):
    return HarnessConfig(
        project_dir=tmp_path,
        task_spec=task_spec,
        max_sessions=max_sessions,
        max_cost_dollars=10.0,
    )


def _fake_agent_result(summary="Done", input_tokens=100, output_tokens=50):
    return {
        "response": summary,
        "messages": [],
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


@patch("harness.session_orchestrator.AIAgent")
def test_run_harness_completes_when_all_features_done(MockAgent, tmp_path):
    cfg = _make_cfg(tmp_path)
    # Pre-populate features.json with one already-complete feature
    tracker = FeatureTracker(cfg.features_file)
    tracker.add_feature(Feature(id="f1", description="Only feature", passes=True))
    tracker.save()
    orch = SessionOrchestrator(cfg)
    result = orch.run_harness()
    assert result["status"] == "completed"
    assert result["sessions_run"] == 0
    MockAgent.assert_not_called()


@patch("harness.session_orchestrator.AIAgent")
def test_run_harness_runs_one_session(MockAgent, tmp_path):
    cfg = _make_cfg(tmp_path, max_sessions=1)
    tracker = FeatureTracker(cfg.features_file)
    tracker.add_feature(Feature(id="f1", description="Build thing"))
    tracker.save()

    mock_instance = MagicMock()
    mock_instance.run_conversation.return_value = _fake_agent_result()
    MockAgent.return_value = mock_instance

    orch = SessionOrchestrator(cfg)
    result = orch.run_harness()
    assert result["sessions_run"] == 1
    assert mock_instance.run_conversation.call_count == 1


@patch("harness.session_orchestrator.AIAgent")
def test_run_harness_stops_at_session_limit(MockAgent, tmp_path):
    cfg = _make_cfg(tmp_path, max_sessions=2)
    tracker = FeatureTracker(cfg.features_file)
    for i in range(5):
        tracker.add_feature(Feature(id=f"f{i}", description=f"Feature {i}"))
    tracker.save()

    mock_instance = MagicMock()
    mock_instance.run_conversation.return_value = _fake_agent_result()
    MockAgent.return_value = mock_instance

    orch = SessionOrchestrator(cfg)
    result = orch.run_harness()
    assert result["sessions_run"] == 2
    assert result["status"] == "session_limit_reached"


@patch("harness.session_orchestrator.AIAgent")
def test_run_harness_saves_progress_after_each_session(MockAgent, tmp_path):
    cfg = _make_cfg(tmp_path, max_sessions=1)
    tracker = FeatureTracker(cfg.features_file)
    tracker.add_feature(Feature(id="f1", description="Build thing"))
    tracker.save()

    mock_instance = MagicMock()
    mock_instance.run_conversation.return_value = _fake_agent_result("Built it")
    MockAgent.return_value = mock_instance

    orch = SessionOrchestrator(cfg)
    orch.run_harness()
    assert cfg.progress_file.exists()
    content = cfg.progress_file.read_text()
    assert "## Session 1" in content


@patch("harness.session_orchestrator.AIAgent")
def test_on_session_callbacks_fired(MockAgent, tmp_path):
    cfg = _make_cfg(tmp_path, max_sessions=1)
    tracker = FeatureTracker(cfg.features_file)
    tracker.add_feature(Feature(id="f1", description="Thing"))
    tracker.save()

    mock_instance = MagicMock()
    mock_instance.run_conversation.return_value = _fake_agent_result()
    MockAgent.return_value = mock_instance

    starts, ends = [], []
    orch = SessionOrchestrator(cfg, on_session_start=starts.append, on_session_end=ends.append)
    orch.run_harness()
    assert len(starts) == 1
    assert len(ends) == 1
