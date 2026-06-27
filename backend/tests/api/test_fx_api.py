"""Tests for GET /finance/fx — auth guard + stubbed FxService."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
from httpx import ASGITransport

from pragya_assistant.api.deps import get_fx
from pragya_assistant.finance.fx import FxService
from tests.fakes import ScriptedChatProvider

AUTH = {"Authorization": "Bearer token"}


class _StubFxService(FxService):
    """Pre-loaded rate so no real HTTP call is made."""

    async def get_usd_inr(self) -> tuple[Decimal | None, str | None]:
        return Decimal("83.75"), "2026-06-20"


class _NullFxService(FxService):
    """Always returns (None, None) to simulate first-fetch failure."""

    async def get_usd_inr(self) -> tuple[Decimal | None, str | None]:
        return None, None


@pytest.mark.asyncio
async def test_fx_requires_token(build_test_app) -> None:  # type: ignore[no-untyped-def]
    """No auth header → 401."""
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/finance/fx")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_fx_returns_rate_when_available(build_test_app) -> None:  # type: ignore[no-untyped-def]
    """Auth present + stubbed FxService → 200 with usd_inr and as_of."""
    stub = _StubFxService()
    app = build_test_app(ScriptedChatProvider([]))
    app.dependency_overrides[get_fx] = lambda: stub

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/finance/fx", headers=AUTH)

    assert resp.status_code == 200
    data = resp.json()
    assert float(data["usd_inr"]) == pytest.approx(83.75)
    assert data["as_of"] == "2026-06-20"


@pytest.mark.asyncio
async def test_fx_returns_nulls_when_rate_unavailable(build_test_app) -> None:  # type: ignore[no-untyped-def]
    """Auth present but rate unavailable → 200 with null fields."""
    stub = _NullFxService()
    app = build_test_app(ScriptedChatProvider([]))
    app.dependency_overrides[get_fx] = lambda: stub

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/finance/fx", headers=AUTH)

    assert resp.status_code == 200
    data = resp.json()
    assert data["usd_inr"] is None
    assert data["as_of"] is None
