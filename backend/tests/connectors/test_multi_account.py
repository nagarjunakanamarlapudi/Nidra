"""Multi-account: two Google-style accounts under one OAuth connector, aggregated."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.agent.tools import Tool
from pragya_assistant.connectors.base import (
    ConnectorContext,
    ConnectorDeps,
    Health,
    RegisteredConnector,
)
from pragya_assistant.connectors.manager import ConnectorManager
from pragya_assistant.connectors.oauth import OAuthToken
from pragya_assistant.connectors.registry import ConnectorRegistry
from pragya_assistant.connectors.spec import (
    AuthStrategy,
    Capability,
    ConnectorSpec,
    OAuthConfig,
)
from pragya_assistant.connectors.store import AppCredentialStore, ConnectorInstanceStore

_SPEC = ConnectorSpec(
    key="multi",
    name="Multi",
    category="Test",
    pitch="",
    icon="",
    auth=AuthStrategy(
        kind="oauth2",
        oauth=OAuthConfig(
            authorize_url="https://a/auth",
            token_url="https://a/tok",  # noqa: S106
            scopes=("s.read",),
            provider="multi",
        ),
    ),
    capabilities=frozenset({Capability.TOOLS}),
)


class _MultiConn:
    """OAuth connector whose identity is encoded in the token ('tok:<email>'),
    and whose tool aggregates over all linked accounts."""

    async def test_connection(self, ctx: ConnectorContext) -> Health:
        return Health(ok=True)

    async def account_identity(self, access_token: str) -> tuple[str, str]:
        email = access_token.split(":", 1)[1]
        return email, email

    def build_tools(self, ctx: ConnectorContext) -> list[Tool]:
        labels = [a.label for a in ctx.accounts]

        async def _whoami(args: dict[str, Any]) -> str:
            return "accounts: " + ", ".join(labels)

        schema = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
        return [
            Tool(name="whoami", description="list accounts", input_schema=schema, handler=_whoami)
        ]


class _FakeOAuth:
    async def start(self, spec: ConnectorSpec, config: dict[str, Any]) -> str:
        return "https://auth/redirect?state=ST"

    async def exchange(
        self, spec: ConnectorSpec, config: dict[str, Any], *, code: str, state: str
    ) -> OAuthToken:
        return OAuthToken(
            access_token=f"tok:{code}", refresh_token="R", expires_at=None, scope="s.read"
        )

    async def access_token_for(
        self, spec: ConnectorSpec, config: dict[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        return config.get("access_token", "tok:?"), config


def _manager(sf: async_sessionmaker[AsyncSession]) -> ConnectorManager:
    reg = ConnectorRegistry()
    reg.register(RegisteredConnector(spec=_SPEC, build=lambda deps: _MultiConn()))
    return ConnectorManager(
        registry=reg,
        instance_store=ConnectorInstanceStore(sf, "key"),
        oauth=_FakeOAuth(),  # type: ignore[arg-type]
        deps=ConnectorDeps(session_factory=sf, settings=None),  # type: ignore[arg-type]
        rebuild_engine=lambda tools, native=(): ("E", tools, native),
        apply_engine=lambda e: None,
        app_credential_store=AppCredentialStore(sf, "key"),
    )


async def test_two_accounts_linked_aggregated_and_disconnected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    mgr = _manager(session_factory)
    await mgr.start_oauth("multi", {})
    await mgr.complete_oauth("multi", code="work@x.com", state="ST")
    await mgr.complete_oauth("multi", code="home@x.com", state="ST")

    # both accounts are linked under the one connector
    entry = await mgr.detail("multi")
    assert entry is not None
    assert entry.enabled is True
    assert {a.label for a in entry.accounts} == {"work@x.com", "home@x.com"}

    # the tool aggregates across both accounts
    tools = await mgr.connector_tools()
    whoami = next(t for t in tools if t.name == "whoami")
    out = await whoami.handler({})
    assert "work@x.com" in out and "home@x.com" in out

    # re-connecting the SAME account updates in place (no duplicate)
    await mgr.complete_oauth("multi", code="work@x.com", state="ST")
    entry = await mgr.detail("multi")
    assert entry is not None and len(entry.accounts) == 2

    # disconnect one account → one remains, connector still enabled
    work_id = next(a.id for a in entry.accounts if a.label == "work@x.com")
    await mgr.disconnect_account("multi", work_id)
    entry = await mgr.detail("multi")
    assert entry is not None
    assert [a.label for a in entry.accounts] == ["home@x.com"]
    assert entry.enabled is True

    # disconnect the last → connector disabled
    home_id = entry.accounts[0].id
    await mgr.disconnect_account("multi", home_id)
    entry = await mgr.detail("multi")
    assert entry is not None and entry.accounts == [] and entry.enabled is False
