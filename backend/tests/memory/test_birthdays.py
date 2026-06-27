import datetime as dt

from pragya_assistant.memory.birthdays import days_until_next_birthday


def test_birthday_later_this_year() -> None:
    assert days_until_next_birthday(dt.date(1990, 3, 10), today=dt.date(2026, 3, 1)) == 9


def test_birthday_today_is_zero() -> None:
    assert days_until_next_birthday(dt.date(1990, 6, 20), today=dt.date(2026, 6, 20)) == 0


def test_birthday_already_passed_wraps_to_next_year() -> None:
    # birthday was Jan 2; today is Dec 30 2026 -> next is Jan 2 2027 = 3 days
    assert days_until_next_birthday(dt.date(1990, 1, 2), today=dt.date(2026, 12, 30)) == 3


def test_feb29_birthday_in_non_leap_year_clamps_to_feb28() -> None:
    # 2026 is not a leap year; next occurrence treated as Feb 28
    assert days_until_next_birthday(dt.date(2000, 2, 29), today=dt.date(2026, 2, 20)) == 8
