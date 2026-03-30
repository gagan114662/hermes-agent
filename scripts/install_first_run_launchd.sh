#!/bin/bash
# Creates a launchd entry that runs first_run.py once at login
# Safe to run multiple times — first_run.py is idempotent
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$SCRIPT_DIR/../venv/bin/python3"
FIRST_RUN_SCRIPT="$SCRIPT_DIR/first_run.py"

PLIST_PATH="$HOME/Library/LaunchAgents/ai.hermes.first-run.plist"
cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>ai.hermes.first-run</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$FIRST_RUN_SCRIPT</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>StandardOutPath</key><string>$HOME/.hermes/first_run.log</string>
    <key>StandardErrorPath</key><string>$HOME/.hermes/first_run.log</string>
</dict>
</plist>
EOF

launchctl load "$PLIST_PATH" 2>/dev/null || true
echo "First run launchd entry installed at: $PLIST_PATH"
