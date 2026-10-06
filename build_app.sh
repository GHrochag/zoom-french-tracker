#!/usr/bin/env bash
#
# Build Zoom French Tracker as a standalone macOS .app bundle.
# Output: dist/Zoom French Tracker.app
#
# Prerequisites: Python 3.9+ with tkinter
#   If using Homebrew Python: brew install python-tk
#   If using python.org Python: tkinter is included
#
# Usage:  bash build_app.sh

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

echo "══════════════════════════════════════════"
echo "  🇫🇷  Building Zoom French Tracker.app"
echo "══════════════════════════════════════════"

# ── Find Python ────────────────────────────────────────────
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
    echo "❌ Python 3.9+ required."
    exit 1
fi
echo "→ Python: $($PYTHON --version)"

# ── Check tkinter ──────────────────────────────────────────
if ! "$PYTHON" -c "import tkinter" 2>/dev/null; then
    echo "❌ tkinter not found."
    echo "   Install: brew install python-tk"
    echo "   Or use Python from https://python.org"
    exit 1
fi
echo "→ tkinter: ✓"

# ── Create venv ────────────────────────────────────────────
echo ""
echo "→ Creating virtual environment..."
VENV_DIR="$APP_DIR/.build_venv"
rm -rf "$VENV_DIR"
"$PYTHON" -m venv "$VENV_DIR"
VENV_PYTHON="$VENV_DIR/bin/python"

# ── Install dependencies ───────────────────────────────────
echo "→ Installing dependencies..."
"$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel 2>&1 | tail -1
"$VENV_PYTHON" -m pip install py2app rumps matplotlib 2>&1 | tail -3

# ── Clean previous builds ──────────────────────────────────
rm -rf build dist

# ── Build the .app ─────────────────────────────────────────
echo ""
echo "→ Building .app bundle (this takes ~1 minute)..."
"$VENV_PYTHON" setup.py py2app 2>&1 | grep -v "^creating\|^copying\|^byte-compiling"

# ── Verify output ──────────────────────────────────────────
APP_PATH="$APP_DIR/dist/Zoom French Tracker.app"
if [ -d "$APP_PATH" ]; then
    SIZE=$(du -sh "$APP_PATH" | cut -f1)
    echo ""
    echo "══════════════════════════════════════════"
    echo "  ✅ Build complete!"
    echo ""
    echo "  📦 $APP_PATH"
    echo "  📏 Size: $SIZE"
    echo ""
    echo "  💡 To install:"
    echo "     cp -r \"$APP_PATH\" ~/Applications/"
    echo ""
    echo "  🚀 Then double-click 'Zoom French Tracker'."
    echo "     The 🇫🇷 icon will appear in your menu bar."
    echo "══════════════════════════════════════════"
else
    echo "❌ Build failed — .app not found."
    exit 1
fi
