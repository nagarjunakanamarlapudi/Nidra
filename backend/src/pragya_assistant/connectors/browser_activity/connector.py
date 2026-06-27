"""Browser Activity connector runtime.

Push-ingest: events arrive at the ingest endpoint, not via a pull. ``sync`` is a
no-op that simply reports how many events are stored, so the connector satisfies
``SupportsIngest`` and the manager's sync/health probes behave sensibly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pragya_assistant.connectors.base import Health, SyncResult
from pragya_assistant.connectors.browser_activity.store import BrowserActivityEventStore

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from pragya_assistant.connectors.base import ConnectorContext


class BrowserActivityConnector:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._store = BrowserActivityEventStore(session_factory)

    async def test_connection(self, ctx: ConnectorContext) -> Health:
        return Health(
            ok=True, detail="Ready to receive activity at /connectors/browser_activity/ingest"
        )

    async def sync(self, ctx: ConnectorContext) -> SyncResult:
        count = await self._store.count(ctx.key)
        return SyncResult(items=count, detail="push-based ingest; events arrive from the extension")
