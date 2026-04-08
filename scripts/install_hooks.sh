#!/usr/bin/env bash
# Install Hermes git hooks into .git/hooks/
# Run once after cloning: bash scripts/install_hooks.sh
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"

cat > "$HOOKS_DIR/pre-commit" << 'EOF'
#!/usr/bin/env bash
# Hermes pre-commit: scan staged files for leaked secrets
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
SCANNER="$REPO_ROOT/scripts/scan_secrets.py"

if [ ! -f "$SCANNER" ]; then
  echo "pre-commit: scanner not found at $SCANNER, skipping"
  exit 0
fi

python3 "$SCANNER"
EOF

chmod +x "$HOOKS_DIR/pre-commit"
echo "✓ pre-commit hook installed at $HOOKS_DIR/pre-commit"
echo "  Staged files will be scanned for secrets before every commit."
