"""The user-model store persists derived trait snapshots (append-only) and
reads back the current model as the latest row per trait."""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.connectors.browser_activity.user_model import (
    TraitSnapshot,
    UserModelStore,
)


async def test_write_and_current_model_returns_latest_per_trait(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = UserModelStore(session_factory)
    # Two snapshots of the same trait at different times → newest wins.
    await store.write(
        [
            TraitSnapshot(
                trait="decisiveness",
                value=0.4,
                confidence=0.5,
                evidence=2,
                provenance=["interaction"],
                computed_at=dt.datetime(2026, 6, 20, 9),
            )
        ]
    )
    await store.write(
        [
            TraitSnapshot(
                trait="decisiveness",
                value=0.8,
                confidence=0.7,
                evidence=5,
                provenance=["interaction", "action"],
                computed_at=dt.datetime(2026, 6, 27, 9),
            ),
            TraitSnapshot(
                trait="preference:payment",
                value="Apple Pay",
                confidence=0.9,
                evidence=3,
                provenance=["interaction"],
                computed_at=dt.datetime(2026, 6, 27, 9),
            ),
        ]
    )

    current = await store.current_model()
    by_trait = {s.trait: s for s in current}
    assert set(by_trait) == {"decisiveness", "preference:payment"}
    assert by_trait["decisiveness"].value == 0.8  # latest, not the 0.4 snapshot
    assert by_trait["preference:payment"].value == "Apple Pay"


async def test_history_is_preserved(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = UserModelStore(session_factory)
    for i, v in enumerate((0.2, 0.5, 0.9)):
        await store.write(
            [
                TraitSnapshot(
                    trait="decisiveness",
                    value=v,
                    confidence=0.6,
                    evidence=i + 1,
                    provenance=["interaction"],
                    computed_at=dt.datetime(2026, 6, 20 + i, 9),
                )
            ]
        )
    history = await store.history("decisiveness")
    assert [s.value for s in history] == [0.2, 0.5, 0.9]  # oldest → newest, all kept
