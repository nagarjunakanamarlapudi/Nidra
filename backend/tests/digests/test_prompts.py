"""Tests for digest prompt builders."""

from pragya_assistant.agent.prompts import build_digest_prompt, build_weekly_finance_prompt


def test_daily_digest_mentions_finance() -> None:
    p = build_digest_prompt("2026-06-21")
    assert "balance" in p.lower() or "bills" in p.lower()


def test_weekly_finance_prompt() -> None:
    p = build_weekly_finance_prompt("2026-06-21")
    assert "spending" in p.lower() and "2026-06-21" in p
