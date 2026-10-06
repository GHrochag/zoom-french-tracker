# 🇫🇷 Zoom French Tracker

Menu bar app for macOS that automatically tracks your French class hours via Zoom.

## How it works

1. **You buy hours** → Input how many you purchased (e.g., 38h).
2. **You open Zoom for class** → App auto-detects it and starts tracking.
3. **You close Zoom** → App calculates the session duration and deducts from your balance.
4. **Alerts** → Get notified when only 2h or 1h remain so you never run out.

## Business rules

| Rule | Value |
|------|-------|
| Detection | Automatic (Zoom open / close) |
| Minimum session | 3 minutes |
| Rounding | Nearest 0.5h |
| Cap per session | 2.0h max |
| Fractions | Only 0.5h (never 5 or 10 min) |
| Balance | Credits-based (no monthly reset) |
| Alerts | At 2h and 1h remaining |

## Installation

```bash
cd zoom_french_tracker
bash setup.sh
```

This installs dependencies, creates a LaunchAgent, and starts the app.

## Requirements

- macOS (tested on Apple Silicon)
- Python 3.9+
- tkinter for calendar/graph windows (`brew install python-tk` if using Homebrew Python)

## Manual start (without LaunchAgent)

```bash
python3 zoom_tracker.py
```

## Usage

- **Menu bar**: Shows `🇫🇷 X.Xh` (your remaining balance)
- **Click icon** → Menu:
  - `➕ Agregar horas…` — Input newly purchased hours
  - `📅 Ver calendario` — Monthly calendar with colored days + history
  - `📊 Ver gráfico` — Bar chart of monthly consumption
  - `❌ Salir` — Quit the app

## Data storage

All data is stored locally in `~/.zoom_french_tracker/tracker.db` (SQLite).

## Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.nous.zoomfrenchtracker.plist
rm ~/Library/LaunchAgents/com.nous.zoomfrenchtracker.plist
rm -rf ~/.zoom_french_tracker
rm -rf zoom_french_tracker/
```