#!/usr/bin/env python3
"""
Canary test: runs a full agent session after deploy to verify health.

Usage:
    python3 scripts/canary_test.py

Exit codes:
    0 — canary passed
    1 — canary failed (alert should be sent)

Sends Telegram alert if TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID are set.
"""
import json
import os
import sys
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("canary")


def send_telegram(message: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        import urllib.request
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = json.dumps({"chat_id": chat_id, "text": message}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        logger.warning("Telegram alert failed: %s", e)


def run_canary() -> tuple[bool, str]:
    """Run a canary session. Returns (passed, message)."""
    try:
        from run_agent import AIAgent

        agent = AIAgent(
            model=os.environ.get("HERMES_CANARY_MODEL", "anthropic/claude-haiku-4-5"),
            api_key=os.environ.get("OPENROUTER_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"),
            quiet_mode=True,
            max_iterations=5,
        )

        start = time.time()
        result = agent.run_conversation(
            "Respond with exactly: CANARY_OK"
        )
        duration = time.time() - start

        response = result.get("final_response", "") or ""
        if "CANARY_OK" in response:
            return True, f"Canary passed in {duration:.1f}s"
        else:
            return False, f"Canary failed: unexpected response: {response[:100]!r}"

    except Exception as e:
        return False, f"Canary error: {e}"


def main():
    passed, message = run_canary()
    logger.info(message)

    if not passed:
        send_telegram(f"Hermes canary FAILED\n{message}")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
