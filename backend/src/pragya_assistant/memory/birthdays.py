"""Pure date logic for birthday recall (no DB), so it's trivially testable."""

from __future__ import annotations

import datetime as dt


def days_until_next_birthday(birthday: dt.date, today: dt.date) -> int:
    """Days from ``today`` to the next occurrence of the birthday's month/day.

    Returns 0 when the birthday is today. A Feb-29 birthday in a non-leap target
    year is treated as Feb 28.
    """
    candidate = _occurrence(today.year, birthday.month, birthday.day)
    if candidate < today:
        candidate = _occurrence(today.year + 1, birthday.month, birthday.day)
    return (candidate - today).days


def _occurrence(year: int, month: int, day: int) -> dt.date:
    try:
        return dt.date(year, month, day)
    except ValueError:
        # Only Feb 29 can be invalid for an otherwise-valid month/day; clamp it.
        return dt.date(year, month, 28)
