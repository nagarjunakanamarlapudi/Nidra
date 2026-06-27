# Connectors Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline, TDD). Steps use checkbox (`- [ ]`) syntax for tracking. Each task ends green: `make -C backend check` (lint + fmt-check + typecheck + test) must pass before commit.

**Goal:** A production-grade connectors platform — an in-app marketplace where the single user enables connectors (OAuth 2.0 / pasted secrets / managed widgets), credentials live in an encrypted Postgres vault, and an enabled connector lights up ingestion + tools with no restart. First shipped connector: Google Calendar (OAuth, read-only).

**Architecture:** A declarative `ConnectorSpec` + a `Connector` runtime protocol with composable capabilities (`ingest` / `tools[native|mcp]` / `channel`). A `ConnectorRegistry` lists what's available; `ConnectorInstance` rows (encrypted `config`) are what's enabled. A `ConnectorManager` merges the two, owns enable/disable/sync/test, and rebuilds the agent engine on change (uniform across loop/codex/claude-code engines → no restart). A generic `OAuthService` (authorization-code + PKCE + refresh rotation) handles OAuth connectors. Existing connectors (`calendars/`, `email_inbox/`, `finance/`) keep working untouched; env creds auto-seed DB instances on boot.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, Pydantic v2 settings, httpx, cryptography (Fernet), pytest + pytest-asyncio (`asyncio_mode=auto`) + respx; Next.js (App Router — read `node_modules/next/dist/docs/` first), Tailwind v4, vanilla fetch + Bearer.

## Global Constraints

- TDD, no patches: write the failing test first, minimal impl, green, commit. One logical change per commit.
- Every task ends with `make -C backend check` green (ruff, ruff format --check, mypy src, pytest). Frontend: `make -C frontend check`.
- Strict mypy (`mypy_path=src`, pydantic plugin) — full type annotations, no `Any` leakage across public interfaces.
- Tests are hermetic: add every new app env var to `_APP_ENV_VARS` in `tests/conftest.py` (currently autouse-cleared). New env var this feature: `APP_BASE_URL`.
- Secrets at rest: encrypt the connector `config` JSON via the shared `pragya_assistant.crypto` (`encrypt_secret`/`decrypt_secret`, Fernet keyed by `APP_SECRET_KEY`). Never log or API-echo secret values.
- Tests create schema via `Base.metadata.create_all` (conftest) — new ORM models work in tests immediately; production still needs an Alembic migration (verify with `make -C backend migrate` against local db).
- Single-user: one `ConnectorInstance` per `connector_key` (UNIQUE). No multi-tenancy.
- Do not break the existing 5 connectors or any current test.
- Commit locally only; do NOT push (user rule [[dont-push-without-asking]]). Work on branch `feat/connectors-platform`.

## File Structure

**New backend package `backend/src/pragya_assistant/connectors/`:**
- `spec.py` — declarative contract: `Field`, `FieldType`, `Capability`, `AuthKind`, `OAuthConfig`, `AuthStrategy`, `ConnectorSpec`.
- `base.py` — runtime types: `Health`, `SyncResult`, `McpMount`, `ConnectorContext`, `Connector` (Protocol), `ConnectorDeps`, `RegisteredConnector`.
- `registry.py` — `ConnectorRegistry` + `build_default_registry(deps)`.
- `store.py` — `ConnectorInstanceStore`, `OAuthFlowStore` (encrypt/decrypt config here).
- `oauth.py` — `OAuthService` (PKCE, authorize URL, code exchange, refresh, `access_token_for`).
- `manager.py` — `ConnectorManager` (catalog/enable/oauth/sync/test/disable/delete + tool resolution + engine refresh + env seeding).
- `google_calendar/` — `spec.py` (the `ConnectorSpec`), `client.py` (httpx Google Calendar REST), `connector.py` (`GoogleCalendarConnector`: sync/tools/test), `store.py` (`CalendarEventStore`), `digest.py` (digest line).

**Modified backend:**
- `memory/models.py` — add `ConnectorInstance`, `ConnectorOAuthFlow`, `CalendarEvent`.
- `migrations/versions/0009_connectors.py` — new tables.
- `config.py` — add `app_base_url: str = "http://localhost:3000"`.
- `agent/toolset.py`, `agent/factory.py` — accept `connector_tools: list[Tool]`.
- `api/deps.py` — wire registry/oauth/manager into `AppComponents`; `get_connectors` dep; rebuild/apply-engine closures.
- `api/app.py` — lifespan startup `await components.connectors.startup()`; include connectors router.
- `api/schemas.py` — connector DTOs.
- `api/routes/connectors.py` — the router.
- `digests/service.py` — accept extra digest contributors (connector lines).
- `tests/conftest.py` — add `APP_BASE_URL` to `_APP_ENV_VARS`; a `build_connectors_app` helper/fixture.

**Frontend:**
- `lib/api.ts` — connector client functions + types.
- `app/Connectors.tsx` (+ small subcomponents) — marketplace gallery + detail drawer.
- `app/Workspace.tsx` — add the "Connectors" tab.
- OAuth return handled by backend redirect to `app_base_url` with `?connector&status`.

---

## Phase 1 — Contract + Registry

### Task 1: Declarative spec + runtime contract
**Files:** Create `connectors/spec.py`, `connectors/base.py`; Test `tests/connectors/test_spec.py`.
**Produces:** `Field`, `FieldType="text|secret|url|select|bool|number"`, `Capability(Enum: INGEST/TOOLS/CHANNEL)`, `AuthKind="none|secret|oauth2|managed_widget"`, `OAuthConfig(authorize_url, token_url, scopes: tuple[str,...], extra_authorize_params: dict, user_provided_client: bool=True)`, `AuthStrategy(kind, oauth: OAuthConfig|None, widget: str|None)`, `ConnectorSpec(key, name, category, pitch, icon, auth, capabilities: frozenset[Capability], config_schema: tuple[Field,...], docs_url)`. In `base.py`: `Health(ok: bool, detail: str|None)`, `SyncResult(items: int, detail: str|None)`, `McpMount(...)`, `ConnectorContext(key, config: dict[str,Any], granted_scopes: tuple[str,...], access_token: Callable[[], Awaitable[str]] | None)`, `Connector` Protocol (`test_connection(ctx)->Health`; optional `sync(ctx)->SyncResult`, `build_tools(ctx)->list[Tool]`, `mcp_mount(ctx)->McpMount|None`, `channel_worker(ctx)->Any`), `ConnectorDeps(session_factory, settings)`, `RegisteredConnector(spec, build: Callable[[ConnectorDeps], Connector])`.
**Tests:** construct a `ConnectorSpec` with each auth kind; `Capability.INGEST in spec.capabilities`; `Field` defaults (`required=True`, `type="text"`); frozen dataclasses immutable.
**TDD:** failing test → dataclasses/enums → green → commit `feat(connectors): declarative spec + runtime contract`.

### Task 2: Registry
**Files:** Create `connectors/registry.py`; Test `tests/connectors/test_registry.py`.
**Interfaces:** Consumes Task 1. Produces `ConnectorRegistry` (`register(rc: RegisteredConnector)`, `get(key)->RegisteredConnector|None`, `all_specs()->list[ConnectorSpec]`, `__contains__`), and `build_default_registry(deps: ConnectorDeps)->ConnectorRegistry` (seeded with Google Calendar in Task 8; empty stub now).
**Tests:** register + get; unknown key → None; duplicate key overwrites with a warning-free upsert; `all_specs` ordering stable (sorted by `name`).
**Commit:** `feat(connectors): registry`.

## Phase 2 — Persistence + encrypted config

### Task 3: ORM models
**Files:** Modify `memory/models.py`; Test `tests/connectors/test_models.py`.
**Produces:** `ConnectorInstance` (`id`, `connector_key: str unique index`, `enabled: bool=False`, `status: str="disabled"`, `config: str=""` (encrypted JSON), `granted_scopes: list[str]|None` JSONB, `last_sync_at: dt|None`, `last_error: str|None`, `created_at`, `updated_at server_default+onupdate`); `ConnectorOAuthFlow` (`state: str pk`, `connector_key`, `code_verifier: str`, `created_at`); `CalendarEvent` (`id`, `connector_key index`, `uid: str index`, `summary`, `location|None`, `start: dt`, `end: dt|None`, `all_day: bool`, `calendar_id|None`, `updated_at`); UNIQUE(`connector_key`,`uid`).
**Tests:** insert + read each via `session` fixture; `connector_key` uniqueness raises on duplicate.
**Commit:** `feat(connectors): instance, oauth-flow, calendar-event models`.

### Task 4: Stores (encrypted config)
**Files:** Create `connectors/store.py`; Test `tests/connectors/test_store.py`.
**Produces:** `ConnectorInstanceStore(session_factory, app_secret_key)`: `get(key)->ConnectorInstance|None`, `list()`, `list_enabled()`, `upsert_config(key, config: dict, *, enabled, status, granted_scopes=None)`, `patch_config(key, partial: dict)`, `set_status(key, status, *, last_error=None)`, `set_last_sync(key, when)`, `delete(key)`, and `decrypt_config(inst)->dict` / `encrypt_config(dict)->str` helpers (Fernet via crypto). `OAuthFlowStore(session_factory)`: `create(state, connector_key, code_verifier)`, `pop(state)->ConnectorOAuthFlow|None` (read+delete), `purge_older_than(seconds)`.
**Tests:** config encrypt→decrypt round-trip; stored `config` column is ciphertext (not plaintext substring); `list_enabled` filters; `patch_config` merges; oauth flow create→pop returns then second pop is None.
**Commit:** `feat(connectors): encrypted instance store + oauth-flow store`.

### Task 5: Alembic migration
**Files:** Create `migrations/versions/0009_connectors.py` (down_revision `0008`); no new test (covered by model tests + manual `make migrate`).
**Steps:** hand-write `op.create_table` for `connector_instances`, `connector_oauth_flow`, `calendar_events` mirroring Task 3 columns + indexes/uniques; `downgrade` drops them. Verify: `make -C backend migrate` (upgrade) then `alembic downgrade -1` then upgrade again, against local `pragya` db.
**Commit:** `feat(connectors): 0009 migration`.

## Phase 3 — OAuth service

### Task 6: Generic OAuth 2.0 (PKCE + refresh)
**Files:** Create `connectors/oauth.py`; Test `tests/connectors/test_oauth.py`.
**Produces:** `OAuthService(flow_store, *, app_base_url, now=callable)`:
- `start(spec, instance_config) -> str` (authorize URL): generate `code_verifier` (43–128 url-safe), S256 `code_challenge`, random `state`; persist flow; build URL from `spec.auth.oauth` with `client_id` (from instance_config), `redirect_uri = {app_base_url}/connectors/oauth/callback`, `scope`, `state`, `code_challenge`, `code_challenge_method=S256`, plus `extra_authorize_params` (e.g. `access_type=offline`, `prompt=consent`).
- `exchange(spec, instance_config, *, code, state) -> OAuthToken` (validate+pop state, POST token_url with verifier via httpx, return `OAuthToken(access_token, refresh_token, expires_at, scope)`).
- `refresh(spec, instance_config, refresh_token) -> OAuthToken`.
- `access_token_for(spec, config) -> tuple[str, dict]`: returns a valid access token, refreshing if `expires_at` within 60s; returns possibly-updated config so the caller persists rotated tokens.
**Tests (respx):** authorize URL contains state+S256 challenge+redirect+scope; `exchange` posts code+verifier and parses tokens (compute `expires_at` from `expires_in` via injected `now`); bad/missing state → `ValueError`; `refresh` swaps access token, keeps refresh when provider omits a new one; `access_token_for` refreshes when expired, no-ops when fresh.
**Commit:** `feat(connectors): generic OAuth2 service (PKCE + refresh)`.

## Phase 4 — Manager

### Task 7: ConnectorManager (core: catalog/enable/disable)
**Files:** Create `connectors/manager.py`; Test `tests/connectors/test_manager.py`.
**Produces:** `ConnectorManager(registry, instance_store, oauth, *, rebuild_engine: Callable[[list[Tool]], AgentEngine], apply_engine: Callable[[AgentEngine], None], settings)`:
- `async catalog() -> list[CatalogEntry]` — every spec merged with its instance status (key, name, category, pitch, icon, capabilities, auth kind, status, enabled, last_sync_at, last_error, granted_scopes, config_schema, configured-field presence — never secret values).
- `async detail(key) -> CatalogEntry | None`.
- `async enable_secret(key, config: dict) -> CatalogEntry` — validate against `config_schema` (required present, select within options, bool/number coerce), encrypt+store enabled/connected, `test_connection`, then `await self.refresh()`.
- `async disable(key)` / `async delete(key)` → refresh.
**Tests:** catalog merges spec+instance; `enable_secret` validation rejects missing required + unknown field; stored config encrypted; `test_connection` failure → status `error`; disable flips status; refresh invoked (spy).
**Commit:** `feat(connectors): manager core (catalog/enable/disable)`.

### Task 7b: Manager OAuth orchestration
**Files:** Modify `connectors/manager.py`; Test add to `tests/connectors/test_manager.py`.
**Produces:** `async start_oauth(key, client_config: dict) -> str` (store partial config = client_id/secret, status `connecting`; return `oauth.start(...)`); `async complete_oauth(key, *, code, state) -> CatalogEntry` (exchange, merge tokens+granted_scopes into config, status `connected`, refresh); maps token errors → status `needs_reconnect`.
**Tests (fake OAuthService):** start persists client creds + returns URL; complete stores tokens encrypted, sets scopes, refreshes; failed exchange → `needs_reconnect`.
**Commit:** `feat(connectors): manager OAuth orchestration`.

### Task 7c: Manager tools + sync + refresh + env seeding
**Files:** Modify `connectors/manager.py`; Test add.
**Produces:** `async connector_tools() -> list[Tool]` (enabled + `TOOLS`-capable → build a `ConnectorContext` (decrypted config; `access_token` closure for oauth via `oauth.access_token_for`, persisting rotated tokens) → `connector.build_tools(ctx)`); `async sync(key) -> SyncResult` (`INGEST`-capable; update `last_sync_at`/`last_error`); `async test_connection(key) -> Health`; `async refresh()` (`apply_engine(rebuild_engine(await connector_tools()))`); `async startup()` (`seed_from_env()` then `refresh()`); `async seed_from_env()` (for known env-backed connectors with creds set and no instance, create enabled instance — Google Calendar has no env form, so this is a no-op hook now + a documented extension point).
**Tests:** `connector_tools` returns tools only for enabled tools-connectors; `sync` sets `last_sync_at`; `refresh` calls rebuild+apply with current tools; oauth tool ctx refreshes token and persists rotation.
**Commit:** `feat(connectors): tool resolution, sync, engine refresh, env seeding`.

## Phase 5 — Google Calendar connector

### Task 8: CalendarEvent store
**Files:** Create `connectors/google_calendar/store.py`; Test `tests/connectors/google_calendar/test_store.py`.
**Produces:** `CalendarEventStore(session_factory)`: `replace_for(connector_key, events: list[RawEvent])` (delete-then-insert by connector_key, upsert by `(connector_key, uid)`), `events_between(connector_key, start, end)->list[CalendarEvent]`, `count(connector_key)->int`. `RawEvent` dataclass (`uid, summary, location, start, end, all_day, calendar_id`).
**Tests:** replace inserts; replace again updates/removes; `events_between` filters + orders by start.
**Commit:** `feat(gcal): calendar-event store`.

### Task 8b: Google Calendar client + connector (sync)
**Files:** Create `connectors/google_calendar/client.py`, `connectors/google_calendar/connector.py`, `connectors/google_calendar/spec.py`; Test `tests/connectors/google_calendar/test_connector.py`.
**Produces:** `GoogleCalendarClient` (httpx; `async list_events(access_token, *, time_min, time_max, calendar_id="primary")->list[RawEvent]` hitting `https://www.googleapis.com/calendar/v3/calendars/{id}/events` with `Authorization: Bearer`, paginating `pageToken`, parsing dateTime/date+all_day). `GOOGLE_CALENDAR_SPEC: ConnectorSpec` (key `google_calendar`, auth oauth2 with `authorize_url=https://accounts.google.com/o/oauth2/v2/auth`, `token_url=https://oauth2.googleapis.com/token`, scopes `("https://www.googleapis.com/auth/calendar.readonly",)`, `extra_authorize_params={access_type:"offline", prompt:"consent"}`, config_schema = client_id (text), client_secret (secret), calendar_id (text, default "primary", required False), sync_days_ahead (number default 30)). `GoogleCalendarConnector(session_factory)`: `sync(ctx)` (token via `ctx.access_token()`; window today−1d…+sync_days_ahead; `client.list_events`; `store.replace_for`; return `SyncResult(items=count)`), `test_connection(ctx)` (list_events for a 1-day window → `Health(ok=True)` / error).
**Tests (respx):** sync pulls events from a mocked Google response into the store (assert count + a parsed event); pagination across two pages; all-day event parsing; `test_connection` ok + failure paths.
**Commit:** `feat(gcal): client, spec, connector sync`.

### Task 8c: Google Calendar tools + read-only safety + digest + registry
**Files:** Create `connectors/google_calendar/tools.py`, `connectors/google_calendar/digest.py`; modify `connectors/registry.py` (register in `build_default_registry`); Test `tests/connectors/google_calendar/test_tools.py`, `test_safety.py`.
**Produces:** `build_tools(ctx)->[gcal_agenda, gcal_upcoming]` reading `CalendarEventStore.events_between` (read from DB; no token needed). Digest line builder. Register `RegisteredConnector(GOOGLE_CALENDAR_SPEC, lambda deps: GoogleCalendarConnector(deps.session_factory))` in `build_default_registry`.
**Tests:** tools format events from the store; **safety test:** `GOOGLE_CALENDAR_SPEC.auth.oauth.scopes == ("…/calendar.readonly",)` and the package contains no write scope / no `events.insert|update|delete|patch` strings (mirrors email no-send test).
**Commit:** `feat(gcal): read-only tools + digest + register; safety test`.

## Phase 6 — API

### Task 9: Connectors router
**Files:** Modify `api/schemas.py`; create `api/routes/connectors.py`; Test `tests/api/test_connectors.py`.
**Produces:** DTOs (`ConnectorSummaryOut`, `ConnectorDetailOut`, `ConnectorFieldOut`, `EnableSecretIn`, `OAuthStartIn`, `OAuthStartOut`); router (prefix none, tag `connectors`, `dependencies=[Depends(require_token)]`): `GET /connectors`, `GET /connectors/{key}`, `POST /connectors/{key}/enable` (secret), `POST /connectors/{key}/oauth/start`→`{authorize_url}`, `GET /connectors/oauth/callback?code&state` (no auth dep — provider redirect; on success/fail `RedirectResponse` to `{app_base_url}/?connector={key}&status=...`), `POST /connectors/{key}/sync`, `POST /connectors/{key}/test`, `POST /connectors/{key}/disable`, `DELETE /connectors/{key}`. Secrets never in responses.
**Tests:** add `build_connectors_app` fixture (wires a `ConnectorManager` over the test db + a fake registry incl. a secret connector + an oauth connector with a fake OAuthService). Assert: 401 without token; catalog shape; enable secret → connected + secret redacted; oauth/start returns URL; callback redirects + stores tokens; sync/test/disable/delete; unknown key → 404.
**Commit:** `feat(api): connectors router`.

## Phase 7 — Wiring (no-restart re-wire)

### Task 10: Compose into the app
**Files:** Modify `config.py`, `agent/toolset.py`, `agent/factory.py`, `api/deps.py`, `api/app.py`, `digests/service.py`, `tests/conftest.py`; Test `tests/api/test_connectors_wiring.py`.
**Produces:** `Settings.app_base_url`; `build_agent_tools(..., connector_tools: list[Tool] | None = None)` appends them; `build_engine(..., connector_tools=None)` threads through; `build_components` constructs `ConnectorDeps`, `build_default_registry`, `OAuthFlowStore`, `OAuthService`, `ConnectorInstanceStore`, `ConnectorManager` with `rebuild_engine=lambda tools: build_engine(settings, memory, task_store, calendar_service, email_service, finance, connector_tools=tools)` and `apply_engine=lambda eng: (setattr(components,'agent',eng), components.digests.set_engine(eng))`; `AppComponents.connectors`; `get_connectors` dep; `app.py` lifespan startup `await resolved.connectors.startup()`; include connectors router; `DigestService.set_engine`.
**Tests:** build components (real db) → enable a (fake) tools-connector via manager → `components.agent` registry now includes its tool (proves no-restart re-wire); lifespan startup seeds + refreshes without error.
**Commit:** `feat(connectors): wire registry/manager/oauth into the app + no-restart re-wire`.

## Phase 8 — Frontend marketplace (read `node_modules/next/dist/docs/` first)

### Task 11: API client
**Files:** Modify `frontend/lib/api.ts`; (frontend tests if present, else manual `make -C frontend check`).
**Produces:** types (`ConnectorSummary`, `ConnectorDetail`, `ConnectorField`) + `listConnectors`, `getConnector`, `enableConnectorSecret(key, config)`, `startConnectorOAuth(key, clientConfig)`, `syncConnector`, `testConnector`, `disableConnector`, `deleteConnector` — reuse `getJson`/`postJson`/`postJsonBody` + error handling.
**Commit:** `feat(web): connectors API client`.

### Task 12: Marketplace UI + tab (use frontend-design skill)
**Files:** Create `frontend/app/Connectors.tsx` (+ subcomponents as needed); modify `frontend/app/Workspace.tsx` (add `"connectors"` to `View`, tab button, render).
**Produces:** catalog gallery (cards: icon, name, category chip, pitch, status badge, capability chips; search + category filter); detail drawer (auth-aware: OAuth "Connect" + collapsible client_id/secret setup; secret auto-form from `config_schema`; managed-widget slot; health panel with last sync / error / Sync now / Test / Disconnect). On OAuth return (`?connector&status` query) show a toast + refresh. Match the warm Tailwind theme tokens in `globals.css`.
**Commit:** `feat(web): connectors marketplace UI`.

### Task 13: End-to-end verification
- `make -C backend check` green; `make -C frontend check` green.
- `make migrate` applies 0009; app boots; `GET /connectors` shows Google Calendar as *Available*.
- Drive OAuth with a real Google Cloud OAuth client if creds available; else document the one-time setup. Mocked-Google tests already prove sync→tools→digest.
- Update `.env.example` (`APP_BASE_URL`) and `docs/ARCHITECTURE.md` if it enumerates connectors; `make docs-check`.
**Commit:** `docs(connectors): .env.example + architecture; e2e verification notes`.

## Self-Review (against the spec)

- Capability model (ingest/tools[native|mcp]/channel) → Task 1; mcp/channel are contract-only (out-of-scope build) ✓
- Marketplace catalog + enable + auth-aware UI → Tasks 9, 11, 12 ✓
- Encrypted vault replacing env → Tasks 4, 10 (seeding) ✓
- OAuth 2.0 PKCE + refresh → Task 6; orchestration 7b; route callback 9 ✓
- No-restart re-wire → Task 7c + 10 ✓
- Google Calendar read-only slice (ingest+tools+digest+safety) → Tasks 8/8b/8c ✓
- Per-connector bespoke storage → `calendar_events` (Task 3/8) ✓
- Tests incl. encrypt round-trip, OAuth, redaction, read-only safety → Tasks 4/6/8c/9 ✓
- Out-of-scope (multi-user, unified search, other-connector migration, channel runtime, mcp adapter, non-Google OAuth) → not built; seams present ✓
