"""Agent tools that expose captured activity + the user model to the chat agent."""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.agent.activity_tools import build_activity_tools
from pragya_assistant.connectors.browser_activity.store import (
    BrowserActivityEventStore,
    IngestedEvent,
)
from pragya_assistant.user_model.dreams import DreamStore, NewDream
from pragya_assistant.user_model.store import TraitSnapshot, UserModelStore

KEY = "browser_activity"


def _tool(tools: list, name: str):  # type: ignore[no-untyped-def]
    return next(t for t in tools if t.name == name)


async def test_recent_browsing_summarizes_signals(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    events = BrowserActivityEventStore(session_factory)
    await events.add_events(
        KEY,
        [
            IngestedEvent(client_id="s1", event_type="search", ts=dt.datetime(2026, 6, 20, 9),
                          data={"query": "flights to tokyo"}),
            IngestedEvent(client_id="r1", event_type="reading", ts=dt.datetime(2026, 6, 20, 10),
                          domain="medium.com", title="Best ryokans in Kyoto"),
        ],
    )
    tools = build_activity_tools(session_factory)
    out = await _tool(tools, "recent_browsing").handler({"days": 3650})
    assert "flights to tokyo" in out
    assert "ryokans" in out.lower() or "Kyoto" in out


async def test_recent_browsing_handles_empty(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tools = build_activity_tools(session_factory)
    out = await _tool(tools, "recent_browsing").handler({"days": 1})
    assert "no" in out.lower()


async def test_about_me_reports_opinions_and_dreams(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await UserModelStore(session_factory).write(
        [TraitSnapshot(trait="preference:payment", value="Apple Pay", confidence=0.8,
                       evidence=2, provenance=["browser"])]
    )
    dreams = DreamStore(session_factory)
    await dreams.add([NewDream(hypothesis="Planning a Japan trip", kind="foresight", confidence=0.6)])

    tools = build_activity_tools(session_factory)
    out = await _tool(tools, "about_me").handler({})
    assert "preference:payment" in out and "Apple Pay" in out
    assert "Japan trip" in out  # active dreams surfaced too
