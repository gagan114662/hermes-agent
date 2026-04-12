# tests/test_harness/test_config.py
from pathlib import Path
import pytest
from harness.config import HarnessConfig


def test_harness_config_defaults(tmp_path):
    cfg = HarnessConfig(project_dir=tmp_path, task_spec="Build X")
    assert cfg.max_sessions == 50
    assert cfg.max_cost_dollars == 100.0
    assert cfg.max_session_duration_seconds == 7200
    assert cfg.model == "anthropic/claude-sonnet-4-6"
    assert cfg.progress_file == tmp_path / "hermes_progress.md"
    assert cfg.features_file == tmp_path / "hermes_features.json"
    assert cfg.init_script is None
    assert cfg.allowed_tools is None
    assert cfg.forbidden_paths is None
    assert cfg.approval_required_commands is None
    assert cfg.gateway_url is None


def test_harness_config_custom(tmp_path):
    cfg = HarnessConfig(
        project_dir=tmp_path,
        task_spec="Fix bug",
        max_sessions=10,
        max_cost_dollars=5.0,
        model="openai/gpt-4o",
        gateway_url="http://localhost:30000/v1",
        forbidden_paths=["/etc", "/root"],
        approval_required_commands=["git push", "npm publish"],
    )
    assert cfg.max_sessions == 10
    assert cfg.gateway_url == "http://localhost:30000/v1"
    assert "/etc" in cfg.forbidden_paths


def test_harness_config_progress_file_override(tmp_path):
    custom = tmp_path / "my_progress.md"
    cfg = HarnessConfig(project_dir=tmp_path, task_spec="X", progress_file=custom)
    assert cfg.progress_file == custom
