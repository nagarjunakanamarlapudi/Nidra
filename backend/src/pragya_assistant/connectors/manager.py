"""The ConnectorManager — the heart of the platform.

It joins the registry (what's available) with instances (what's enabled), owns
the enable / OAuth / sync / test / disable lifecycle, resolves the enabled
connectors' tools, and rebuilds the agent engine on any change so a newly
connected connector is live on the next turn — no restart.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pragya_assistant.connectors.base import (
    AccountAuth,
    ConnectorContext,
    ConnectorDeps,
    Health,
    RegisteredConnector,
    SupportsAccountIdentity,
    SupportsChannel,
    SupportsIngest,
    SupportsTools,
    SyncResult,
)
from pragya_assistant.connectors.registry import ConnectorRegistry
from pragya_assistant.connectors.spec import Capability, ConnectorSpec, Field
from pragya_assistant.connectors.store import AppCredentialStore, ConnectorInstanceStore

if TYPE_CHECKING:
    from pragya_assistant.agent.engine import AgentEngine
    from pragya_assistant.agent.tools import Tool
    from pragya_assistant.connectors.oauth import OAuthService
    from pragya_assistant.memory.models import ConnectorInstance

# Token fields that live in a ConnectorAccount (OAuth), kept out of instance config.
_TOKEN_KEYS = ("access_token", "refresh_token", "expires_at", "scope")


class ConnectorError(Exception):
    """A connector operation failed (enable, sync, OAuth, …)."""


class UnknownConnectorError(ConnectorError):
    """No connector is registered under the given key."""


@dataclass(frozen=True)
class AccountSummary:
    """One linked account of a connector, as shown in the marketplace (no secrets)."""

    id: int
    label: str
    status: str
    granted_scopes: list[str]


@dataclass(frozen=True)
class CatalogEntry:
    """A connector as shown in the marketplace: spec + live status (no secrets)."""

    key: str
    name: str
    category: str
    pitch: str
    icon: str
    capabilities: list[str]
    auth_kind: str
    widget: str | None
    status: str
    enabled: bool
    last_sync_at: dt.datetime | None
    last_error: str | None
    granted_scopes: list[str]
    config_schema: list[Field]
    configured_fields: list[str]
    docs_url: str | None
    oauth_server_configured: bool
    accounts: list[AccountSummary]  # linked accounts (multi-account OAuth connectors)


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


class ConnectorManager:
    def __init__(
        self,
        *,
        registry: ConnectorRegistry,
        instance_store: ConnectorInstanceStore,
        oauth: OAuthService,
        deps: ConnectorDeps,
        rebuild_engine: Callable[[list[Tool], tuple[str, ...]], AgentEngine],
        apply_engine: Callable[[AgentEngine], None],
        app_credential_store: AppCredentialStore,
        server_oauth_clients: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self._registry = registry
        self._store = instance_store
        self._accounts = instance_store.accounts()  # multi-account token store
        self._oauth = oauth
        self._deps = deps
        self._rebuild_engine = rebuild_engine
        self._apply_engine = apply_engine
        self._app_creds = app_credential_store
        # provider -> {"client_id", "client_secret"} from env (takes precedence
        # over DB-stored app creds); enables one-click OAuth without UI paste.
        self._server_clients = server_oauth_clients or {}
        # Running channel workers (e.g. the Telegram poller), keyed by connector.
        self._channel_tasks: dict[str, asyncio.Task[Any]] = {}

    async def _server_client(self, spec: ConnectorSpec) -> dict[str, str] | None:
        """The shared OAuth app creds for a connector's provider — env first,
        then the DB app-credential store; None if neither is set."""
        if spec.auth.oauth is None or spec.auth.oauth.provider is None:
            return None
        provider = spec.auth.oauth.provider
        env = self._server_clients.get(provider)
        if env and env.get("client_id"):
            return env
        stored = await self._app_creds.get(provider)
        if stored and stored.get("client_id"):
            return stored
        return None

    # --- catalog -----------------------------------------------------------
    async def catalog(self) -> list[CatalogEntry]:
        return [await self._entry(spec) for spec in self._registry.all_specs()]

    async def detail(self, key: str) -> CatalogEntry | None:
        rc = self._registry.get(key)
        return None if rc is None else await self._entry(rc.spec)

    async def _entry(self, spec: ConnectorSpec) -> CatalogEntry:
        inst = await self._store.get(spec.key)
        if inst is None:
            status, enabled, last_sync, last_error, scopes, configured = (
                "available",
                False,
                None,
                None,
                [],
                [],
            )
        else:
            config = self._store.decrypt_config(inst)
            configured = [f.key for f in spec.config_schema if f.key in config]
            status, enabled = inst.status, inst.enabled
            last_sync, last_error = inst.last_sync_at, inst.last_error
            scopes = list(inst.granted_scopes or [])
        # When the server already holds the OAuth client creds, hide those fields.
        server_configured = (
            spec.auth.kind == "oauth2" and await self._server_client(spec) is not None
        )
        schema = list(spec.config_schema)
        if server_configured and spec.auth.oauth is not None:
            hidden = set(spec.auth.oauth.client_field_keys)
            schema = [f for f in schema if f.key not in hidden]
        # Multi-account (OAuth): the linked accounts, read from stored rows (no probe).
        accounts: list[AccountSummary] = []
        if spec.auth.kind == "oauth2":
            accounts = [
                AccountSummary(
                    id=a.id,
                    label=a.label,
                    status=a.status,
                    granted_scopes=list(a.granted_scopes or []),
                )
                for a in await self._accounts.list_for_connector(spec.key)
            ]
        return CatalogEntry(
            key=spec.key,
            name=spec.name,
            category=spec.category,
            pitch=spec.pitch,
            icon=spec.icon,
            capabilities=[c.value for c in sorted(spec.capabilities)],
            auth_kind=spec.auth.kind,
            widget=spec.auth.widget,
            status=status,
            enabled=enabled,
            last_sync_at=last_sync,
            last_error=last_error,
            granted_scopes=scopes,
            config_schema=schema,
            configured_fields=configured,
            docs_url=spec.docs_url,
            oauth_server_configured=server_configured,
            accounts=accounts,
        )

    # --- enable / disable / delete ----------------------------------------
    async def enable_secret(self, key: str, config: dict[str, Any]) -> CatalogEntry:
        rc = self._require(key)
        if rc.spec.auth.kind not in ("secret", "none", "managed_widget"):
            raise ValueError(f"{key} uses {rc.spec.auth.kind} auth — use the OAuth flow to connect")
        validated = self._validate(rc.spec, config)
        await self._store.upsert_config(key, validated, enabled=True, status="connected")
        health = await self.test_connection(key)
        if not health.ok:
            await self._store.set_status(key, "error", last_error=health.detail)
        await self.refresh()
        return await self._entry(rc.spec)

    async def update_config(self, key: str, partial: dict[str, Any]) -> CatalogEntry:
        rc = self._require(key)
        await self._store.patch_config(key, partial)
        await self.refresh()
        return await self._entry(rc.spec)

    async def disable(self, key: str) -> CatalogEntry:
        rc = self._require(key)
        inst = await self._store.get(key)
        if inst is not None:
            await self._store.upsert_config(
                key,
                self._store.decrypt_config(inst),
                enabled=False,
                status="disabled",
                granted_scopes=inst.granted_scopes,
            )
        await self.refresh()
        return await self._entry(rc.spec)

    async def delete(self, key: str) -> None:
        self._require(key)
        for acc in await self._accounts.list_for_connector(key):
            await self._accounts.delete(acc.id)
        await self._store.delete(key)
        await self.refresh()

    # --- OAuth -------------------------------------------------------------
    async def set_app_credentials(self, key: str, creds: dict[str, Any]) -> CatalogEntry:
        """Save the shared OAuth *app* creds for this connector's provider, so
        future connects are one-click. Stored encrypted, keyed by provider."""
        rc = self._require(key)
        oauth = rc.spec.auth.oauth
        if rc.spec.auth.kind != "oauth2" or oauth is None or oauth.provider is None:
            raise ConnectorError(f"{key} does not support a shared OAuth app")
        missing = [k for k in oauth.client_field_keys if not creds.get(k)]
        if missing:
            raise ValueError(f"missing required fields: {missing}")
        selected = {k: str(creds[k]) for k in oauth.client_field_keys}
        await self._app_creds.set(oauth.provider, selected)
        return await self._entry(rc.spec)

    async def start_oauth(self, key: str, client_config: dict[str, Any]) -> str:
        rc = self._require(key)
        if rc.spec.auth.kind != "oauth2":
            raise ConnectorError(f"{key} is not an OAuth connector")
        # Server-held client creds (env or saved app) take precedence over the UI.
        server = await self._server_client(rc.spec)
        merged = {**client_config, **server} if server else client_config
        validated = self._validate(rc.spec, merged)
        await self._store.upsert_config(key, validated, enabled=False, status="connecting")
        return await self._oauth.start(rc.spec, validated)

    async def complete_oauth(self, key: str, *, code: str, state: str) -> CatalogEntry:
        rc = self._require(key)
        inst = await self._store.get(key)
        if inst is None:
            raise ConnectorError(f"no pending OAuth for {key}")
        config = self._store.decrypt_config(inst)
        try:
            token = await self._oauth.exchange(rc.spec, config, code=code, state=state)
        except Exception as exc:
            await self._store.set_status(key, "needs_reconnect", last_error=str(exc))
            raise ConnectorError(f"OAuth exchange failed for {key}: {exc}") from exc
        scopes = token.scope.split() if token.scope else list(rc.spec.auth.oauth.scopes)  # type: ignore[union-attr]
        # Identify the account (email) so re-connecting updates rather than clobbers,
        # and a second login becomes a distinct account.
        external_id, label = await self._account_identity(rc, token.access_token)
        await self._accounts.upsert_by_identity(
            key, external_id, label=label, config=token.to_config(), granted_scopes=scopes
        )
        # The instance is the connector's on/off + settings marker (no tokens).
        settings = {k: v for k, v in config.items() if k not in _TOKEN_KEYS}
        await self._store.upsert_config(
            key, settings, enabled=True, status="connected", granted_scopes=scopes
        )
        await self.refresh()
        return await self._entry(rc.spec)

    async def _account_identity(
        self, rc: RegisteredConnector, access_token: str
    ) -> tuple[str, str]:
        """(external_account_id, label) for a freshly linked account; falls back to
        a single default identity for connectors that don't expose one."""
        conn = rc.build(self._deps)
        if isinstance(conn, SupportsAccountIdentity):
            with contextlib.suppress(Exception):  # identity is best-effort; fall back
                return await conn.account_identity(access_token)
        return "default", rc.spec.name

    async def disconnect_account(self, key: str, account_id: int) -> CatalogEntry:
        """Remove one linked account; disable the connector if it was the last."""
        rc = self._require(key)
        await self._accounts.delete(account_id)
        if not await self._accounts.list_for_connector(key):
            inst = await self._store.get(key)
            if inst is not None:
                await self._store.set_status(key, "disabled")
                await self._store.upsert_config(
                    key,
                    self._store.decrypt_config(inst),
                    enabled=False,
                    status="disabled",
                    granted_scopes=inst.granted_scopes,
                )
        await self.refresh()
        return await self._entry(rc.spec)

    async def complete_oauth_by_state(self, *, code: str, state: str) -> CatalogEntry:
        """Resolve the connector from the callback ``state``, then finish OAuth."""
        key = await self._oauth.connector_for_state(state)
        if key is None:
            raise ConnectorError("unknown or expired OAuth state")
        return await self.complete_oauth(key, code=code, state=state)

    # --- sync / test -------------------------------------------------------
    async def sync(self, key: str) -> SyncResult:
        rc = self._require(key)
        inst = await self._store.get(key)
        if inst is None or not inst.enabled:
            raise ConnectorError(f"{key} is not enabled")
        if Capability.INGEST not in rc.spec.capabilities:
            raise ConnectorError(f"{key} does not ingest data")
        conn = rc.build(self._deps)
        if not isinstance(conn, SupportsIngest):
            raise ConnectorError(f"{key} declares ingest but has no sync()")
        ctx = await self._context(rc.spec, inst)
        try:
            result = await conn.sync(ctx)
        except Exception as exc:
            await self._store.set_status(key, "error", last_error=str(exc))
            raise ConnectorError(f"sync failed for {key}: {exc}") from exc
        await self._store.set_last_sync(key, _utcnow())
        await self._store.set_status(key, "connected")
        return result

    async def test_connection(self, key: str) -> Health:
        rc = self._require(key)
        inst = await self._store.get(key)
        if inst is None:
            raise ConnectorError(f"{key} is not configured")
        conn = rc.build(self._deps)
        ctx = await self._context(rc.spec, inst)
        return await conn.test_connection(ctx)

    # --- tool resolution + engine refresh ---------------------------------
    async def connector_tools(self) -> list[Tool]:
        tools: list[Tool] = []
        for inst in await self._store.list_enabled():
            rc = self._registry.get(inst.connector_key)
            if rc is None or Capability.TOOLS not in rc.spec.capabilities:
                continue
            conn = rc.build(self._deps)
            if not isinstance(conn, SupportsTools):
                continue
            ctx = await self._context(rc.spec, inst)
            tools.extend(conn.build_tools(ctx))
        return tools

    async def native_engine_tools(self) -> tuple[str, ...]:
        """Engine-native tool names enabled by connectors (e.g. WebSearch/WebFetch),
        deduped in registration order. Independent of build_tools()."""
        names: list[str] = []
        for inst in await self._store.list_enabled():
            rc = self._registry.get(inst.connector_key)
            if rc is not None:
                names.extend(rc.spec.native_engine_tools)
        return tuple(dict.fromkeys(names))

    async def refresh(self) -> None:
        """Rebuild the agent engine with the current connector tools, swap it in,
        then reconcile channel workers. Works uniformly across all engines."""
        engine = self._rebuild_engine(
            await self.connector_tools(), await self.native_engine_tools()
        )
        self._apply_engine(engine)
        await self._sync_channels()

    async def _sync_channels(self) -> None:
        """Start a background worker for each enabled CHANNEL connector and cancel
        workers whose connector was disabled (or whose task has died)."""
        want: dict[str, ConnectorInstance] = {}
        for inst in await self._store.list_enabled():
            rc = self._registry.get(inst.connector_key)
            if rc is not None and Capability.CHANNEL in rc.spec.capabilities:
                want[inst.connector_key] = inst

        for key, task in list(self._channel_tasks.items()):
            if key not in want or task.done():
                task.cancel()
                del self._channel_tasks[key]

        for key, inst in want.items():
            if key in self._channel_tasks:
                continue
            rc = self._require(key)
            conn = rc.build(self._deps)
            if not isinstance(conn, SupportsChannel):
                continue
            ctx = await self._context(rc.spec, inst)
            self._channel_tasks[key] = asyncio.create_task(
                conn.channel_worker(ctx), name=f"channel:{key}"
            )

    async def shutdown(self) -> None:
        """Cancel all running channel workers (called on app shutdown)."""
        for task in self._channel_tasks.values():
            task.cancel()
        self._channel_tasks.clear()

    async def startup(self) -> None:
        await self._migrate_tokens_to_accounts()
        await self.seed_from_env()
        await self.refresh()

    async def _migrate_tokens_to_accounts(self) -> None:
        """One-time: move pre-multi-account OAuth tokens from an instance's config
        into a ConnectorAccount row, so existing connections keep working. Idempotent
        (skips a connector that already has any account)."""
        for inst in await self._store.list_all():
            rc = self._registry.get(inst.connector_key)
            if rc is None or rc.spec.auth.kind != "oauth2":
                continue
            config = self._store.decrypt_config(inst)
            if not config.get("access_token"):
                continue
            if await self._accounts.list_for_connector(inst.connector_key):
                continue
            external_id, label = await self._account_identity(rc, str(config["access_token"]))
            token_config = {k: config[k] for k in _TOKEN_KEYS if k in config}
            await self._accounts.upsert_by_identity(
                inst.connector_key,
                external_id,
                label=label,
                config=token_config,
                granted_scopes=list(inst.granted_scopes or []),
            )
            settings = {k: v for k, v in config.items() if k not in _TOKEN_KEYS}
            await self._store.upsert_config(
                inst.connector_key,
                settings,
                enabled=inst.enabled,
                status=inst.status,
                granted_scopes=inst.granted_scopes,
            )

    async def seed_from_env(self) -> None:
        """Auto-create instances from legacy env settings on first boot.

        Migration bridge: connectors that used to be plain env flags seed a DB
        instance here once, then are managed from the UI. (OAuth connectors like
        Google Calendar have no env form, so they're skipped.) The `is None` guard
        means this only ever creates — it never re-enables a user-disabled one.
        """
        settings = self._deps.settings
        if settings is None:
            return
        # Web search: WEB_SEARCH_ENABLED → the web_search connector, one time.
        if (
            getattr(settings, "web_search_enabled", False)
            and "web_search" in self._registry
            and await self._store.get("web_search") is None
        ):
            await self._store.upsert_config("web_search", {}, enabled=True, status="connected")

        # Telegram: TELEGRAM_BOT_TOKEN (+ allowed chat ids) → the telegram connector.
        if (
            getattr(settings, "telegram_bot_token", None)
            and "telegram" in self._registry
            and await self._store.get("telegram") is None
        ):
            chats = ",".join(
                str(c) for c in getattr(settings, "telegram_allowed_chat_ids", []) or []
            )
            await self._store.upsert_config(
                "telegram",
                {"bot_token": settings.telegram_bot_token, "allowed_chat_ids": chats},
                enabled=True,
                status="connected",
            )

        # Plaid/Finance: configured (PLAID creds) → the plaid connector, one time.
        # Preserves the old behaviour where finance tools were live whenever Plaid
        # was set up; thereafter it's managed from the marketplace.
        if (
            self._deps.finance is not None
            and "plaid" in self._registry
            and await self._store.get("plaid") is None
        ):
            await self._store.upsert_config("plaid", {}, enabled=True, status="connected")

    # --- internals ---------------------------------------------------------
    def _require(self, key: str) -> RegisteredConnector:
        rc = self._registry.get(key)
        if rc is None:
            raise UnknownConnectorError(key)
        return rc

    async def _context(self, spec: ConnectorSpec, inst: ConnectorInstance) -> ConnectorContext:
        config = self._store.decrypt_config(inst)
        if spec.auth.kind != "oauth2":
            return ConnectorContext(
                key=spec.key, config=config, granted_scopes=tuple(inst.granted_scopes or ())
            )
        # OAuth: tokens live in per-account rows. Populate `accounts` (for aggregation)
        # and `access_token` = the first account (back-compat for single-account tools).
        accounts: list[AccountAuth] = []
        for acc in await self._accounts.list_for_connector(spec.key):
            accounts.append(
                AccountAuth(
                    account_id=acc.id,
                    label=acc.label,
                    access_token=self._account_token_getter(spec, acc.id),
                    granted_scopes=tuple(acc.granted_scopes or ()),
                )
            )
        return ConnectorContext(
            key=spec.key,
            config=config,
            granted_scopes=accounts[0].granted_scopes if accounts else (),
            access_token=accounts[0].access_token if accounts else None,
            accounts=tuple(accounts),
        )

    def _account_token_getter(self, spec: ConnectorSpec, account_id: int) -> Callable[[], Any]:
        async def _token() -> str:
            return await self._account_access_token(spec, account_id)

        return _token

    async def _account_access_token(self, spec: ConnectorSpec, account_id: int) -> str:
        account = await self._accounts.get(account_id)
        if account is None:
            raise ConnectorError(f"account {account_id} not found")
        config = self._accounts.decrypt_config(account)
        token, new_config = await self._oauth.access_token_for(spec, config)
        if new_config is not config:
            rotated = {**config, **{k: new_config[k] for k in _TOKEN_KEYS if k in new_config}}
            await self._accounts.update_config(account_id, rotated)
        return token

    def _validate(self, spec: ConnectorSpec, config: dict[str, Any]) -> dict[str, Any]:
        known = {f.key for f in spec.config_schema}
        unknown = set(config) - known
        if unknown:
            raise ValueError(f"unknown fields: {sorted(unknown)}")
        out: dict[str, Any] = {}
        for f in spec.config_schema:
            value = config.get(f.key)
            if value not in (None, ""):
                if f.type == "select" and f.options and str(value) not in f.options:
                    raise ValueError(f"{f.key} must be one of {list(f.options)}")
                out[f.key] = value
            elif f.default is not None:
                out[f.key] = f.default
            elif f.required:
                raise ValueError(f"missing required field: {f.key}")
        return out
