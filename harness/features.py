"""Feature tracking — the features.json backbone of a harness run.

Each feature is a unit of work the agent is expected to implement.
FeatureTracker loads/saves features.json and answers "what should
the next session work on?" respecting completion state and dependencies.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Feature:
    """One unit of work tracked across harness sessions.

    Attributes
    ----------
    id : str
        Unique slug used as the primary key (e.g. "user-auth", "feat-001").
    description : str
        Human-readable description of what needs to be built.
    file_path : str
        Primary file this feature touches (informational, for context).
    test_cases : list[str]
        Natural-language descriptions of acceptance tests.
    dependencies : list[str]
        Feature IDs that must be complete before this one can be started.
    passes : bool
        True when the feature has been verified complete.
    assigned_session : int | None
        Session number that claimed this feature (set when a session starts
        working on it so parallel harness instances can coordinate).
    """

    id: str
    description: str
    file_path: str = ""
    test_cases: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    passes: bool = False
    assigned_session: Optional[int] = None


class FeatureTracker:
    """Load, query, and persist features.json.

    Usage
    -----
    tracker = FeatureTracker(Path("hermes_features.json"))
    next_feat = tracker.get_next_feature()   # None if all done
    tracker.mark_complete(next_feat.id, session_number=5)
    tracker.save()
    """

    def __init__(self, features_file: Path) -> None:
        self._path = Path(features_file)
        self._features: list[Feature] = []
        if self._path.exists():
            self._load()

    # ── Persistence ───────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text())
            if isinstance(raw, list):
                self._features = [Feature(**f) for f in raw]
            elif isinstance(raw, dict) and "features" in raw:
                self._features = [Feature(**f) for f in raw["features"]]
        except Exception as exc:
            logger.warning("Failed to load features from %s: %s", self._path, exc)
            self._features = []

    def save(self) -> None:
        """Write current state to features_file (creates parent dirs)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps([asdict(f) for f in self._features], indent=2)
        )

    # ── Mutation ──────────────────────────────────────────────────────

    def add_feature(self, feature: Feature) -> None:
        """Append a feature.  Does not auto-save — call save() explicitly."""
        self._features.append(feature)

    def mark_complete(self, feature_id: str, session_number: Optional[int] = None) -> None:
        """Mark feature as passing.  Does not auto-save."""
        for feat in self._features:
            if feat.id == feature_id:
                feat.passes = True
                if session_number is not None:
                    feat.assigned_session = session_number
                return
        logger.warning("mark_complete: feature '%s' not found", feature_id)

    # ── Query ─────────────────────────────────────────────────────────

    def get_feature(self, feature_id: str) -> Optional[Feature]:
        for f in self._features:
            if f.id == feature_id:
                return f
        return None

    def get_next_feature(self) -> Optional[Feature]:
        """Return the first incomplete, unblocked feature, or None."""
        complete_ids = {f.id for f in self._features if f.passes}
        for feat in self._features:
            if feat.passes:
                continue
            if all(dep in complete_ids for dep in feat.dependencies):
                return feat
        return None

    def get_incomplete_features(self, limit: int = 3) -> list[Feature]:
        """Return up to `limit` incomplete features for context injection."""
        complete_ids = {f.id for f in self._features if f.passes}
        result = []
        for feat in self._features:
            if not feat.passes and all(dep in complete_ids for dep in feat.dependencies):
                result.append(feat)
                if len(result) >= limit:
                    break
        return result

    def get_progress_stats(self) -> dict:
        total = len(self._features)
        completed = sum(1 for f in self._features if f.passes)
        pending = total - completed
        pct = (completed / total * 100.0) if total > 0 else 0.0
        return {
            "total": total,
            "completed": completed,
            "pending": pending,
            "pct_complete": round(pct, 1),
        }

    def all_complete(self) -> bool:
        return all(f.passes for f in self._features)
