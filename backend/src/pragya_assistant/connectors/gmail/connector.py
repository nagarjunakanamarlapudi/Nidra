"""The Gmail connector: read-only tools + a health probe. No ingest/storage."""

from __future__ import annotations

from pragya_assistant.agent.tools import Tool
from pragya_assistant.connectors.base import ConnectorContext, Health
from pragya_assistant.connectors.gmail.client import GmailClient
from pragya_assistant.connectors.gmail.tools import build_gmail_tools


class GmailConnector:
    def __init__(self, *, client: GmailClient | None = None) -> None:
        self._client = client or GmailClient()

    async def _token(self, ctx: ConnectorContext) -> str:
        if ctx.access_token is None:
            raise RuntimeError("gmail requires an OAuth access token")
        return await ctx.access_token()

    async def account_identity(self, access_token: str) -> tuple[str, str]:
        email = await self._client.profile_email(access_token)
        return (email or "gmail", email or "Gmail")

    async def test_connection(self, ctx: ConnectorContext) -> Health:
        try:
            email = await self._client.profile_email(await self._token(ctx))
        except Exception as exc:
            return Health(ok=False, detail=str(exc))
        return Health(ok=True, detail=f"Connected to {email}" if email else "Connected to Gmail")

    def build_tools(self, ctx: ConnectorContext) -> list[Tool]:
        return build_gmail_tools(self._client, ctx)
