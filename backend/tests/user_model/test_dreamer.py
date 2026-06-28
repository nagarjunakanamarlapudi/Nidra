"""The dreamer reads Opinions + the resolved-dream track record (in-context RSI)
and writes speculative Dreams — never user_model_snapshots."""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.user_model.dreamer import DreamerService, engine_dream_fn
from pragya_assistant.user_model.dreams import DreamStore, NewDream
from pragya_assistant.user_model.store import TraitSnapshot, UserModelStore

CANNED = (
    '{"dreams": [{"hypothesis": "Planning a Japan trip in spring", '
    '"kind": "foresight", "confidence": 0.6, "provenance": ["browser", "calendar"]}]}'
)


async def test_dreamer_writes_dreams_and_not_opinions(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    opinions = UserModelStore(session_factory)
    dreams = DreamStore(session_factory)
    await opinions.write(
        [TraitSnapshot(trait="preference:payment", value="Apple Pay", confidence=0.8, evidence=1)]
    )

    async def fake_complete(_prompt: str) -> str:
        return CANNED

    created = await DreamerService(opinions, dreams, fake_complete).dream()

    assert any("Japan trip" in d.hypothesis for d in created)
    assert any("Japan trip" in d.hypothesis for d in await dreams.active())
    # the dreamer must NOT have touched opinions
    model = await opinions.current_model()
    assert {s.trait for s in model} == {"preference:payment"}


async def test_engine_dream_fn_uses_the_agent_engine() -> None:
    """The dreamer can run on the configured agent brain (e.g. claude-code)."""

    class FakeEngine:
        def __init__(self) -> None:
            self.prompts: list[str] = []

        async def respond(self, history, user_text, *, effort=None):  # type: ignore[no-untyped-def]
            self.prompts.append(user_text)
            return CANNED, []

    engine = FakeEngine()
    out = await engine_dream_fn(engine)("dream on this")
    assert "Japan trip" in out
    assert engine.prompts == ["dream on this"]


async def test_dreamer_tolerates_insight_alias(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """gemma sometimes returns the connectedInsights/insight shape — accept it."""
    opinions = UserModelStore(session_factory)
    dreams = DreamStore(session_factory)
    aliased = (
        '{"connectedInsights": [{"insight": "Planning a trip to Japan", '
        '"confidence": 0.8, "fromSignals": ["browser", "calendar"]}]}'
    )

    async def fake(_prompt: str) -> str:
        return aliased

    created = await DreamerService(opinions, dreams, fake).dream()
    assert any("Planning a trip to Japan" in d.hypothesis for d in created)


async def test_dreamer_feeds_track_record_into_prompt(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """In-context RSI: prior resolved dreams + current opinions condition the next dream."""
    opinions = UserModelStore(session_factory)
    dreams = DreamStore(session_factory)
    await opinions.write(
        [TraitSnapshot(trait="decisiveness", value=0.8, confidence=0.7, evidence=5)]
    )
    await dreams.add([NewDream(hypothesis="Suggested a car upgrade", kind="need", confidence=0.5)])
    did = (await dreams.active())[0].id
    await dreams.resolve(did, status="confirmed", signal="acted", at=dt.datetime(2026, 6, 28))

    seen: dict[str, str] = {}

    async def capture(prompt: str) -> str:
        seen["prompt"] = prompt
        return CANNED

    await DreamerService(opinions, dreams, capture).dream()

    p = seen["prompt"]
    assert "decisiveness" in p  # current opinions are in context
    assert "Suggested a car upgrade" in p and "confirmed" in p  # the RSI track record is in context
