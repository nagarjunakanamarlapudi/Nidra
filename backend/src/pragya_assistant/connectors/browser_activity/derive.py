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


def compute_browser_traits(rows: list[BrowserActivityEvent]) -> list[TraitSnapshot]:
    """Pure: distill decision-style traits from browser interaction/action rows.
    Shared by UserModelDeriver and the multi-source BrowserExtractor. Provenance
    is source-level (``browser``); every trait carries a derivation evidence chain.

    NOTE: we intentionally do NOT derive "decisiveness" from time-on-page latency.
    Time-since-page-load is not deliberation — a tab can sit open/backgrounded for
    an hour. Decision style is read from REVERSALS (re-touching a control), which
    is time-independent.
    """
    interactions = [r for r in rows if r.event_type == "interaction"]
    actions = [r for r in rows if r.event_type == "action"]
    snaps: list[TraitSnapshot] = []

    # Deliberation: controls the user re-touched / reversed — a time-independent
    # decision-style signal (toggled on then off, re-chose, etc.).
    by_key: dict[str, list[BrowserActivityEvent]] = {}
    for r in interactions:
        key = (r.data or {}).get("elementKey")
        if key:
            by_key.setdefault(str(key), []).append(r)
    reversed_keys = {k: rs for k, rs in by_key.items() if len(rs) > 1}
    if reversed_keys:
        event_ids = [r.id for rs in reversed_keys.values() for r in rs]
        snaps.append(
            TraitSnapshot(
                trait="deliberation",
                value=len(reversed_keys),
                confidence=round(min(1.0, len(reversed_keys) / 3), 2),
                evidence=len(reversed_keys),
                provenance=["browser"],
                derivation={
                    "formula": "count of controls re-touched/reversed (time-independent)",
                    "inputs": {"reversed_controls": len(reversed_keys)},
                    "event_ids": event_ids,
                },
            )
        )

    # Abandonment: abandoned / reached funnels.
    reached_rows = [r for r in actions if "reached" in ((r.data or {}).get("milestone") or "")]
    abandoned_rows = [r for r in actions if (r.data or {}).get("milestone") == "abandoned"]
    if reached_rows or abandoned_rows:
        reached, abandoned = len(reached_rows), len(abandoned_rows)
        rate = round(abandoned / reached, 2) if reached else (1.0 if abandoned else 0.0)
        snaps.append(
            TraitSnapshot(
                trait="abandonment_rate",
                value=rate,
                confidence=round(min(1.0, (reached + abandoned) / 4), 2),
                evidence=reached + abandoned,
                provenance=["browser"],
                derivation={
                    "formula": "abandoned / reached funnels",
                    "inputs": {"abandoned": abandoned, "reached": reached},
                    "event_ids": [r.id for r in reached_rows + abandoned_rows],
                },
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
                        derivation={
                            "formula": "latest payment-method choice",
                            "inputs": {"choice": pay},
                            "event_ids": [r.id],
                        },
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
