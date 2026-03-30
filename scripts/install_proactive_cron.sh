#!/bin/bash
# Install the proactive loop cron job (runs every 15 minutes)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$SCRIPT_DIR/../venv/bin/python3"
LOOP_SCRIPT="$SCRIPT_DIR/proactive_loop.py"
LOG_FILE="$HOME/.hermes/proactive_loop.log"

CRON_LINE="*/15 * * * * $PYTHON $LOOP_SCRIPT >> $LOG_FILE 2>&1"

# Remove any existing entry, add new one
(crontab -l 2>/dev/null | grep -v "proactive_loop.py"; echo "$CRON_LINE") | crontab -
echo "Proactive loop cron installed: runs every 15 minutes"
echo "Logs: $LOG_FILE"
