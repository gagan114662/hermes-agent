#!/bin/bash
# Build Hermes.dmg — drag-to-install macOS installer
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
APP="$SCRIPT_DIR/Hermes.app"
DIST="$REPO_ROOT/dist"
DMG_NAME="Hermes"
VERSION="${1:-1.0.0}"
OUTPUT="$DIST/${DMG_NAME}-${VERSION}.dmg"

mkdir -p "$DIST"

echo "Building $OUTPUT..."

# Remove old DMG if exists
rm -f "$OUTPUT"

create-dmg \
    --volname "Hermes" \
    --volicon "$APP/Contents/Resources/hermes.icns" \
    --window-pos 200 120 \
    --window-size 600 400 \
    --icon-size 100 \
    --icon "Hermes.app" 150 180 \
    --hide-extension "Hermes.app" \
    --app-drop-link 450 180 \
    --no-internet-enable \
    "$OUTPUT" \
    "$APP"

echo ""
echo "✓ Built: $OUTPUT"
echo "  Size: $(du -sh "$OUTPUT" | cut -f1)"
echo ""
echo "To distribute: upload $OUTPUT to your website or S3"
