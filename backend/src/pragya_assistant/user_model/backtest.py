"""Backtest harness — the dreamer's cold start + offline benchmark.

Dream as-of a past cutoff T using ONLY signals <= T (reconstruct the belief state
at T — no look-ahead leakage), then verify each dream by CORROBORATION against
real activity in (T, T+horizon]. There is no intervention in history, so the only
available verifier is corroboration; this measures PREDICTIVENESS, not lift. The
live loop is still required for intervention effect.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

# Injected seams (async where they hit the DB / LLM).
SignalsBefore = Callable[[dt.datetime], Awaitable[list[Any]]]
SignalsBetween = Callable[[dt.datetime, dt.datetime], Awaitable[list[Any]]]
OpinionFn = Callable[[list[Any]], Awaitable[list[Any]]]
DreamFn = Callable[[list[Any]], Awaitable[list[str]]]
Corroborates = Callable[[str, Any], bool]


def _tokens(text: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", text.lower()) if len(w) >= 4}


def keyword_corroborates(hypothesis: str, text: str) -> bool:
    """Default corroboration matcher: any significant token shared between the
    dream and a later signal. Deliberately simple; swap in embeddings later."""
    return bool(_tokens(hypothesis) & _tokens(text))


@dataclass(frozen=True)
class BacktestResult:
    cutoff: dt.datetime
    dreams: list[str]
    corroborated: list[str]
    hit_rate: float  # corroborated / dreams (predictiveness, not lift)


class Backtester:
    def __init__(
        self,
        *,
        signals_before: SignalsBefore,
        signals_between: SignalsBetween,
        opinion_fn: OpinionFn,
        dream_fn: DreamFn,
        corroborates: Corroborates = keyword_corroborates,
    ) -> None:
        self._signals_before = signals_before
        self._signals_between = signals_between
        self._opinion_fn = opinion_fn
        self._dream_fn = dream_fn
        self._corroborates = corroborates

    async def run(self, *, cutoff: dt.datetime, horizon: dt.timedelta) -> BacktestResult:
        past = await self._signals_before(cutoff)  # <= T only — no look-ahead
        opinions = await self._opinion_fn(past)
        dreams = await self._dream_fn(opinions)
        future = await self._signals_between(cutoff, cutoff + horizon)  # (T, T+horizon]
        corroborated = [d for d in dreams if any(self._corroborates(d, e) for e in future)]
        hit_rate = round(len(corroborated) / len(dreams), 2) if dreams else 0.0
        return BacktestResult(
            cutoff=cutoff, dreams=dreams, corroborated=corroborated, hit_rate=hit_rate
        )
