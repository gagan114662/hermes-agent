#!/usr/bin/env python3
"""
First Run — one-time setup sequence for new installs.

1. Detect and configure all MCP servers from credentials
2. Run the proactive loop immediately (instant first actions)
3. Send the wow Telegram message: "I connected to X tools and already did Y"
4. Mark setup as done so this never runs again
"""
import logging
import os
import sys
import httpx
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.mcp_autoconfig import detect_and_configure
from scripts.proactive_loop import run_all_queues

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _setup_marker() -> Path:
    return Path(os.environ.get("HOME", str(Path.home()))) / ".hermes" / ".setup_done"


def _is_first_run() -> bool:
    return not _setup_marker().exists()


def _mark_setup_done() -> None:
    marker = _setup_marker()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()


def _send_welcome(services: list, actions: list) -> None:
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    owner_id = os.environ.get("TELEGRAM_OWNER_ID", "")
    if not bot_token or not owner_id:
        logger.info("Telegram not configured — skipping welcome message")
        return

    svc_list = ", ".join(services) if services else "your tools"
    lines = [
        f"👋 Hi! I'm Hermes, your AI employee. I'm already working.\n",
        f"🔗 Connected to: {svc_list}\n",
    ]
    if actions:
        lines.append("Here's what I just did:\n")
        for a in actions[:5]:
            lines.append(f"✅ {a}")
        if len(actions) > 5:
            lines.append(f"... and {len(actions) - 5} more")
        lines.append("\nI'll update you every morning. You won't need to ask me anything.")
    else:
        lines.append("I'm watching your inbox, leads, and reviews. I'll update you every morning.")

    text = "\n".join(lines)
    try:
        httpx.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": owner_id, "text": text},
            timeout=10,
        )
        logger.info("Welcome message sent to owner")
    except Exception as e:
        logger.warning("Welcome message failed: %s", e)


def run_first_time_setup() -> None:
    """Run the full first-time setup sequence. No-op if already done."""
    if not _is_first_run():
        logger.info("Setup already done — skipping first run")
        return

    logger.info("=== Hermes First Run ===")

    # 1. Detect tools from credentials, configure MCP servers
    logger.info("Step 1: Detecting and configuring tools...")
    services = detect_and_configure()
    logger.info("Configured %d services: %s", len(services), services)

    # 2. Run the proactive work loop immediately — create instant value
    logger.info("Step 2: Running first proactive loop pass...")
    actions = run_all_queues()
    logger.info("First loop completed: %d actions", len(actions))

    # 3. Send the wow message to owner
    logger.info("Step 3: Sending welcome message...")
    _send_welcome(services, actions)

    # 4. Mark as done
    _mark_setup_done()
    logger.info("=== First run complete ===")


if __name__ == "__main__":
    run_first_time_setup()
