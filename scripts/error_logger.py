#!/usr/bin/env python3
"""
Error intelligence: logs tool errors to ~/.hermes/errors/ for weekly digest.

Wired into gateway/hooks.py on_tool_error hook.
Weekly digest sent via Telegram.
"""
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

ERRORS_DIR = os.path.expanduser("~/.hermes/errors")


def log_tool_error(
    tool_name: str,
    error: str,
    args: dict = None,
    session_id: str = None,
) -> None:
    """Append a tool error to today's error log. Never raises."""
    try:
        os.makedirs(ERRORS_DIR, exist_ok=True)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        log_file = os.path.join(ERRORS_DIR, f"{today}.jsonl")

        entry = {
            "ts": datetime.utcnow().isoformat(),
            "tool": tool_name,
            "error": str(error)[:500],
            "session_id": session_id,
        }
        with open(log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def get_weekly_digest() -> str:
    """Summarize top errors from the past 7 days."""
    from collections import Counter
    import glob

    error_counts: Counter = Counter()
    total = 0

    log_files = glob.glob(os.path.join(ERRORS_DIR, "*.jsonl"))
    for lf in sorted(log_files)[-7:]:  # last 7 files
        try:
            with open(lf) as f:
                for line in f:
                    entry = json.loads(line)
                    key = f"{entry.get('tool', '?')}: {entry.get('error', '?')[:60]}"
                    error_counts[key] += 1
                    total += 1
        except Exception:
            pass

    if total == 0:
        return "No tool errors in the past 7 days."

    top5 = error_counts.most_common(5)
    lines = [f"{count}x {err}" for err, count in top5]
    return f"Weekly Error Digest ({total} total errors)\n" + "\n".join(lines)
