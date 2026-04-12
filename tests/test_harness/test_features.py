# tests/test_harness/test_features.py
import json
from pathlib import Path
import pytest
from harness.features import Feature, FeatureTracker


def test_feature_dataclass_defaults():
    f = Feature(id="feat-1", description="Add login page")
    assert f.passes is False
    assert f.assigned_session is None
    assert f.test_cases == []
    assert f.dependencies == []


def test_feature_tracker_empty(tmp_path):
    features_file = tmp_path / "features.json"
    tracker = FeatureTracker(features_file)
    assert tracker.get_next_feature() is None
    stats = tracker.get_progress_stats()
    assert stats["total"] == 0
    assert stats["completed"] == 0


def test_feature_tracker_add_and_get_next(tmp_path):
    features_file = tmp_path / "features.json"
    tracker = FeatureTracker(features_file)
    tracker.add_feature(Feature(id="f1", description="First"))
    tracker.add_feature(Feature(id="f2", description="Second"))
    nxt = tracker.get_next_feature()
    assert nxt is not None
    assert nxt.id == "f1"


def test_feature_tracker_mark_complete(tmp_path):
    features_file = tmp_path / "features.json"
    tracker = FeatureTracker(features_file)
    tracker.add_feature(Feature(id="f1", description="First"))
    tracker.mark_complete("f1", session_number=3)
    tracker.save()
    # Reload and verify persistence
    tracker2 = FeatureTracker(features_file)
    feat = tracker2.get_feature("f1")
    assert feat.passes is True
    assert feat.assigned_session == 3


def test_feature_tracker_skip_completed(tmp_path):
    features_file = tmp_path / "features.json"
    tracker = FeatureTracker(features_file)
    tracker.add_feature(Feature(id="f1", description="Done", passes=True))
    tracker.add_feature(Feature(id="f2", description="Next"))
    nxt = tracker.get_next_feature()
    assert nxt.id == "f2"


def test_feature_tracker_progress_stats(tmp_path):
    features_file = tmp_path / "features.json"
    tracker = FeatureTracker(features_file)
    tracker.add_feature(Feature(id="f1", description="Done", passes=True))
    tracker.add_feature(Feature(id="f2", description="Pending"))
    stats = tracker.get_progress_stats()
    assert stats["total"] == 2
    assert stats["completed"] == 1
    assert stats["pending"] == 1
    assert stats["pct_complete"] == 50.0


def test_feature_tracker_respects_dependencies(tmp_path):
    features_file = tmp_path / "features.json"
    tracker = FeatureTracker(features_file)
    tracker.add_feature(Feature(id="f1", description="Auth"))
    tracker.add_feature(Feature(id="f2", description="Dashboard", dependencies=["f1"]))
    # f2 depends on f1 which is not complete → get_next_feature returns f1
    nxt = tracker.get_next_feature()
    assert nxt.id == "f1"
