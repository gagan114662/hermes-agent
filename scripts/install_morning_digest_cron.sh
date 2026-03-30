#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$SCRIPT_DIR/../venv/bin/python3"
DIGEST_SCRIPT="$SCRIPT_DIR/morning_digest.py"
LOG_FILE="$HOME/.hermes/morning_digest.log"

CRON_LINE="0 8 * * * $PYTHON $DIGEST_SCRIPT >> $LOG_FILE 2>&1"
(crontab -l 2>/dev/null | grep -v "morning_digest.py"; echo "$CRON_LINE") | crontab -
echo "Morning digest cron installed: runs at 8am daily"
echo "Logs: $LOG_FILE"
