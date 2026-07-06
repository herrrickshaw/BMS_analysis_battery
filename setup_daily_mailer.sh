#!/bin/bash
# Setup Daily Mailer Launchd Service
# ============================================================================
# Install the daily mailer to run every day at 8:30 AM

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_SRC="$SCRIPT_DIR/com.screener.daily-mailer.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.screener.daily-mailer.plist"
LOG_DIR="$HOME/.screener"

echo "=========================================="
echo "Daily Mailer Setup"
echo "=========================================="
echo ""

# Create log directory
mkdir -p "$LOG_DIR"
chmod 755 "$LOG_DIR"
echo "✓ Log directory created: $LOG_DIR"

# Copy plist to LaunchAgents
mkdir -p "$HOME/Library/LaunchAgents"
cp "$PLIST_SRC" "$PLIST_DEST"
chmod 644 "$PLIST_DEST"
echo "✓ Plist installed: $PLIST_DEST"

# Load the launchd job
launchctl load "$PLIST_DEST" 2>/dev/null || {
    echo "  Note: Job may already be loaded. To reload, run:"
    echo "    launchctl unload '$PLIST_DEST'"
    echo "    launchctl load '$PLIST_DEST'"
}
echo "✓ Launchd job loaded"

# Verify installation
if launchctl list | grep -q "com.screener.daily-mailer"; then
    echo "✓ Service is active"
else
    echo "✗ Service not active (may require restart)"
fi

echo ""
echo "=========================================="
echo "SETUP COMPLETE"
echo "=========================================="
echo ""
echo "The daily mailer is scheduled to run every day at 8:30 AM."
echo ""
echo "Before first run, set the Gmail app password:"
echo "  launchctl setenv DAILY_MAILER_PASSWORD 'your-16-char-app-password'"
echo ""
echo "Get your Gmail app password:"
echo "  1. Go to https://myaccount.google.com/apppasswords"
echo "  2. Select Mail and macOS"
echo "  3. Copy the 16-character password"
echo "  4. Run the launchctl setenv command above"
echo ""
echo "To test the mailer manually:"
echo "  python3 $SCRIPT_DIR/daily_mailer.py --preview"
echo ""
echo "To view logs:"
echo "  tail -f $LOG_DIR/daily_mailer_*.log"
echo ""
echo "To uninstall:"
echo "  launchctl unload '$PLIST_DEST'"
echo "  rm '$PLIST_DEST'"
echo ""
