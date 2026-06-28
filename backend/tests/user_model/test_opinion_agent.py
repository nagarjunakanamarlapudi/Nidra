"""Query tools feed an evidence ledger; the ledger is the citable universe."""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.agent.tools import Tool
from pragya_assistant.connectors.browser_activity.store import (
    BrowserActivityEventStore,
    IngestedEvent,
)
from pragya_assistant.user_model.opinion_agent import (
    EvidenceLedger,
    build_query_tools,
    parse_proposed_opinions,
)

KEY = "browser_activity"


def _tool(tools: list[Tool], name: str) -> Tool:
    return next(t for t in tools if t.name == name)


def test_ledger_assigns_ids_and_dedups() -> None:
    from pragya_assistant.user_model.facts import Fact

    led = EvidenceLedger()
    out = led.record([Fact("browser", "search", "a", event_ids=[1])])
    assert out[0].id == "f1" and led.facts[0].id == "f1"
    out2 = led.record([Fact("browser", "search", "b", event_ids=[2])])
    assert out2[0].id == "f2" and len(led.facts) == 2


async def test_query_browsing_tool_populates_ledger(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    events = BrowserActivityEventStore(session_factory)
    await events.add_events(
        KEY,
        [IngestedEvent(client_id="s1", event_type="search", ts=dt.datetime(2026, 6, 20, 9),
                       data={"query": "flights to tokyo"})],
    )
    led = EvidenceLedger()
    tools = build_query_tools(led, browser=events, now=dt.datetime(2026, 6, 27, 12))
    out = await _tool(tools, "query_browsing").handler({"days": 30})
    assert "flights to tokyo" in out and "f1" in out      # observation cites the ledger id
    assert led.facts and led.facts[0].summary.startswith("searched")


def test_parse_proposed_opinions_tolerates_garbage() -> None:
    text = ('{"opinions": [{"trait": "", "value": 1, "evidence_fact_ids": ["f1"]},'
            '{"trait": "intent:travel", "value": "Tokyo", "confidence": 0.9, '
            '"evidence_fact_ids": ["f1"]}]}')
    ops = parse_proposed_opinions(text)
    assert len(ops) == 1
    assert ops[0].trait == "intent:travel" and ops[0].evidence_fact_ids == ["f1"]


def test_parse_proposed_opinions_drops_null_value_and_clamps_confidence() -> None:
    text = ('{"opinions": ['
            '{"trait": "intent:travel", "value": null, "confidence": 0.8, '
            '"evidence_fact_ids": ["f1"]},'
            '{"trait": "interest:rust", "value": "rust", "confidence": "high", '
            '"evidence_fact_ids": [2]}'
            ']}')
    ops = parse_proposed_opinions(text)
    assert len(ops) == 1
    assert ops[0].trait == "interest:rust"
    assert ops[0].confidence == 0.0          # unparseable confidence -> 0.0
    assert ops[0].evidence_fact_ids == ["2"]  # int id coerced to str


def test_parse_proposed_opinions_empty_on_garbage_text() -> None:
    assert parse_proposed_opinions("not json at all") == []
