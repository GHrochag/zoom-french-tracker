# 🇫🇷 Zoom French Tracker

macOS menu bar app. Tracks your French class hours automatically — opens and closes with Zoom.

## How it works

1. Buy hours → input them into the app
2. Open Zoom for class → app auto-detects and starts tracking
3. Close Zoom → app calculates duration and deducts from balance
4. Alerts at 2h and 1h remaining

## One-command install

```bash
cd ~/Projects
git clone git@github.com:GHrochag/zoom-french-tracker.git
cd zoom-french-tracker
bash setup.sh
```

This builds a standalone `.app`, installs it to `~/Applications/`, and sets it to start on login. No terminal needed after that — just double-click the app.

**Prerequisite:** tkinter. If using Homebrew Python: `brew install python-tk`. Python from python.org includes it.

## Rules

| Rule | Value |
|------|-------|
| Detection | Automatic (Zoom open / close) |
| Minimum | 3 minutes |
| Rounding | Nearest 0.5h |
| Cap | 2.0h per session |
| Fractions | 0.5h only |
| Balance | Credits-based, no monthly reset |
| Alerts | 2h and 1h remaining |

## Data

All data stored locally in `~/.zoom_french_tracker/tracker.db` (SQLite).

## Uninstall

Delete from `~/Applications/` and remove `~/.zoom_french_tracker/`.
