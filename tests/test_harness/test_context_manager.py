# tests/test_harness/test_context_manager.py
from pathlib import Path
import pytest
from harness.context_manager import ContextManager
from harness.features import Feature, FeatureTracker


def test_load_context_empty_files(tmp_path):
    cm = ContextManager()
    ctx = cm.load_context(
        progress_file=tmp_path / "progress.md",
        features_file=tmp_path / "features.json",
        task_spec="Build auth system",
    )
    assert ctx["task_spec"] == "Build auth system"
    assert ctx["session_history"] == []
    assert ctx["completed_features"] == []
    assert ctx["next_steps"] == []


def test_load_context_reads_progress(tmp_path):
    progress = tmp_path / "progress.md"
    progress.write_text("## Session 1\nCompleted login feature.\n")
    cm = ContextManager()
    ctx = cm.load_context(
        progress_file=progress,
        features_file=tmp_path / "features.json",
        task_spec="Build auth",
    )
    assert len(ctx["session_history"]) == 1
    assert "login" in ctx["session_history"][0]


def test_load_context_next_steps_from_features(tmp_path):
    features_file = tmp_path / "features.json"
    tracker = FeatureTracker(features_file)
    tracker.add_feature(Feature(id="f1", description="Login page", passes=True))
    tracker.add_feature(Feature(id="f2", description="Dashboard"))
    tracker.add_feature(Feature(id="f3", description="Profile"))
    tracker.add_feature(Feature(id="f4", description="Settings"))
    tracker.save()
    cm = ContextManager()
    ctx = cm.load_context(
        progress_file=tmp_path / "progress.md",
        features_file=features_file,
        task_spec="Build app",
    )
    assert len(ctx["next_steps"]) == 3
    assert ctx["next_steps"][0]["id"] == "f2"


def test_save_progress_writes_markdown(tmp_path):
    progress = tmp_path / "progress.md"
    cm = ContextManager()
    cm.save_progress(
        progress_file=progress,
        features_file=tmp_path / "features.json",
        session_number=2,
        summary="Implemented user registration endpoint.",
        features_completed=["user-registration"],
    )
    content = progress.read_text()
    assert "## Session 2" in content
    assert "user registration" in content.lower()
    assert "user-registration" in content


def test_save_progress_appends_to_existing(tmp_path):
    progress = tmp_path / "progress.md"
    progress.write_text("## Session 1\nPrevious work.\n")
    cm = ContextManager()
    cm.save_progress(
        progress_file=progress,
        features_file=tmp_path / "features.json",
        session_number=2,
        summary="More work done.",
        features_completed=[],
    )
    content = progress.read_text()
    assert "## Session 1" in content
    assert "## Session 2" in content


def test_build_system_prompt_under_100kb(tmp_path):
    cm = ContextManager()
    ctx = cm.load_context(
        progress_file=tmp_path / "progress.md",
        features_file=tmp_path / "features.json",
        task_spec="x" * 50_000,
    )
    prompt = cm.build_system_prompt(ctx)
    assert len(prompt.encode()) < 100 * 1024
