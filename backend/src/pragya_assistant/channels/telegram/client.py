"""Minimal Telegram Bot API client (httpx)."""

from __future__ import annotations

from typing import Any

import httpx


class TelegramClient:
    def __init__(self, token: str, *, base_url: str = "https://api.telegram.org") -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")

    async def get_me(self) -> dict[str, Any]:
        """Return the bot's own profile (used to validate the token)."""
        url = f"{self._base_url}/bot{self._token}/getMe"
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
        return dict(data.get("result", {}))

    async def send_message(self, chat_id: int, text: str) -> None:
        url = f"{self._base_url}/bot{self._token}/sendMessage"
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json={"chat_id": chat_id, "text": text})
            response.raise_for_status()

    async def get_updates(
        self,
        offset: int | None = None,
        *,
        poll_timeout: int = 25,
        allowed_updates: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Long-poll for updates (outbound; no public URL needed).

        ``poll_timeout`` is Telegram's server-side long-poll duration (seconds).
        """
        url = f"{self._base_url}/bot{self._token}/getUpdates"
        params: dict[str, Any] = {"timeout": poll_timeout}
        if offset is not None:
            params["offset"] = offset
        if allowed_updates is not None:
            params["allowed_updates"] = allowed_updates
        async with httpx.AsyncClient(timeout=poll_timeout + 10) as client:
            response = await client.post(url, json=params)
            response.raise_for_status()
            data = response.json()
        return list(data.get("result", []))
