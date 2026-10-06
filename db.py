"""
Database module for Zoom French Tracker.
SQLite-based storage for sessions, credits, and settings.
"""

import sqlite3
import os
from datetime import datetime
from pathlib import Path

DB_DIR = Path.home() / ".zoom_french_tracker"
DB_PATH = DB_DIR / "tracker.db"


def _get_conn():
    """Get a database connection with row factory."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = _get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time TEXT NOT NULL,
            end_time TEXT,
            duration_minutes REAL,
            rounded_hours REAL,
            status TEXT NOT NULL DEFAULT 'active'
        );

        CREATE TABLE IF NOT EXISTS credits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL CHECK(amount > 0),
            added_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            note TEXT
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """
    )
    conn.commit()
    conn.close()


# ── Session CRUD ──────────────────────────────────────────────


def start_session(start_time: datetime) -> int:
    """Record a new active session. Returns session ID."""
    conn = _get_conn()
    cursor = conn.execute(
        "INSERT INTO sessions (start_time, status) VALUES (?, 'active')",
        (start_time.strftime("%Y-%m-%d %H:%M:%S"),),
    )
    conn.commit()
    sid = cursor.lastrowid
    conn.close()
    return sid


def end_session(
    session_id: int, end_time: datetime, duration_minutes: float, rounded_hours: float
):
    """Complete a session with its calculated duration."""
    conn = _get_conn()
    conn.execute(
        """UPDATE sessions
           SET end_time = ?, duration_minutes = ?, rounded_hours = ?, status = 'completed'
           WHERE id = ?""",
        (
            end_time.strftime("%Y-%m-%d %H:%M:%S"),
            round(duration_minutes, 1),
            rounded_hours,
            session_id,
        ),
    )
    conn.commit()
    conn.close()


def cancel_session(session_id: int):
    """Mark a session as cancelled (e.g., orphaned or under minimum)."""
    conn = _get_conn()
    conn.execute(
        "UPDATE sessions SET status = 'cancelled' WHERE id = ?", (session_id,)
    )
    conn.commit()
    conn.close()


def get_active_session() -> dict | None:
    """Return the currently active session, if any."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM sessions WHERE status = 'active' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_month_sessions(year: int, month: int) -> list[dict]:
    """Return all completed sessions for a given month."""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT * FROM sessions
           WHERE status = 'completed'
             AND strftime('%Y', start_time) = ?
             AND strftime('%m', start_time) = ?
           ORDER BY start_time DESC""",
        (str(year), f"{month:02d}"),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_completed_sessions() -> list[dict]:
    """Return all completed sessions, newest first."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM sessions WHERE status = 'completed' ORDER BY start_time DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_daily_hours(year: int, month: int) -> dict[int, float]:
    """Return {day: total_hours} for a given month."""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT CAST(strftime('%d', start_time) AS INTEGER) AS day,
                  SUM(rounded_hours) AS total
           FROM sessions
           WHERE status = 'completed'
             AND strftime('%Y', start_time) = ?
             AND strftime('%m', start_time) = ?
           GROUP BY day""",
        (str(year), f"{month:02d}"),
    ).fetchall()
    conn.close()
    return {r["day"]: r["total"] for r in rows}


# ── Credits CRUD ──────────────────────────────────────────────


def add_credits(amount: float, note: str = "") -> int:
    """Add purchased hours. Returns credit ID."""
    conn = _get_conn()
    cursor = conn.execute(
        "INSERT INTO credits (amount, note) VALUES (?, ?)",
        (amount, note),
    )
    conn.commit()
    cid = cursor.lastrowid
    conn.close()
    return cid


def get_total_credits() -> float:
    """Sum of all purchased hours."""
    conn = _get_conn()
    row = conn.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM credits").fetchone()
    conn.close()
    return row["total"]


def get_total_consumed() -> float:
    """Sum of all consumed (rounded) hours from completed sessions."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT COALESCE(SUM(rounded_hours), 0) AS total FROM sessions WHERE status = 'completed'"
    ).fetchone()
    conn.close()
    return row["total"]


def get_balance() -> float:
    """Credits purchased minus hours consumed."""
    return get_total_credits() - get_total_consumed()


def get_credit_history() -> list[dict]:
    """All credit additions, newest first."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM credits ORDER BY added_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Settings ──────────────────────────────────────────────────


def get_setting(key: str, default: str = "") -> str:
    conn = _get_conn()
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?", (key,)
    ).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
    )
    conn.commit()
    conn.close()


# ── Stats ─────────────────────────────────────────────────────


def get_summary() -> dict:
    """Return a summary dict for the menu bar / dashboard."""
    return {
        "balance": get_balance(),
        "total_purchased": get_total_credits(),
        "total_consumed": get_total_consumed(),
        "total_sessions": _count_completed(),
    }


def _count_completed() -> int:
    conn = _get_conn()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM sessions WHERE status = 'completed'"
    ).fetchone()
    conn.close()
    return row["n"]


def get_monthly_hours_breakdown(year: int = None) -> list[dict]:
    """Return monthly consumption: [{year, month, hours}, ...]."""
    conn = _get_conn()
    rows = conn.execute(
        """SELECT strftime('%Y', start_time) AS year,
                  strftime('%m', start_time) AS month,
                  SUM(rounded_hours) AS hours
           FROM sessions
           WHERE status = 'completed'
           GROUP BY year, month
           ORDER BY year, month"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]