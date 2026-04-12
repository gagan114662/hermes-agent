"""ContextManager — smart loading of progress + features into agent context.

Progressive loading strategy:
  Priority 1 (always)  — task_spec + completed feature list + next 3 steps
  Priority 2 (always)  — recent session history (last 5 sessions)
  Priority 3 (sometimes) — files mentioned in progress for the current feature

Total context is kept under MAX_CONTEXT_BYTES to leave room for the
conversation itself.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from harness.features import Feature, FeatureTracker

logger = logging.getLogger(__name__)

MAX_CONTEXT_BYTES = 100 * 1024   # 100 KB hard cap for injected context
SESSION_HISTORY_LIMIT = 5        # Last N sessions to include


class ContextManager:
    """Read and write the progress.md / features.json pair.

    All methods are stateless — pass the file paths on each call so the
    same ContextManager instance can serve multiple harness configs.
    """

    # ── Loading ───────────────────────────────────────────────────────

    def load_context(
        self,
        progress_file: Path,
        features_file: Path,
        task_spec: str,
    ) -> dict:
        """Load and assemble harness context.

        Returns
        -------
        dict with keys:
          task_spec         — the original goal string
          session_history   — list of str, one per past session summary
          completed_features — list of Feature dicts (passes=True)
          next_steps        — list of Feature dicts (up to 3 next incomplete)
        """
        progress_file = Path(progress_file)
        features_file = Path(features_file)

        tracker = FeatureTracker(features_file)
        session_history = self._parse_session_history(progress_file)
        completed = [f for f in tracker.get_all_features() if f.passes]
        next_steps = tracker.get_incomplete_features(limit=3)

        return {
            "task_spec": task_spec,
            "session_history": session_history[-SESSION_HISTORY_LIMIT:],
            "completed_features": [{"id": f.id, "description": f.description} for f in completed],
            "next_steps": [
                {
                    "id": f.id,
                    "description": f.description,
                    "test_cases": f.test_cases,
                    "file_path": f.file_path,
                }
                for f in next_steps
            ],
        }

    def build_system_prompt(self, ctx: dict) -> str:
        """Convert loaded context into an agent system prompt string.

        Trims to MAX_CONTEXT_BYTES by progressively dropping the oldest
        session history entries first.
        """
        parts = [
            "# Harness Session\n",
            f"## Goal\n{ctx['task_spec']}\n",
        ]

        if ctx.get("completed_features"):
            lines = "\n".join(
                f"- [{f['id']}] {f['description']}"
                for f in ctx["completed_features"]
            )
            parts.append(f"\n## Completed Features\n{lines}\n")

        if ctx.get("next_steps"):
            lines = "\n".join(
                f"- [{f['id']}] {f['description']}"
                + (f"\n  Test: {'; '.join(f['test_cases'])}" if f.get("test_cases") else "")
                for f in ctx["next_steps"]
            )
            parts.append(f"\n## Next Features to Implement\n{lines}\n")

        if ctx.get("session_history"):
            history = ctx["session_history"]
            history_parts = ["\n## Session History (most recent last)\n"]
            for entry in history:
                history_parts.append(f"---\n{entry}\n")
            parts.extend(history_parts)

        prompt = "".join(parts)

        # Trim if over budget — drop history first
        while len(prompt.encode()) > MAX_CONTEXT_BYTES and ctx.get("session_history"):
            ctx["session_history"].pop(0)
            prompt = self.build_system_prompt(ctx)

        # Hard truncate if still too long (shouldn't happen in practice)
        if len(prompt.encode()) > MAX_CONTEXT_BYTES:
            prompt = prompt.encode()[:MAX_CONTEXT_BYTES].decode(errors="ignore")

        return prompt

    # ── Saving ────────────────────────────────────────────────────────

    def save_progress(
        self,
        progress_file: Path,
        features_file: Path,
        session_number: int,
        summary: str,
        features_completed: list[str],
    ) -> None:
        """Append a session summary to progress.md and mark features done.

        Parameters
        ----------
        progress_file   : Path to the markdown progress file.
        features_file   : Path to features.json (to mark features complete).
        session_number  : The 1-based session index.
        summary         : Free-text summary of what this session accomplished.
        features_completed : List of feature IDs completed this session.
        """
        progress_file = Path(progress_file)
        progress_file.parent.mkdir(parents=True, exist_ok=True)

        ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        section = f"\n## Session {session_number} — {ts}\n\n{summary}\n"

        if features_completed:
            feat_list = "\n".join(f"- {fid}" for fid in features_completed)
            section += f"\n**Features completed this session:**\n{feat_list}\n"

        with open(progress_file, "a", encoding="utf-8") as fh:
            fh.write(section)

        # Update features.json
        if features_completed:
            tracker = FeatureTracker(features_file)
            for fid in features_completed:
                tracker.mark_complete(fid, session_number=session_number)
            tracker.save()

    # ── Internal helpers ──────────────────────────────────────────────

    def _parse_session_history(self, progress_file: Path) -> list[str]:
        """Split progress.md on ## Session N headers."""
        if not progress_file.exists():
            return []
        content = progress_file.read_text(encoding="utf-8")
        # Split on h2 session headers, keep each block
        blocks = re.split(r"(?=^## Session \d+)", content, flags=re.MULTILINE)
        return [b.strip() for b in blocks if b.strip() and b.strip().startswith("## Session")]
