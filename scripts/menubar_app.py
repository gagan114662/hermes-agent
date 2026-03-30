#!/usr/bin/env python3
"""
Hermes Menubar App — live activity feed in the macOS menu bar.
Shows last 5 actions. Pause/resume toggle. Requires rumps.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import rumps

LOG_PATH = Path(os.environ.get("HOME", str(Path.home()))) / ".hermes" / "action_log.json"
PAUSE_PATH = Path(os.environ.get("HOME", str(Path.home()))) / ".hermes" / ".paused"


def _load_recent(n=5) -> list:
    if not LOG_PATH.exists():
        return []
    try:
        log = json.loads(LOG_PATH.read_text())
        return list(reversed(log[-n:]))
    except Exception:
        return []


def _time_ago(ts_str: str) -> str:
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - ts
        mins = int(delta.total_seconds() / 60)
        if mins < 1:
            return "just now"
        if mins < 60:
            return f"{mins}m ago"
        return f"{mins // 60}h ago"
    except Exception:
        return ""


class HermesMenubar(rumps.App):
    def __init__(self):
        super().__init__("⚡", quit_button=None)
        self.paused = PAUSE_PATH.exists()
        self._update_menu()

    def _update_menu(self):
        items = []
        recent = _load_recent()
        if not recent:
            items.append(rumps.MenuItem("● Hermes is watching...", callback=None))
        else:
            for entry in recent:
                label = f"{_time_ago(entry['timestamp'])}   {entry['action'][:55]}"
                items.append(rumps.MenuItem(label, callback=None))

        items.append(rumps.separator)
        pause_label = "▶ Resume Hermes" if self.paused else "⏸ Pause Hermes"
        items.append(rumps.MenuItem(pause_label, callback=self.toggle_pause))
        items.append(rumps.MenuItem("Quit", callback=rumps.quit_application))
        self.menu.clear()
        self.menu = items
        self.title = "⏸" if self.paused else "⚡"

    @rumps.timer(30)
    def refresh(self, _):
        self.paused = PAUSE_PATH.exists()
        self._update_menu()

    def toggle_pause(self, _):
        if self.paused:
            PAUSE_PATH.unlink(missing_ok=True)
            self.paused = False
        else:
            PAUSE_PATH.touch()
            self.paused = True
        self._update_menu()


if __name__ == "__main__":
    HermesMenubar().run()
