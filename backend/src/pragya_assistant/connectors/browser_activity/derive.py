"""Derive durable user-model traits from the stored decision substrate.

Server-side counterpart to the extension's opinions layer: reads recent
interaction/action events and distills decision-style traits + preferences into
``UserModelSnapshot`` rows. Deterministic and append-only, so the model can be
recomputed any time and its evolution tracked.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pragya_assistant.connectors.browser_activity.store import BrowserActivityEventStore
from pragya_assistant.user_model.store import TraitSnapshot, UserModelStore

if TYPE_CHECKING:
    from pragya_assistant.memory.models import BrowserActivityEvent

_PAYMENT_GROUP = re.compile(r"payment", re.I)


def _num(x: object) -> float | None:
    return float(x) if isinstance(x, int | float) and not isinstance(x, bool) and x >= 0 else None


def compute_browser_traits(rows: list[BrowserActivityEvent]) -> list[TraitSnapshot]:
    """Pure: distill decision-style traits from browser interaction/action rows.
    Shared by UserModelDeriver and the multi-source BrowserExtractor. Provenance
    is source-level (``browser``) so cross-source merge groups it cleanly."""
    interactions = [r for r in rows if r.event_type == "interaction"]
    actions = [r for r in rows if r.event_type == "action"]
    snaps: list[TraitSnapshot] = []

    # Decisiveness: fast decisions → high (normalized over an 8s ceiling).
    lat = [v for r in interactions if (v := _num((r.metrics or {}).get("latencyMs"))) is not None]
    if lat:
        avg = sum(lat) / len(lat)
        snaps.append(
            TraitSnapshot(
                trait="decisiveness",
                value=round(1 - min(1.0, avg / 8000), 2),
                confidence=round(min(1.0, len(lat) / 5), 2),
                evidence=len(lat),
                provenance=["browser"],
            )
        )

    # Abandonment: abandoned / reached funnels.
    reached = sum(1 for r in actions if "reached" in ((r.data or {}).get("milestone") or ""))
    abandoned = sum(1 for r in actions if (r.data or {}).get("milestone") == "abandoned")
    if reached or abandoned:
        rate = round(abandoned / reached, 2) if reached else (1.0 if abandoned else 0.0)
        snaps.append(
            TraitSnapshot(
                trait="abandonment_rate",
                value=rate,
                confidence=round(min(1.0, (reached + abandoned) / 4), 2),
                evidence=reached + abandoned,
                provenance=["browser"],
            )
        )

    # Payment preference: the latest payment-method choice (rows are newest-first).
    for r in interactions:
        d = r.data or {}
        if d.get("action") == "choose" and _PAYMENT_GROUP.search(str(d.get("group") or "")):
            pay = d.get("value") or d.get("label")
            if pay:
                snaps.append(
                    TraitSnapshot(
                        trait="preference:payment",
                        value=pay,
                        confidence=0.8,
                        evidence=1,
                        provenance=["browser"],
                    )
                )
            break

    return snaps


class UserModelDeriver:
    def __init__(
        self,
        events: BrowserActivityEventStore,
        model: UserModelStore,
        *,
        connector_key: str = "browser_activity",
    ) -> None:
        self._events = events
        self._model = model
        self._key = connector_key

    async def derive(self, *, limit: int = 500) -> list[TraitSnapshot]:
        rows = await self._events.recent(
            self._key, types=["interaction", "impression", "action"], limit=limit
        )
        snaps = compute_browser_traits(rows)
        if snaps:
            await self._model.write(snaps)
        return snaps
