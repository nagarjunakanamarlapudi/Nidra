"""A generic OAuth 2.0 authorization-code client with PKCE and refresh rotation.

Provider-agnostic: endpoints + scopes come from the connector's
:class:`~pragya_assistant.connectors.spec.OAuthConfig`; the user's
``client_id``/``client_secret`` come from the (encrypted) instance config. One
shared callback handles every provider, dispatched by the opaque ``state``.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from pragya_assistant.connectors.spec import ConnectorSpec, OAuthConfig
from pragya_assistant.connectors.store import OAuthFlowStore

_REFRESH_SKEW = dt.timedelta(seconds=60)


@dataclass(frozen=True)
class OAuthToken:
    access_token: str
    refresh_token: str | None
    expires_at: dt.datetime | None
    scope: str | None

    def to_config(self) -> dict[str, Any]:
        """The token fields to merge into a connector's encrypted config."""
        data: dict[str, Any] = {"access_token": self.access_token}
        if self.refresh_token is not None:
            data["refresh_token"] = self.refresh_token
        if self.expires_at is not None:
            data["expires_at"] = self.expires_at.isoformat()
        if self.scope is not None:
            data["scope"] = self.scope
        return data


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    return verifier, challenge


class OAuthService:
    def __init__(
        self,
        flow_store: OAuthFlowStore,
        *,
        redirect_base_url: str,
        now: Callable[[], dt.datetime] | None = None,
    ) -> None:
        self._flows = flow_store
        # The callback route lives on the backend, so this must be the API's base.
        self._redirect_uri = f"{redirect_base_url.rstrip('/')}/connectors/oauth/callback"
        self._now = now or (lambda: dt.datetime.now(dt.UTC))

    @staticmethod
    def _oauth(spec: ConnectorSpec) -> OAuthConfig:
        if spec.auth.oauth is None:
            raise ValueError(f"connector {spec.key!r} has no OAuth config")
        return spec.auth.oauth

    async def start(self, spec: ConnectorSpec, instance_config: dict[str, Any]) -> str:
        """Persist a PKCE flow and return the provider's authorize URL."""
        oauth = self._oauth(spec)
        verifier, challenge = _pkce_pair()
        state = secrets.token_urlsafe(32)
        await self._flows.create(state, spec.key, verifier)
        params = {
            "client_id": instance_config["client_id"],
            "redirect_uri": self._redirect_uri,
            "response_type": "code",
            "scope": " ".join(oauth.scopes),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            **oauth.extra_authorize_params,
        }
        return f"{oauth.authorize_url}?{urlencode(params)}"

    async def exchange(
        self, spec: ConnectorSpec, instance_config: dict[str, Any], *, code: str, state: str
    ) -> OAuthToken:
        """Validate the callback ``state``, then trade ``code`` for tokens."""
        oauth = self._oauth(spec)
        flow = await self._flows.pop(state)
        if flow is None or flow.connector_key != spec.key:
            raise ValueError("invalid or expired OAuth state")
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._redirect_uri,
            "client_id": instance_config["client_id"],
            "client_secret": instance_config.get("client_secret", ""),
            "code_verifier": flow.code_verifier,
        }
        return await self._token_request(oauth.token_url, data, fallback_refresh=None)

    async def refresh(
        self, spec: ConnectorSpec, instance_config: dict[str, Any], refresh_token: str
    ) -> OAuthToken:
        oauth = self._oauth(spec)
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": instance_config["client_id"],
            "client_secret": instance_config.get("client_secret", ""),
        }
        return await self._token_request(oauth.token_url, data, fallback_refresh=refresh_token)

    async def connector_for_state(self, state: str) -> str | None:
        """Which connector a pending OAuth ``state`` belongs to (peek, no consume)."""
        return await self._flows.connector_for_state(state)

    async def access_token_for(
        self, spec: ConnectorSpec, config: dict[str, Any]
    ) -> tuple[str, dict[str, Any]]:
        """Return a valid access token, refreshing if needed. Also returns the
        (possibly rotated) config so the caller can persist new tokens."""
        access = config.get("access_token")
        expires_at = config.get("expires_at")
        refresh_token = config.get("refresh_token")
        if access and expires_at and not self._is_expiring(expires_at):
            return access, config
        if not refresh_token:
            if access:
                return access, config
            raise ValueError("no access token and no refresh token available")
        token = await self.refresh(spec, config, refresh_token)
        return token.access_token, {**config, **token.to_config()}

    async def _token_request(
        self, token_url: str, data: dict[str, Any], *, fallback_refresh: str | None
    ) -> OAuthToken:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(token_url, data=data, headers={"Accept": "application/json"})
            resp.raise_for_status()
            payload: dict[str, Any] = resp.json()
        expires_at: dt.datetime | None = None
        if "expires_in" in payload:
            expires_at = self._now() + dt.timedelta(seconds=int(payload["expires_in"]))
        return OAuthToken(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token") or fallback_refresh,
            expires_at=expires_at,
            scope=payload.get("scope"),
        )

    def _is_expiring(self, expires_at_raw: str) -> bool:
        try:
            expires_at = dt.datetime.fromisoformat(expires_at_raw)
        except ValueError:
            return True
        return expires_at <= self._now() + _REFRESH_SKEW
