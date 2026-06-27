"""Generic OAuth 2.0 service: authorization-code + PKCE + refresh rotation."""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.connectors.oauth import OAuthService
from pragya_assistant.connectors.spec import (
    AuthStrategy,
    Capability,
    ConnectorSpec,
    Field,
    OAuthConfig,
)
from pragya_assistant.connectors.store import OAuthFlowStore

AUTH = "https://accounts.example/authorize"
TOKEN = "https://oauth.example/token"
CLIENT = {"client_id": "CID", "client_secret": "SEC"}


def _spec() -> ConnectorSpec:
    return ConnectorSpec(
        key="demo",
        name="Demo",
        category="X",
        pitch="x",
        icon="🔌",
        auth=AuthStrategy(
            kind="oauth2",
            oauth=OAuthConfig(
                authorize_url=AUTH,
                token_url=TOKEN,
                scopes=("scope.read",),
                extra_authorize_params={"access_type": "offline", "prompt": "consent"},
            ),
        ),
        capabilities=frozenset({Capability.INGEST}),
        config_schema=(
            Field(key="client_id", label="Client ID"),
            Field(key="client_secret", label="Secret", type="secret"),
        ),
    )


def _fixed_now() -> dt.datetime:
    return dt.datetime(2026, 6, 23, 12, 0, tzinfo=dt.UTC)


def _service(session_factory: async_sessionmaker[AsyncSession]) -> OAuthService:
    return OAuthService(
        OAuthFlowStore(session_factory), redirect_base_url="https://app.example", now=_fixed_now
    )


async def test_start_builds_authorize_url_with_pkce(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    flows = OAuthFlowStore(session_factory)
    svc = OAuthService(flows, redirect_base_url="https://app.example", now=_fixed_now)
    url = await svc.start(_spec(), CLIENT)

    parsed = urlparse(url)
    q = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == AUTH
    assert q["client_id"] == ["CID"]
    assert q["redirect_uri"] == ["https://app.example/connectors/oauth/callback"]
    assert q["response_type"] == ["code"]
    assert q["scope"] == ["scope.read"]
    assert q["code_challenge_method"] == ["S256"]
    assert q["access_type"] == ["offline"]
    assert q["prompt"] == ["consent"]

    state = q["state"][0]
    flow = await flows.pop(state)
    assert flow is not None
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(flow.code_verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    assert q["code_challenge"][0] == expected


@respx.mock
async def test_exchange_posts_code_and_verifier(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    svc = _service(session_factory)
    url = await svc.start(_spec(), CLIENT)
    state = parse_qs(urlparse(url).query)["state"][0]
    route = respx.post(TOKEN).mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "AT",
                "refresh_token": "RT",
                "expires_in": 3600,
                "scope": "scope.read",
            },
        )
    )

    token = await svc.exchange(_spec(), CLIENT, code="CODE", state=state)

    assert token.access_token == "AT"
    assert token.refresh_token == "RT"
    assert token.expires_at == dt.datetime(2026, 6, 23, 13, 0, tzinfo=dt.UTC)
    body = parse_qs(route.calls.last.request.content.decode())
    assert body["grant_type"] == ["authorization_code"]
    assert body["code"] == ["CODE"]
    assert body["client_id"] == ["CID"]
    assert body["code_verifier"][0]


async def test_exchange_with_bad_state_raises(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    svc = _service(session_factory)
    with pytest.raises(ValueError, match="state"):
        await svc.exchange(_spec(), CLIENT, code="C", state="does-not-exist")


@respx.mock
async def test_refresh_preserves_refresh_token_when_provider_omits_it(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    svc = _service(session_factory)
    respx.post(TOKEN).mock(
        return_value=httpx.Response(200, json={"access_token": "AT2", "expires_in": 3600})
    )
    token = await svc.refresh(_spec(), CLIENT, "RTold")
    assert token.access_token == "AT2"
    assert token.refresh_token == "RTold"


@respx.mock
async def test_access_token_for_refreshes_when_expired(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    svc = _service(session_factory)
    respx.post(TOKEN).mock(
        return_value=httpx.Response(200, json={"access_token": "FRESH", "expires_in": 3600})
    )
    config = {
        **CLIENT,
        "access_token": "STALE",
        "refresh_token": "RT",
        "expires_at": dt.datetime(2026, 6, 23, 11, 0, tzinfo=dt.UTC).isoformat(),
    }
    token, new_config = await svc.access_token_for(_spec(), config)
    assert token == "FRESH"
    assert new_config["access_token"] == "FRESH"
    assert new_config["expires_at"] == dt.datetime(2026, 6, 23, 13, 0, tzinfo=dt.UTC).isoformat()


async def test_access_token_for_is_noop_when_fresh(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    svc = _service(session_factory)
    config = {
        **CLIENT,
        "access_token": "GOOD",
        "refresh_token": "RT",
        "expires_at": dt.datetime(2026, 6, 23, 13, 0, tzinfo=dt.UTC).isoformat(),
    }
    token, new_config = await svc.access_token_for(_spec(), config)
    assert token == "GOOD"
    assert new_config == config
