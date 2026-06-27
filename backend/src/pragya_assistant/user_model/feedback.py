"""Dream outcome capture — the loop's return path.

A user outcome on a surfaced dream (acted / corroborated / dismissed / snoozed /
ignored) resolves the dream AND emits a REAL activity signal. That signal ingests
like any other and is what may later ground an Opinion — the dream is *never*
written as an Opinion directly (the one-way valve).
"""

from __future__ import annotations

import datetime as dt

from pragya_assistant.connectors.browser_activity.store import (
    BrowserActivityEventStore,
    IngestedEvent,
)
from pragya_assistant.user_model.dreams import DreamStore

_CONFIRM = {"acted", "corroborated"}
_REFUTE = {"dismissed"}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


class DreamFeedbackService:
    def __init__(
        self,
        dreams: DreamStore,
        events: BrowserActivityEventStore,
        *,
        connector_key: str = "browser_activity",
    ) -> None:
        self._dreams = dreams
        self._events = events
        self._key = connector_key

    async def record(
        self, dream_id: int, *, signal: str, at: dt.datetime | None = None
    ) -> str | None:
        """Resolve a dream by its real outcome and emit a grounding signal.
        ``snoozed`` / ``ignored`` do not resolve (stay active; ignored expires via TTL).
        Returns the resolved status, or None if not resolved."""
        if signal in _CONFIRM:
            status = "confirmed"
        elif signal in _REFUTE:
            status = "refuted"
        else:
            return None  # snoozed / ignored → leave active

        hypothesis = await self._dreams.hypothesis_of(dream_id)
        ts = at or _now()
        await self._dreams.resolve(dream_id, status=status, signal=signal, at=ts)
        await self._events.add_events(
            self._key,
            [
                IngestedEvent(
                    client_id=f"dream-{dream_id}-{signal}",
                    event_type="dream_outcome",
                    ts=ts,
                    source="dream",
                    data={
                        "dream_id": dream_id,
                        "signal": signal,
                        "status": status,
                        "hypothesis": hypothesis,
                    },
                )
            ],
        )
        return status
