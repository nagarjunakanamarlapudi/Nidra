"""HTTP layer for the connectors marketplace."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
import respx
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import AsyncEngine

from pragya_assistant.agent.core import LoopEngine
from pragya_assistant.agent.tools import ToolRegistry
from pragya_assistant.api.app import create_app
from pragya_assistant.api.deps import AppComponents
from pragya_assistant.config import Settings
from pragya_assistant.connectors.base import ConnectorDeps
from pragya_assistant.connectors.manager import ConnectorManager
from pragya_assistant.connectors.oauth import OAuthService
from pragya_assistant.connectors.store import (
    AppCredentialStore,
    ConnectorInstanceStore,
    OAuthFlowStore,
)
from pragya_assistant.digests.service import DigestService
from pragya_assistant.digests.store import DigestStore
from pragya_assistant.memory.conversations import ConversationStore
from pragya_assistant.memory.db import create_session_factory
from tests.conftest import TEST_DATABASE_URL
from tests.connectors._fakes import build_fake_registry
from tests.fakes import ScriptedChatProvider

AUTH = {"Authorization": "Bearer token"}
TOKEN_URL = "https://prov.example/token"


def _app(engine: AsyncEngine) -> object:
    settings = Settings(
        _env_file=None,
        app_secret_key="secretkey-secretkey",
        api_auth_token="token",
        database_url=TEST_DATABASE_URL,
        app_base_url="https://web.example",
        digest_enabled=False,
    )
    sf = create_session_factory(engine)
    agent = LoopEngine(
        provider=ScriptedChatProvider([]), registry=ToolRegistry([]), system_prompt="S"
    )
    components = AppComponents(
        settings=settings,
        engine=engine,
        agent=agent,
        conversations=ConversationStore(sf),
        digests=DigestService(engine=agent, store=DigestStore(sf)),
    )
    components.connectors = ConnectorManager(
        registry=build_fake_registry(),
        instance_store=ConnectorInstanceStore(sf, settings.app_secret_key),
        oauth=OAuthService(OAuthFlowStore(sf), redirect_base_url=settings.app_base_url),
        deps=ConnectorDeps(session_factory=sf, settings=settings),
        rebuild_engine=lambda tools, native=(): agent,
        apply_engine=lambda e: None,
        app_credential_store=AppCredentialStore(sf, settings.app_secret_key),
    )
    return create_app(settings, components=components)


def _client(engine: AsyncEngine) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=_app(engine)), base_url="http://test")


async def test_requires_token(engine: AsyncEngine) -> None:
    async with _client(engine) as c:
        assert (await c.get("/connectors")).status_code == 401


async def test_catalog_lists_connectors(engine: AsyncEngine) -> None:
    async with _client(engine) as c:
        resp = await c.get("/connectors", headers=AUTH)
    assert resp.status_code == 200
    by_key = {e["key"]: e for e in resp.json()}
    assert {"fake_secret", "fake_oauth"} <= set(by_key)
    assert by_key["fake_secret"]["status"] == "available"
    assert by_key["fake_oauth"]["auth_kind"] == "oauth2"


async def test_detail_exposes_schema_not_secrets(engine: AsyncEngine) -> None:
    async with _client(engine) as c:
        resp = await c.get("/connectors/fake_secret", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert [f["key"] for f in body["config_schema"]] == ["api_key"]
    assert body["configured_fields"] == []


async def test_unknown_connector_404(engine: AsyncEngine) -> None:
    async with _client(engine) as c:
        assert (await c.get("/connectors/nope", headers=AUTH)).status_code == 404


async def test_enable_secret_connects_and_redacts(engine: AsyncEngine) -> None:
    async with _client(engine) as c:
        resp = await c.post(
            "/connectors/fake_secret/enable",
            json={"config": {"api_key": "SUPERSECRET"}},
            headers=AUTH,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "connected"
    assert body["enabled"] is True
    assert body["configured_fields"] == ["api_key"]
    assert "SUPERSECRET" not in resp.text  # never echo secrets


async def test_enable_missing_field_400(engine: AsyncEngine) -> None:
    async with _client(engine) as c:
        resp = await c.post("/connectors/fake_secret/enable", json={"config": {}}, headers=AUTH)
    assert resp.status_code == 400


async def test_enable_oauth_connector_via_secret_path_rejected(engine: AsyncEngine) -> None:
    async with _client(engine) as c:
        resp = await c.post(
            "/connectors/fake_oauth/enable",
            json={"config": {"client_id": "a", "client_secret": "b"}},
            headers=AUTH,
        )
    assert resp.status_code == 400


async def test_oauth_app_save_enables_one_click(engine: AsyncEngine) -> None:
    async with _client(engine) as c:
        before = (await c.get("/connectors/fake_oauth", headers=AUTH)).json()
        assert before["oauth_server_configured"] is False
        assert "client_id" in [f["key"] for f in before["config_schema"]]

        resp = await c.post(
            "/connectors/fake_oauth/oauth/app",
            json={"client_id": "CID", "client_secret": "TOPSECRET"},
            headers=AUTH,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["oauth_server_configured"] is True
    assert "client_id" not in [f["key"] for f in body["config_schema"]]
    assert "TOPSECRET" not in resp.text


async def test_oauth_start_returns_authorize_url(engine: AsyncEngine) -> None:
    async with _client(engine) as c:
        resp = await c.post(
            "/connectors/fake_oauth/oauth/start",
            json={"config": {"client_id": "CID", "client_secret": "SEC"}},
            headers=AUTH,
        )
    assert resp.status_code == 200
    url = resp.json()["authorize_url"]
    assert url.startswith("https://prov.example/auth")
    assert "state=" in url


@respx.mock
async def test_oauth_callback_completes_and_redirects(engine: AsyncEngine) -> None:
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"access_token": "AT", "refresh_token": "RT", "expires_in": 3600}
        )
    )
    async with _client(engine) as c:
        start = await c.post(
            "/connectors/fake_oauth/oauth/start",
            json={"config": {"client_id": "CID", "client_secret": "SEC"}},
            headers=AUTH,
        )
        state = parse_qs(urlparse(start.json()["authorize_url"]).query)["state"][0]
        cb = await c.get(f"/connectors/oauth/callback?code=CODE&state={state}")
    assert cb.status_code == 303
    assert cb.headers["location"] == "https://web.example/?connector=fake_oauth&status=connected"


async def test_oauth_callback_bad_state_redirects_error(engine: AsyncEngine) -> None:
    async with _client(engine) as c:
        cb = await c.get("/connectors/oauth/callback?code=X&state=nope")
    assert cb.status_code == 303
    assert cb.headers["location"] == "https://web.example/?status=error"


@respx.mock
async def test_sync_after_connect(engine: AsyncEngine) -> None:
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"access_token": "AT", "refresh_token": "RT", "expires_in": 3600}
        )
    )
    async with _client(engine) as c:
        start = await c.post(
            "/connectors/fake_oauth/oauth/start",
            json={"config": {"client_id": "CID", "client_secret": "SEC"}},
            headers=AUTH,
        )
        state = parse_qs(urlparse(start.json()["authorize_url"]).query)["state"][0]
        await c.get(f"/connectors/oauth/callback?code=CODE&state={state}")
        resp = await c.post("/connectors/fake_oauth/sync", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["items"] == 5


async def test_test_disable_delete(engine: AsyncEngine) -> None:
    async with _client(engine) as c:
        await c.post(
            "/connectors/fake_secret/enable", json={"config": {"api_key": "K"}}, headers=AUTH
        )
        health = await c.post("/connectors/fake_secret/test", headers=AUTH)
        assert health.json()["ok"] is True
        disabled = await c.post("/connectors/fake_secret/disable", headers=AUTH)
        assert disabled.json()["enabled"] is False
        deleted = await c.delete("/connectors/fake_secret", headers=AUTH)
        assert deleted.json() == {"removed": True}
        detail = await c.get("/connectors/fake_secret", headers=AUTH)
        assert detail.json()["status"] == "available"
