"""Tests for FxService — USD→INR cached rate fetcher."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
import respx

from pragya_assistant.finance.fx import FxService

_GOOD_RESPONSE = {
    "amount": 1.0,
    "base": "USD",
    "date": "2026-06-20",
    "rates": {"INR": 83.5},
}

_FX_URL = "https://api.frankfurter.dev/v1/latest?base=USD&symbols=INR"


@pytest.mark.asyncio
@respx.mock
async def test_successful_fetch_returns_rate_and_date() -> None:
    """A successful HTTP fetch returns the INR rate and the as-of date."""
    respx.get(_FX_URL).mock(return_value=httpx.Response(200, json=_GOOD_RESPONSE))

    svc = FxService()
    rate, as_of = await svc.get_usd_inr()

    assert rate == Decimal("83.5")
    assert as_of == "2026-06-20"


@pytest.mark.asyncio
@respx.mock
async def test_cache_prevents_second_request() -> None:
    """A second call within TTL must NOT make another HTTP request."""
    route = respx.get(_FX_URL).mock(return_value=httpx.Response(200, json=_GOOD_RESPONSE))

    svc = FxService()
    rate1, _ = await svc.get_usd_inr()
    rate2, _ = await svc.get_usd_inr()

    assert rate1 == rate2
    assert route.call_count == 1  # only one real request


@pytest.mark.asyncio
@respx.mock
async def test_fetch_error_after_prior_success_returns_cached_value() -> None:
    """When a re-fetch fails but we have a prior cached value, return it."""
    # First call succeeds.
    respx.get(_FX_URL).mock(return_value=httpx.Response(200, json=_GOOD_RESPONSE))
    svc = FxService()
    await svc.get_usd_inr()

    # Force TTL expiry by backdating the fetched_at timestamp.
    svc._fetched_at = 0.0

    # Second call fails.
    respx.get(_FX_URL).mock(side_effect=httpx.ConnectError("network down"))
    rate, as_of = await svc.get_usd_inr()

    assert rate == Decimal("83.5")
    assert as_of == "2026-06-20"


@pytest.mark.asyncio
@respx.mock
async def test_error_with_no_cache_returns_none_none() -> None:
    """When the very first fetch fails and there is no cache, return (None, None)."""
    respx.get(_FX_URL).mock(side_effect=httpx.ConnectError("network down"))

    svc = FxService()
    rate, as_of = await svc.get_usd_inr()

    assert rate is None
    assert as_of is None
