"""Per-source grounded trait extractors feeding the OpinionFormer.

Each implements the SourceExtractor protocol (a ``source`` tag + ``extract()``)
and depends on a NARROW slice of its connector's store, so it's testable with a
fake and the real store satisfies it structurally. All traits are grounded in
real signals, with source-level provenance.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, Protocol

from pragya_assistant.connectors.browser_activity.derive import compute_browser_traits
from pragya_assistant.connectors.browser_activity.store import BrowserActivityEventStore
from pragya_assistant.user_model.store import TraitSnapshot


class BrowserExtractor:
    """Decision-style traits from browser interaction/action signals."""

    source = "browser"

    def __init__(
        self, events: BrowserActivityEventStore, *, connector_key: str = "browser_activity"
    ) -> None:
        self._events = events
        self._key = connector_key

    async def extract(self) -> list[TraitSnapshot]:
        rows = await self._events.recent(
            self._key, types=["interaction", "impression", "action"], limit=500
        )
        return compute_browser_traits(rows)


class _SpendingSource(Protocol):
    async def spending_by_category(self, start: dt.date, end: dt.date) -> dict[str, Decimal]: ...


class FinanceExtractor:
    """Spending-shape traits from Plaid transactions."""

    source = "plaid"

    def __init__(self, store: _SpendingSource, *, today: dt.date, window_days: int = 30) -> None:
        self._store = store
        self._today = today
        self._window = window_days

    async def extract(self) -> list[TraitSnapshot]:
        spend = await self._store.spending_by_category(
            self._today - dt.timedelta(days=self._window), self._today
        )
        if not spend:
            return []
        total = sum(spend.values()) or Decimal(1)
        top, top_amt = max(spend.items(), key=lambda kv: kv[1])
        concentration = float(top_amt) / float(total)
        return [
            TraitSnapshot(
                trait="spend:top_category",
                value=top,
                confidence=round(min(1.0, concentration), 2),
                evidence=len(spend),
                provenance=["plaid"],
            )
        ]


class _EventsSource(Protocol):
    async def events_between(
        self, connector_key: str, start: dt.datetime, end: dt.datetime
    ) -> list[Any]: ...


class CalendarExtractor:
    """Routine/load traits from calendar events."""

    source = "calendar"

    def __init__(
        self,
        store: _EventsSource,
        *,
        today: dt.datetime,
        window_days: int = 28,
        connector_key: str = "google_calendar",
    ) -> None:
        self._store = store
        self._today = today
        self._window = window_days
        self._key = connector_key

    async def extract(self) -> list[TraitSnapshot]:
        events = await self._store.events_between(
            self._key, self._today - dt.timedelta(days=self._window), self._today
        )
        if not events:
            return []
        weeks = max(1, self._window // 7)
        per_week = round(len(events) / weeks, 1)
        return [
            TraitSnapshot(
                trait="calendar:weekly_load",
                value=per_week,
                confidence=round(min(1.0, len(events) / 20), 2),
                evidence=len(events),
                provenance=["calendar"],
            )
        ]
