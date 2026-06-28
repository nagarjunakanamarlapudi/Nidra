"""The OpinionFormer orchestrates per-source extractors into one user model,
merging the same trait across sources (corroboration → union provenance, summed
evidence, boosted confidence)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.user_model.opinions import OpinionFormer
from pragya_assistant.user_model.store import TraitSnapshot, UserModelStore


class FakeExtractor:
    def __init__(self, source: str, snaps: list[TraitSnapshot]) -> None:
        self.source = source
        self._snaps = snaps

    async def extract(self) -> list[TraitSnapshot]:
        return self._snaps


async def test_form_merges_same_trait_across_sources(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    model = UserModelStore(session_factory)
    browser = FakeExtractor(
        "browser",
        [TraitSnapshot("interest:travel", value=0.7, confidence=0.6, evidence=3, provenance=["browser"],
                       derivation={"formula": "browser reads", "event_ids": [1, 2, 3]})],
    )
    plaid = FakeExtractor(
        "plaid",
        [TraitSnapshot("interest:travel", value="high", confidence=0.5, evidence=2, provenance=["plaid"],
                       derivation={"formula": "travel spend", "event_ids": [9]})],
    )
    cal = FakeExtractor(
        "calendar",
        [TraitSnapshot("routine:mornings", value=True, confidence=0.8, evidence=5, provenance=["calendar"])],
    )

    formed = await OpinionFormer([browser, plaid, cal], model).form()
    by = {s.trait: s for s in formed}

    assert set(by) == {"interest:travel", "routine:mornings"}
    travel = by["interest:travel"]
    assert set(travel.provenance) == {"browser", "plaid"}  # corroborated across sources
    assert travel.evidence == 5  # 3 + 2
    assert travel.confidence >= 0.6  # boosted (or at least the max)
    # the merged opinion keeps every source's evidence chain
    assert len(travel.derivation["sources"]) == 2
    # persisted to the user model
    assert {s.trait for s in await model.current_model()} == {"interest:travel", "routine:mornings"}
