"""The Google Calendar connector: ingest (sync) + tools + health probe."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.agent.tools import Tool
from pragya_assistant.connectors.base import ConnectorContext, Health, SyncResult
from pragya_assistant.connectors.google_calendar.client import GoogleCalendarClient
from pragya_assistant.connectors.google_calendar.store import CalendarEventStore
from pragya_assistant.connectors.google_calendar.tools import build_calendar_tools


class GoogleCalendarConnector:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        client: GoogleCalendarClient | None = None,
        now: Callable[[], dt.datetime] | None = None,
    ) -> None:
        self._store = CalendarEventStore(session_factory)
        self._client = client or GoogleCalendarClient()
        self._now = now or (lambda: dt.datetime.now(dt.UTC).replace(tzinfo=None))

    async def _token(self, ctx: ConnectorContext) -> str:
        if ctx.access_token is None:
            raise RuntimeError("google_calendar requires an OAuth access token")
        return await ctx.access_token()

    async def account_identity(self, access_token: str) -> tuple[str, str]:
        email = await self._client.primary_email(access_token)
        return (email or "calendar", email or "Calendar")

    def _accounts(self, ctx: ConnectorContext) -> list[tuple[str, Any]]:
        """(label, token-getter) per connected account; single-token fallback."""
        if ctx.accounts:
            return [(a.label, a.access_token) for a in ctx.accounts]
        if ctx.access_token is not None:
            return [("", ctx.access_token)]
        return []

    async def sync(self, ctx: ConnectorContext) -> SyncResult:
        accounts = self._accounts(ctx)
        if not accounts:
            raise RuntimeError("google_calendar requires an OAuth access token")
        calendar_id = ctx.config.get("calendar_id") or "primary"
        days_ahead = int(ctx.config.get("sync_days_ahead") or 30)
        days_back = int(ctx.config.get("sync_days_back") or 90)
        now = self._now()
        total = 0
        for label, get_token in accounts:
            events = await self._client.list_events(
                await get_token(),
                time_min=now - dt.timedelta(days=days_back),
                time_max=now + dt.timedelta(days=days_ahead),
                calendar_id=calendar_id,
            )
            await self._store.replace_for(ctx.key, events, account_label=label)
            total += len(events)
        return SyncResult(items=total, detail=f"{total} events across {len(accounts)} account(s)")

    async def test_connection(self, ctx: ConnectorContext) -> Health:
        accounts = self._accounts(ctx)
        if not accounts:
            return Health(ok=False, detail="No account connected")
        now = self._now()
        calendar_id = ctx.config.get("calendar_id") or "primary"
        try:
            for _label, get_token in accounts:
                await self._client.list_events(
                    await get_token(),
                    time_min=now,
                    time_max=now + dt.timedelta(days=1),
                    calendar_id=calendar_id,
                )
        except Exception as exc:
            return Health(ok=False, detail=str(exc))
        return Health(ok=True, detail=f"Connected ({len(accounts)} account(s))")

    def build_tools(self, ctx: ConnectorContext) -> list[Tool]:
        return build_calendar_tools(self._store, ctx.key)
