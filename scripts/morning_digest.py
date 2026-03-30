#!/usr/bin/env python3
"""
Morning Digest — sends owner a daily Telegram summary of everything Hermes did.
Runs at 8am via cron. Reads action_log.json, formats a human-friendly message.
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _log_path() -> Path:
    return Path(os.environ.get("HOME", str(Path.home()))) / ".hermes" / "action_log.json"


def load_last_24h_actions() -> list:
    path = _log_path()
    if not path.exists():
        return []
    try:
        log = json.loads(path.read_text())
    except Exception:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent = []
    for entry in log:
        try:
            ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
            if ts >= cutoff:
                recent.append(entry)
        except Exception:
            continue
    return recent


def format_digest(actions: list) -> str:
    if not actions:
        return "☀️ Good morning! All clear — nothing needed attention overnight. I'm watching."

    lines = [f"☀️ Good morning! Here's what I did while you slept ({len(actions)} tasks):\n"]
    for entry in actions:
        lines.append(f"✅ {entry['action']}")
    lines.append("\nI'm on it today. You focus on what only you can do.")
    return "\n".join(lines)


def _telegram_send(bot_token: str, chat_id: str, text: str) -> None:
    httpx.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=10,
    )


def send_digest() -> None:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    owner_id = os.environ.get("TELEGRAM_OWNER_ID", "")
    if not bot_token or not owner_id:
        logger.warning("Telegram not configured — skipping digest")
        return

    actions = load_last_24h_actions()
    text = format_digest(actions)
    _telegram_send(bot_token, owner_id, text)

    # Clear the log after sending
    _log_path().write_text(json.dumps([], indent=2))
    logger.info("Morning digest sent (%d actions)", len(actions))


if __name__ == "__main__":
    send_digest()
