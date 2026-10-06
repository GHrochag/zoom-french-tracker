"""
py2app setup script for Zoom French Tracker.
Builds a standalone .app bundle for macOS — no Terminal needed.
"""
from setuptools import setup

APP = ["zoom_tracker.py"]
DATA_FILES = []
OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "CFBundleName": "Zoom French Tracker",
        "CFBundleDisplayName": "Zoom French Tracker",
        "CFBundleIdentifier": "com.nous.zoomfrenchtracker",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "LSUIElement": True,  # Menu bar only — no Dock icon
        "NSHighResolutionCapable": True,
    },
    "packages": ["rumps", "matplotlib", "tkinter"],
    "includes": ["db", "session_tracker"],
    "excludes": ["wx", "PyQt5", "PyQt6", "PySide2", "PySide6", "tkinter.test"],
    "site_packages": True,
}

setup(
    name="Zoom French Tracker",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
