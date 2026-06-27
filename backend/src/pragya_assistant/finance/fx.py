"""USD→INR exchange-rate service with in-memory caching (12h TTL).

Fetches from Frankfurter (https://api.frankfurter.dev), which is free and
requires no API key.  On any network / parse error the last cached value is
returned so callers always get a best-effort result.
"""

from __future__ import annotations

import time
from decimal import Decimal

import httpx

_FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest?base=USD&symbols=INR"
_TTL_SECONDS = 12 * 60 * 60  # 12 hours


class FxService:
    """Singleton-friendly USD→INR rate cache."""

    def __init__(self) -> None:
        self._rate: Decimal | None = None
        self._as_of: str | None = None
        self._fetched_at: float = 0.0  # monotonic seconds; 0 → never fetched

    async def get_usd_inr(self) -> tuple[Decimal | None, str | None]:
        """Return (rate, as_of_date).

        Returns the cached value when the TTL has not expired.
        On fetch error, returns the last cached value if present, else (None, None).
        Never raises.
        """
        now = time.monotonic()
        if self._rate is not None and (now - self._fetched_at) < _TTL_SECONDS:
            return self._rate, self._as_of

        # Attempt a fresh fetch.
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(_FRANKFURTER_URL)
                resp.raise_for_status()
                data: dict[str, object] = resp.json()
                rates = data.get("rates")
                if not isinstance(rates, dict):
                    raise ValueError("Unexpected response shape")
                inr = rates.get("INR")
                if inr is None:
                    raise ValueError("INR not in response")
                self._rate = Decimal(str(inr))
                self._as_of = str(data.get("date", ""))
                self._fetched_at = now
        except Exception:  # noqa: BLE001, S110
            # Return whatever we have cached (may be None if first fetch ever).
            pass

        return self._rate, self._as_of
