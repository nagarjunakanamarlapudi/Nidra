"""Connectors marketplace API — catalog, enable, OAuth, sync, test, disable.

All routes require the bearer token except the OAuth callback, which is the
provider's redirect target (protected by the opaque ``state`` instead).
Secrets are never echoed back — only which schema fields are configured.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse

from pragya_assistant.api.auth import require_token
from pragya_assistant.api.deps import get_components, get_connectors
from pragya_assistant.api.schemas import (
    ConnectorAccountOut,
    ConnectorDetailOut,
    ConnectorFieldOut,
    ConnectorHealthOut,
    ConnectorSummaryOut,
    EnableSecretIn,
    OAuthAppIn,
    OAuthStartIn,
    OAuthStartOut,
)
from pragya_assistant.connectors.manager import (
    CatalogEntry,
    ConnectorError,
    ConnectorManager,
    UnknownConnectorError,
)

router = APIRouter(tags=["connectors"], dependencies=[Depends(require_token)])
# Public — hit by the OAuth provider's browser redirect (no bearer token).
oauth_router = APIRouter(tags=["connectors"])

Manager = Annotated[ConnectorManager, Depends(get_connectors)]


def _summary(entry: CatalogEntry) -> ConnectorSummaryOut:
    return ConnectorSummaryOut(
        key=entry.key,
        name=entry.name,
        category=entry.category,
        pitch=entry.pitch,
        icon=entry.icon,
        capabilities=entry.capabilities,
        auth_kind=entry.auth_kind,
        widget=entry.widget,
        status=entry.status,
        enabled=entry.enabled,
        last_sync_at=entry.last_sync_at,
        last_error=entry.last_error,
        granted_scopes=entry.granted_scopes,
        configured_fields=entry.configured_fields,
        oauth_server_configured=entry.oauth_server_configured,
        accounts=[
            ConnectorAccountOut(
                id=a.id, label=a.label, status=a.status, granted_scopes=a.granted_scopes
            )
            for a in entry.accounts
        ],
    )


def _detail(entry: CatalogEntry) -> ConnectorDetailOut:
    return ConnectorDetailOut(
        **_summary(entry).model_dump(),
        config_schema=[
            ConnectorFieldOut(
                key=f.key,
                label=f.label,
                type=f.type,
                required=f.required,
                help=f.help,
                placeholder=f.placeholder,
                options=list(f.options),
                default=f.default,
            )
            for f in entry.config_schema
        ],
        docs_url=entry.docs_url,
    )


@router.get("/connectors", response_model=list[ConnectorSummaryOut])
async def list_connectors(manager: Manager) -> list[ConnectorSummaryOut]:
    return [_summary(e) for e in await manager.catalog()]


@router.get("/connectors/{key}", response_model=ConnectorDetailOut)
async def get_connector(key: str, manager: Manager) -> ConnectorDetailOut:
    entry = await manager.detail(key)
    if entry is None:
        raise HTTPException(status_code=404, detail="Unknown connector")
    return _detail(entry)


@router.post("/connectors/{key}/enable", response_model=ConnectorDetailOut)
async def enable_connector(key: str, body: EnableSecretIn, manager: Manager) -> ConnectorDetailOut:
    try:
        entry = await manager.enable_secret(key, body.config)
    except UnknownConnectorError:
        raise HTTPException(status_code=404, detail="Unknown connector") from None
    except (ValueError, ConnectorError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _detail(entry)


@router.post("/connectors/{key}/oauth/app", response_model=ConnectorDetailOut)
async def set_oauth_app(key: str, body: OAuthAppIn, manager: Manager) -> ConnectorDetailOut:
    """Save the shared OAuth app creds once → connecting becomes one-click."""
    try:
        entry = await manager.set_app_credentials(
            key, {"client_id": body.client_id, "client_secret": body.client_secret}
        )
    except UnknownConnectorError:
        raise HTTPException(status_code=404, detail="Unknown connector") from None
    except (ValueError, ConnectorError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _detail(entry)


@router.post("/connectors/{key}/oauth/start", response_model=OAuthStartOut)
async def start_oauth(key: str, body: OAuthStartIn, manager: Manager) -> OAuthStartOut:
    try:
        url = await manager.start_oauth(key, body.config)
    except UnknownConnectorError:
        raise HTTPException(status_code=404, detail="Unknown connector") from None
    except (ValueError, ConnectorError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return OAuthStartOut(authorize_url=url)


@oauth_router.get("/connectors/oauth/callback")
async def oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    components = get_components(request)
    base = components.settings.app_base_url.rstrip("/")
    manager = components.connectors
    if manager is None or error or not code or not state:
        return RedirectResponse(url=f"{base}/?status=error", status_code=303)
    try:
        entry = await manager.complete_oauth_by_state(code=code, state=state)
    except ConnectorError:
        return RedirectResponse(url=f"{base}/?status=error", status_code=303)
    return RedirectResponse(url=f"{base}/?connector={entry.key}&status=connected", status_code=303)


@router.post("/connectors/{key}/sync")
async def sync_connector(key: str, manager: Manager) -> dict[str, object]:
    try:
        result = await manager.sync(key)
    except UnknownConnectorError:
        raise HTTPException(status_code=404, detail="Unknown connector") from None
    except ConnectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"items": result.items, "detail": result.detail}


@router.post("/connectors/{key}/test", response_model=ConnectorHealthOut)
async def test_connector(key: str, manager: Manager) -> ConnectorHealthOut:
    try:
        health = await manager.test_connection(key)
    except UnknownConnectorError:
        raise HTTPException(status_code=404, detail="Unknown connector") from None
    except ConnectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ConnectorHealthOut(ok=health.ok, detail=health.detail)


@router.post("/connectors/{key}/disable", response_model=ConnectorDetailOut)
async def disable_connector(key: str, manager: Manager) -> ConnectorDetailOut:
    try:
        entry = await manager.disable(key)
    except UnknownConnectorError:
        raise HTTPException(status_code=404, detail="Unknown connector") from None
    return _detail(entry)


@router.delete("/connectors/{key}")
async def delete_connector(key: str, manager: Manager) -> dict[str, bool]:
    try:
        await manager.delete(key)
    except UnknownConnectorError:
        raise HTTPException(status_code=404, detail="Unknown connector") from None
    return {"removed": True}


@router.delete("/connectors/{key}/accounts/{account_id}", response_model=ConnectorDetailOut)
async def disconnect_account(key: str, account_id: int, manager: Manager) -> ConnectorDetailOut:
    """Disconnect one linked account (multi-account connectors)."""
    try:
        entry = await manager.disconnect_account(key, account_id)
    except UnknownConnectorError:
        raise HTTPException(status_code=404, detail="Unknown connector") from None
    return _detail(entry)
