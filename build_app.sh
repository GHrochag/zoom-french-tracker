#!/usr/bin/env bash
#
# Build Zoom French Tracker .app — NO py2app.
# Creates a lightweight macOS .app that launches via shell script.
# Venv stays on disk — all PyObjC features work natively.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="Zoom French Tracker"
VENV_DIR="$SCRIPT_DIR/.venv"
APP_DIR="$SCRIPT_DIR/dist/$APP_NAME.app"

echo "══════════════════════════════════════════════"
echo "  🔨 Building $APP_NAME"
echo "══════════════════════════════════════════════"

# ── Venv ────────────────────────────────────────────
PYTHON="${PYTHON:-python3}"
echo "→ Python: $($PYTHON --version)"

if [ ! -d "$VENV_DIR" ]; then
    echo "→ Creating virtual environment..."
    "$PYTHON" -m venv "$VENV_DIR"
fi
VENV_PYTHON="$VENV_DIR/bin/python3"

echo "→ Installing dependencies..."
"$VENV_PYTHON" -m pip install --upgrade pip -q 2>&1 | tail -1
"$VENV_PYTHON" -m pip install rumps -q 2>&1 | tail -1

# ── Build .app ──────────────────────────────────────
echo "→ Building .app..."
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# Launcher script — uses absolute path to project dir (survives copy to ~/Applications)
cat > "$APP_DIR/Contents/MacOS/$APP_NAME" << EOF
#!$SCRIPT_DIR/.venv/bin/python3
import os, sys
sys.path.insert(0, "$SCRIPT_DIR")
os.execv("$SCRIPT_DIR/.venv/bin/python3", ["python3", "$SCRIPT_DIR/zoom_tracker.py"])
EOF
chmod +x "$APP_DIR/Contents/MacOS/$APP_NAME"

# Info.plist
cat > "$APP_DIR/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>Zoom French Tracker</string>
    <key>CFBundleIdentifier</key>
    <string>com.nous.zoomfrenchtracker</string>
    <key>CFBundleName</key>
    <string>Zoom French Tracker</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleIconFile</key>
    <string>icon</string>
    <key>LSUIElement</key>
    <true/>
</dict>
</plist>
PLIST

# Copy icon placeholder
if [ -f "$SCRIPT_DIR/icon.icns" ]; then
    cp "$SCRIPT_DIR/icon.icns" "$APP_DIR/Contents/Resources/"
fi

# ── Done ────────────────────────────────────────────
SIZE=$(du -sh "$APP_DIR" | cut -f1)
echo ""
echo "══════════════════════════════════════════════"
echo "  ✅ Build complete!"
echo ""
echo "  📦 $APP_DIR"
echo "  📏 Size: $SIZE"
echo ""
echo "  💡 Install:"
echo "     cp -r '$APP_DIR' ~/Applications/"
echo ""
echo "  🚀 Then double-click in Finder."
echo "══════════════════════════════════════════════"
