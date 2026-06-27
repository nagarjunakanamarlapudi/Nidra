"""Backtest harness: dream as-of a past cutoff T (signals <= T only), verify by
corroboration against real activity in (T, T+horizon]. The cold-start + offline
benchmark. No look-ahead leakage; corroboration-only (no intervention in history)."""

from __future__ import annotations

import datetime as dt

from pragya_assistant.user_model.backtest import Backtester, keyword_corroborates


def test_keyword_corroborates() -> None:
    assert keyword_corroborates("Planning a Japan trip", "booked a Japan trip hotel")
    assert not keyword_corroborates("Buying a new laptop", "booked a Japan trip hotel")


async def test_backtest_point_in_time_and_corroboration() -> None:
    T = dt.datetime(2026, 6, 15)
    horizon = dt.timedelta(days=14)
    seen: dict[str, object] = {}

    async def signals_before(t: dt.datetime) -> list[dict[str, str]]:
        seen["before"] = t
        return [{"text": "flights to tokyo"}, {"text": "kyoto ryokan"}]

    async def signals_between(a: dt.datetime, b: dt.datetime) -> list[dict[str, str]]:
        seen["between"] = (a, b)
        return [{"text": "booked a Japan trip hotel"}]

    async def opinion_fn(sigs: list[dict[str, str]]) -> list[str]:
        return ["interest: Japan travel"]

    async def dream_fn(opinions: list[str]) -> list[str]:
        return ["Planning a Japan trip", "Buying a new laptop"]

    def corroborates(hyp: str, sig: dict[str, str]) -> bool:
        return keyword_corroborates(hyp, sig["text"])

    res = await Backtester(
        signals_before=signals_before,
        signals_between=signals_between,
        opinion_fn=opinion_fn,
        dream_fn=dream_fn,
        corroborates=corroborates,
    ).run(cutoff=T, horizon=horizon)

    assert "Planning a Japan trip" in res.corroborated
    assert "Buying a new laptop" not in res.corroborated
    assert res.hit_rate == 0.5
    # point-in-time discipline: opinions from <= T, verification from (T, T+horizon]
    assert seen["before"] == T
    assert seen["between"] == (T, T + horizon)
