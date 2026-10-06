"""
py2app setup script for Zoom French Tracker.
Builds a standalone .app bundle for macOS.
"""
from setuptools import setup

APP = ["zoom_tracker.py"]
DATA_FILES = []
OPTIONS = {
    "argv_emulation": True,
    "plist": {
        "LSUIElement": True,
        "CFBundleName": "Zoom French Tracker",
        "CFBundleIdentifier": "com.nous.zoomfrenchtracker",
    },
    "packages": ["rumps"],
    "includes": ["db", "session_tracker"],
    "excludes": ["tkinter", "matplotlib", "PyQt5", "PyQt6"],
}

setup(
    name="Zoom French Tracker",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
