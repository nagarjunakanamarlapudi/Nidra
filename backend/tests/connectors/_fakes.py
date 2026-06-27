"""Shared fake connectors for manager/route tests (not a test module)."""

from __future__ import annotations

from typing import Any

from pragya_assistant.agent.tools import Tool
from pragya_assistant.connectors.base import (
    ConnectorContext,
    Health,
    RegisteredConnector,
    SyncResult,
)
from pragya_assistant.connectors.registry import ConnectorRegistry
from pragya_assistant.connectors.spec import (
    AuthStrategy,
    Capability,
    ConnectorSpec,
    Field,
    OAuthConfig,
)


class FakeSecretConnector:
    async def test_connection(self, ctx: ConnectorContext) -> Health:
        ok = ctx.config.get("api_key") != "BAD"
        return Health(ok=ok, detail=None if ok else "bad key")

    def build_tools(self, ctx: ConnectorContext) -> list[Tool]:
        async def _handler(args: dict[str, Any]) -> str:
            return "ok"

        return [
            Tool(
                name="fake_secret_tool",
                description="d",
                input_schema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
                handler=_handler,
            )
        ]


class FakeOAuthConnector:
    async def test_connection(self, ctx: ConnectorContext) -> Health:
        return Health(ok=True)

    async def sync(self, ctx: ConnectorContext) -> SyncResult:
        if ctx.access_token is not None:
            await ctx.access_token()
        return SyncResult(items=5, detail="5 events")


SECRET_SPEC = ConnectorSpec(
    key="fake_secret",
    name="Fake Secret",
    category="Test",
    pitch="A secret-auth connector.",
    icon="🔑",
    auth=AuthStrategy(kind="secret"),
    capabilities=frozenset({Capability.TOOLS}),
    config_schema=(Field(key="api_key", label="API key", type="secret"),),
)

OAUTH_SPEC = ConnectorSpec(
    key="fake_oauth",
    name="Fake OAuth",
    category="Test",
    pitch="An OAuth connector.",
    icon="🔐",
    auth=AuthStrategy(
        kind="oauth2",
        oauth=OAuthConfig(
            authorize_url="https://prov.example/auth",
            token_url="https://prov.example/token",
            scopes=("s.read",),
            provider="prov",
        ),
    ),
    capabilities=frozenset({Capability.INGEST}),
    config_schema=(
        Field(key="client_id", label="Client ID"),
        Field(key="client_secret", label="Secret", type="secret"),
    ),
)


def build_fake_registry() -> ConnectorRegistry:
    reg = ConnectorRegistry()
    reg.register(RegisteredConnector(spec=SECRET_SPEC, build=lambda deps: FakeSecretConnector()))
    reg.register(RegisteredConnector(spec=OAUTH_SPEC, build=lambda deps: FakeOAuthConnector()))
    return reg
