#!/usr/bin/env bash
#
# Zoom French Tracker — Setup script for macOS
# Installs dependencies and creates a LaunchAgent for auto-start on login.
#
# Usage:  bash setup.sh

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_SRC="$APP_DIR/com.nous.zoomfrenchtracker.plist"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
PLIST_DST="$LAUNCH_AGENTS/com.nous.zoomfrenchtracker.plist"

echo "══════════════════════════════════════════════"
echo "  🇫🇷  Zoom French Tracker — Setup"
echo "══════════════════════════════════════════════"
echo ""

# ── Check Python ──────────────────────────────────────────────
echo "→ Checking Python..."
PYTHON=""
for py in python3 python; do
    if command -v "$py" &>/dev/null; then
        ver=$("$py" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 9 ]; then
            PYTHON="$py"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3.9+ required. Install from https://python.org or Homebrew."
    exit 1
fi
echo "   Using: $PYTHON ($($PYTHON --version))"

# ── Install pip dependencies ──────────────────────────────────
echo ""
echo "→ Installing Python dependencies..."
"$PYTHON" -m pip install --user -r "$APP_DIR/requirements.txt"

# ── Check for tkinter ─────────────────────────────────────────
echo ""
echo "→ Checking tkinter..."
if "$PYTHON" -c "import tkinter" 2>/dev/null; then
    echo "   ✓ tkinter available"
else
    echo "   ⚠ tkinter not found. Calendar/graph windows won't work."
    echo "     Install with: brew install python-tk"
    echo "     Or use Python from python.org (includes tkinter)."
fi

# ── Create LaunchAgent (auto-start on login) ──────────────────
echo ""
echo "→ Creating LaunchAgent for auto-start on login..."

mkdir -p "$LAUNCH_AGENTS"

cat > "$PLIST_SRC" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.nous.zoomfrenchtracker</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$APP_DIR/zoom_tracker.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$HOME/Library/Logs/zoomfrenchtracker.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/Library/Logs/zoomfrenchtracker.err</string>
</dict>
</plist>
PLIST

cp "$PLIST_SRC" "$PLIST_DST"

# Unload if already loaded, then load
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"

echo "   ✓ LaunchAgent installed and loaded"
echo "   Logs: ~/Library/Logs/zoomfrenchtracker.log"

# ── Done ──────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════"
echo "  ✅ Setup complete!"
echo ""
echo "  The app is now running in your menu bar."
echo "  Look for: 🇫🇷 (or ⚠️) in the top-right."
echo ""
echo "  💡 First steps:"
echo "     1. Click 🇫🇷 → Agregar horas…"
echo "     2. Enter how many hours you purchased"
echo "     3. Open Zoom for your class — tracking is automatic!"
echo ""
echo "  To stop:  launchctl unload $PLIST_DST"
echo "  To uninstall: launchctl unload $PLIST_DST && rm $PLIST_DST"
echo "══════════════════════════════════════════════"