#!/usr/bin/env bash
#
# Zoom French Tracker — One-command setup.
#   bash setup.sh  →  builds .app + installs to ~/Applications + auto-start
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="Zoom French Tracker"

echo "══════════════════════════════════════════════"
echo "  🇫🇷  Zoom French Tracker — Setup"
echo "══════════════════════════════════════════════"

# Stop any running instance
pkill -f "Zoom French Tracker" 2>/dev/null || true
sleep 1

# Build the .app
bash "$SCRIPT_DIR/build_app.sh"

# Install to ~/Applications
echo ""
echo "→ Installing to ~/Applications..."
mkdir -p ~/Applications
rm -rf ~/Applications/"$APP_NAME.app"
cp -R "$SCRIPT_DIR/dist/$APP_NAME.app" ~/Applications/

# ── LaunchAgent for auto-start ──────────────────────────
PLIST="$HOME/Library/LaunchAgents/com.nous.zoomfrenchtracker.plist"
mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
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
    <true/>
</dict>
</plist>
PLIST

# Load the LaunchAgent
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST" 2>/dev/null || true

echo ""
echo "══════════════════════════════════════════════"
echo "  ✅  Instalado en ~/Applications/"
echo "  🔄  Se abre solo al iniciar tu Mac"
echo ""
echo "  🚀  Abriendo ahora..."
echo "══════════════════════════════════════════════"

open ~/Applications/"$APP_NAME.app"
