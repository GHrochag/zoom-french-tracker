#!/usr/bin/env bash
#
# Zoom French Tracker — One-command setup for macOS.
# Builds the app and installs it to ~/Applications.
#
# Usage:  bash setup.sh

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

echo "══════════════════════════════════════════"
echo "  🇫🇷  Zoom French Tracker — Setup"
echo "══════════════════════════════════════════"
echo ""

# Build the .app
bash "$APP_DIR/build_app.sh"

# Install to ~/Applications
echo ""
echo "→ Installing to ~/Applications..."
mkdir -p ~/Applications
rm -rf ~/Applications/Zoom\ French\ Tracker.app
cp -R "$APP_DIR/dist/Zoom French Tracker.app" ~/Applications/

# Create LaunchAgent for auto-start on login
echo "→ Setting auto-start on login..."
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
PLIST="$LAUNCH_AGENTS/com.nous.zoomfrenchtracker.plist"
mkdir -p "$LAUNCH_AGENTS"

cat > "$PLIST" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.nous.zoomfrenchtracker</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/open</string>
        <string>-a</string>
        <string>$HOME/Applications/Zoom French Tracker.app</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
PLIST

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

# Launch now
open ~/Applications/Zoom\ French\ Tracker.app

echo ""
echo "══════════════════════════════════════════"
echo "  ✅ Done! Look for 🇫🇷 in your menu bar."
echo ""
echo "  💡 First steps:"
echo "     1. Click 🇫🇷 → Agregar horas…"
echo "     2. Input your purchased hours"
echo "     3. Open Zoom — tracking is automatic!"
echo ""
echo "  🔄 The app auto-starts on login."
echo "  🗑  To uninstall: delete from ~/Applications/"
echo "══════════════════════════════════════════"