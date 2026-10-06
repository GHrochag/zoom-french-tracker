"""
Session duration logic for Zoom French Tracker.
Handles rounding rules and session lifecycle.
"""

import math
from datetime import datetime


def round_session(minutes: float) -> float:
    """
    Round session duration according to business rules:

    1. Sessions under 3 minutes are ignored (return 0).
    2. Duration is capped at 120 minutes (2 hours).
    3. Result is rounded to the nearest 0.5h increment.
    4. Any qualifying session counts as at least 0.5h.

    Examples:
        114 min → 2.0h    (1h54min, rounds to nearest 0.5 = 2.0)
        130 min → 2.0h    (capped at 120min)
        170 min → 2.0h    (capped at 120min)
        80 min  → 1.5h    (1h20min, rounds to nearest 0.5 = 1.5)
        14 min  → 0.5h    (minimum qualifying session)
    """
    if minutes < 3:
        return 0.0

    minutes = min(minutes, 120.0)
    hours = minutes / 60.0

    # Round to nearest 0.5 using floor(x*2 + 0.5)/2
    # This avoids Python's banker's rounding (round(2.5) = 2)
    rounded = math.floor(hours * 2 + 0.5) / 2.0

    # Any session that meets the 3-minute minimum counts as at least 0.5h
    return max(rounded, 0.5)


def compute_duration(start: datetime, end: datetime) -> tuple[float, float]:
    """
    Compute actual and rounded duration between two timestamps.

    Returns:
        (duration_minutes, rounded_hours)
    """
    delta = end - start
    minutes = delta.total_seconds() / 60.0
    rounded = round_session(minutes)
    return minutes, rounded


def format_duration(rounded_hours: float) -> str:
    """Format hours as a human-readable string."""
    if rounded_hours == 0:
        return "0h"
    hours = int(rounded_hours)
    frac = rounded_hours - hours
    if frac == 0:
        return f"{hours}h"
    elif frac == 0.5:
        return f"{hours}h 30m"
    return f"{rounded_hours}h"


def format_balance(hours: float) -> str:
    """Format remaining balance for menu bar display."""
    if hours == int(hours):
        return f"{int(hours)}h"
    return f"{hours:.1f}h"