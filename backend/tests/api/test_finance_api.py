"""Finance API tests — auth guard + 503 when Plaid is not configured."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport

from tests.fakes import ScriptedChatProvider

AUTH = {"Authorization": "Bearer token"}


@pytest.mark.asyncio
async def test_finance_sync_requires_token(build_test_app) -> None:  # type: ignore[no-untyped-def]
    """No auth header → 401."""
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/finance/sync")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_finance_sync_503_when_unconfigured(build_test_app) -> None:  # type: ignore[no-untyped-def]
    """Auth present but Plaid not configured → 503."""
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/finance/sync", headers=AUTH)
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_delete_item_requires_token(build_test_app) -> None:  # type: ignore[no-untyped-def]
    """No auth header → 401."""
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete("/finance/items/1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_item_503_when_unconfigured(build_test_app) -> None:  # type: ignore[no-untyped-def]
    """Auth present but Plaid not configured → 503."""
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.delete("/finance/items/1", headers=AUTH)
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_holdings_requires_token(build_test_app) -> None:  # type: ignore[no-untyped-def]
    """No auth header → 401."""
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/finance/holdings")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_holdings_503_when_unconfigured(build_test_app) -> None:  # type: ignore[no-untyped-def]
    """Auth present but Plaid not configured → 503."""
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/finance/holdings", headers=AUTH)
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_account_transactions_requires_token(build_test_app) -> None:  # type: ignore[no-untyped-def]
    """No auth header → 401."""
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/finance/transactions/1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_account_transactions_503_when_unconfigured(build_test_app) -> None:  # type: ignore[no-untyped-def]
    """Auth present but Plaid not configured → 503."""
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/finance/transactions/1", headers=AUTH)
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_investment_transactions_requires_token(build_test_app) -> None:  # type: ignore[no-untyped-def]
    """No auth header → 401."""
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/finance/investment-transactions/1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_investment_transactions_503_when_unconfigured(build_test_app) -> None:  # type: ignore[no-untyped-def]
    """Auth present but Plaid not configured → 503."""
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/finance/investment-transactions/1", headers=AUTH)
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_holdings_security_transactions_requires_token(build_test_app) -> None:  # type: ignore[no-untyped-def]
    """No auth header → 401."""
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/finance/holdings/sec_AAPL/transactions")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_holdings_security_transactions_503_when_unconfigured(build_test_app) -> None:  # type: ignore[no-untyped-def]
    """Auth present but Plaid not configured → 503."""
    app = build_test_app(ScriptedChatProvider([]))
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/finance/holdings/sec_AAPL/transactions", headers=AUTH)
    assert resp.status_code == 503
