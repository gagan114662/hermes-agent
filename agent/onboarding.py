"""3-3-3 Onboarding — journey-stage detection for Hermes.

Tracks how many sessions a user has had and maps that to a "journey stage":

  Stage 1  day-1     (sessions 1–3)    → point toward /specnew
  Stage 2  week-2    (sessions 4–14)   → point toward /skilltest / /skillnew
  Stage 3  month-2+  (sessions 15+)    → point toward /lineage / /costmap

The session count is stored in a single JSON file at
``~/.hermes/onboarding.json``.  Each call to :func:`record_session` bumps
the counter and records the timestamp of the latest session.

Public API
----------
  record_session()         → bump the counter for the current session
  get_journey_stage()      → JourneyStage with stage int + metadata
  get_onboarding_state()   → raw dict (for /onboard debug view)
  reset_onboarding()       → wipe state (for tests / fresh-start UX)
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _state_path() -> Path:
    from hermes_constants import get_hermes_home
    return Path(get_hermes_home()) / "onboarding.json"


def _load_state() -> Dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {"session_count": 0, "first_session_ts": None, "last_session_ts": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"session_count": 0, "first_session_ts": None, "last_session_ts": None}


def _save_state(state: Dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Journey stage
# ---------------------------------------------------------------------------

# Thresholds (session counts, inclusive lower bound)
_STAGE2_THRESHOLD = 4   # sessions 4-14  → week-2 learner
_STAGE3_THRESHOLD = 15  # sessions 15+   → power user / month-2


@dataclass
class JourneyStage:
    stage: int          # 1, 2, or 3
    session_count: int
    label: str          # "day-1", "week-2", "month-2+"
    headline: str       # one-line description of the stage
    next_command: str   # the most useful command right now
    tip: str            # short contextual tip shown in /onboard output


_STAGES: Dict[int, Dict[str, str]] = {
    1: {
        "label": "day-1",
        "headline": "Just getting started",
        "next_command": "/specnew",
        "tip": (
            "Run /specnew <what you want to build> to let Hermes write a "
            "precise technical spec and context library for your project. "
            "This single step unlocks the full power of every other command."
        ),
    },
    2: {
        "label": "week-2",
        "headline": "Building your toolkit",
        "next_command": "/skillnew",
        "tip": (
            "You have a few sessions under your belt — time to automate "
            "your recurring workflows. Use /skillnew to create a reusable "
            "skill, then /skilltest to put it through a 5-test protocol "
            "before trusting it in production."
        ),
    },
    3: {
        "label": "month-2+",
        "headline": "Power user — observe & optimize",
        "next_command": "/costmap",
        "tip": (
            "You're running complex delegations now. Use /costmap to see "
            "per-task token spend after every /task call, and /lineage "
            "<file> to understand exactly which agent goal produced any "
            "file in your project."
        ),
    },
}


def _stage_for(session_count: int) -> int:
    if session_count >= _STAGE3_THRESHOLD:
        return 3
    if session_count >= _STAGE2_THRESHOLD:
        return 2
    return 1


def get_journey_stage() -> JourneyStage:
    """Return the current journey stage based on total session count."""
    with _lock:
        state = _load_state()
    n = state.get("session_count", 0)
    stage_num = _stage_for(n)
    meta = _STAGES[stage_num]
    return JourneyStage(
        stage=stage_num,
        session_count=n,
        label=meta["label"],
        headline=meta["headline"],
        next_command=meta["next_command"],
        tip=meta["tip"],
    )


# ---------------------------------------------------------------------------
# Session recording
# ---------------------------------------------------------------------------

def record_session() -> JourneyStage:
    """Bump the session counter and persist state.  Returns the new stage."""
    now = datetime.now(tz=timezone.utc).isoformat()
    with _lock:
        state = _load_state()
        if state.get("first_session_ts") is None:
            state["first_session_ts"] = now
        state["session_count"] = state.get("session_count", 0) + 1
        state["last_session_ts"] = now
        _save_state(state)
        n = state["session_count"]

    stage_num = _stage_for(n)
    meta = _STAGES[stage_num]
    return JourneyStage(
        stage=stage_num,
        session_count=n,
        label=meta["label"],
        headline=meta["headline"],
        next_command=meta["next_command"],
        tip=meta["tip"],
    )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def get_onboarding_state() -> Dict[str, Any]:
    """Return the raw persisted state dict (for debug / /onboard command)."""
    with _lock:
        return dict(_load_state())


def reset_onboarding() -> None:
    """Wipe all onboarding state (for testing or /onboard reset)."""
    with _lock:
        path = _state_path()
        if path.exists():
            path.unlink()
