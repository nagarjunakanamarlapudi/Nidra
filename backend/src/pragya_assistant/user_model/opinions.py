"""The OpinionFormer — forms the user model from MANY sources.

Each source (browser, calendar, gmail, plaid, …) contributes a SourceExtractor
that emits grounded TraitSnapshots with its own provenance. The former merges the
same trait across sources — corroboration unions provenance, sums evidence, and
boosts confidence — then persists the result. Opinions are real-signal-only; the
dreamer reads them but never writes here.
"""

from __future__ import annotations

from typing import Protocol

from pragya_assistant.user_model.store import TraitSnapshot, UserModelStore


class SourceExtractor(Protocol):
    """A per-source grounded trait extractor."""

    source: str

    async def extract(self) -> list[TraitSnapshot]: ...


def _merge_by_trait(snaps: list[TraitSnapshot]) -> list[TraitSnapshot]:
    groups: dict[str, list[TraitSnapshot]] = {}
    for s in snaps:
        groups.setdefault(s.trait, []).append(s)

    merged: list[TraitSnapshot] = []
    for trait, group in groups.items():
        rep = max(group, key=lambda s: (s.confidence, s.evidence))  # representative value
        provenance = sorted({p for s in group for p in (s.provenance or [])})
        evidence = sum(s.evidence for s in group)
        n_sources = max(1, len(provenance))
        # corroboration across sources nudges confidence up, capped at 1.0
        confidence = min(1.0, round(rep.confidence + 0.1 * (n_sources - 1), 2))
        merged.append(
            TraitSnapshot(
                trait=trait,
                value=rep.value,
                confidence=confidence,
                evidence=evidence,
                provenance=provenance,
            )
        )
    return merged


class OpinionFormer:
    def __init__(self, extractors: list[SourceExtractor], model: UserModelStore) -> None:
        self._extractors = extractors
        self._model = model

    async def form(self) -> list[TraitSnapshot]:
        collected: list[TraitSnapshot] = []
        for extractor in self._extractors:
            collected.extend(await extractor.extract())
        merged = _merge_by_trait(collected)
        await self._model.write(merged)
        return merged
