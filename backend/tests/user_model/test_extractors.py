"""Per-source extractors: browser (real seeded rows), finance + calendar (narrow
fakes), and a multi-source OpinionFormer run that fuses them."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.connectors.browser_activity.store import (
    BrowserActivityEventStore,
    IngestedEvent,
)
from pragya_assistant.user_model.extractors import (
    BrowserExtractor,
    CalendarExtractor,
    FinanceExtractor,
)
from pragya_assistant.user_model.opinions import OpinionFormer
from pragya_assistant.user_model.store import UserModelStore

KEY = "browser_activity"


class FakeSpending:
    def __init__(self, spend: dict[str, Decimal]) -> None:
        self._spend = spend

    async def spending_by_category(self, start: dt.date, end: dt.date) -> dict[str, Decimal]:
        return self._spend


class FakeEvents:
    def __init__(self, n: int) -> None:
        self._n = n

    async def events_between(self, key: str, start: dt.datetime, end: dt.datetime) -> list[object]:
        return [object()] * self._n


async def test_browser_extractor_from_real_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    events = BrowserActivityEventStore(session_factory)
    await events.add_events(
        KEY,
        [
            IngestedEvent(
                client_id="i1", event_type="interaction", ts=dt.datetime(2026, 6, 28, 9),
                data={"action": "choose", "group": "Payment methods", "value": "Apple Pay"},
                metrics={"latencyMs": 800},
            ),
            IngestedEvent(
                client_id="a1", event_type="action", ts=dt.datetime(2026, 6, 28, 9, 1),
                data={"milestone": "abandoned", "funnel": "checkout"},
            ),
        ],
    )
    traits = {t.trait: t for t in await BrowserExtractor(events).extract()}
    assert "decisiveness" not in traits  # time-on-page is not decisiveness
    assert traits["preference:payment"].value == "Apple Pay"
    assert traits["preference:payment"].provenance == ["browser"]
    assert traits["abandonment_rate"].derivation["event_ids"]  # evidence chain present


async def test_finance_extractor_top_category() -> None:
    ext = FinanceExtractor(
        FakeSpending({"Travel": Decimal("800"), "Groceries": Decimal("200")}),
        today=dt.date(2026, 6, 28),
    )
    traits = await ext.extract()
    assert traits[0].trait == "spend:top_category"
    assert traits[0].value == "Travel"
    assert traits[0].provenance == ["plaid"]


async def test_calendar_extractor_weekly_load() -> None:
    ext = CalendarExtractor(FakeEvents(28), today=dt.datetime(2026, 6, 28), window_days=28)
    traits = await ext.extract()
    assert traits[0].trait == "calendar:weekly_load"
    assert traits[0].value == 7.0  # 28 events / 4 weeks


async def test_opinion_former_fuses_three_sources(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    events = BrowserActivityEventStore(session_factory)
    await events.add_events(
        KEY,
        [
            IngestedEvent(
                client_id="i1", event_type="interaction", ts=dt.datetime(2026, 6, 28, 9),
                data={"action": "choose", "group": "Payment methods", "value": "Apple Pay"},
            )
        ],
    )
    model = UserModelStore(session_factory)
    formed = await OpinionFormer(
        [
            BrowserExtractor(events),
            FinanceExtractor(FakeSpending({"Travel": Decimal("500")}), today=dt.date(2026, 6, 28)),
            CalendarExtractor(FakeEvents(8), today=dt.datetime(2026, 6, 28)),
        ],
        model,
    ).form()
    traits = {t.trait for t in formed}
    assert {"preference:payment", "spend:top_category", "calendar:weekly_load"} <= traits
