# Connectors Platform — Design

**Status:** Approved design — 2026-06-23.
**Summary:** Turn Pragya's ad-hoc, env-file-driven integrations into a **production-grade connectors platform**: a single in-app **marketplace** where the user browses available connectors, clicks **Enable**, authenticates (real OAuth 2.0 where it fits, pasted secrets where it doesn't), and the connector lights up — **ingesting data**, **providing tools**, and/or acting as a **channel**. Credentials move out of `.env` into an **encrypted Postgres vault**. Single-user, self-hosted. First deliverable is a **vertical slice — a new Google Calendar (OAuth) connector** that exercises the whole stack end-to-end.

## Goal

Replace "edit `.env`, restart, hope it's wired" with "open Connectors, click Enable, done." A connector enabled from the UI should immediately (no restart) ingest its data, expose its tools to the agent, and/or run as a channel — and its status, health, and scopes should be visible. Make adding the *next* connector cheap.

## The spine — capability model

A connector is not one shape. It **declares one or more composable capabilities**:

| Capability | Meaning | Examples |
|---|---|---|
| **`ingest`** | "download data" — a `sync()` that pulls external data into the connector's **own** store; reports `last_sync` + counts; contributes to the digest. | Finance, Gmail sync, Google Calendar |
| **`tools`** | contributes agent tools, either **`native`** (in-process `build_*_tools()`, today's pattern) or **`mcp`** (mount an MCP server — `stdio` cmd or `http`/`sse` url — and surface its advertised tools). | native: tasks/memory; mcp: any third-party MCP server |
| **`channel`** | a two-way conversational surface: inbound worker (poll/webhook) + outbound sender. **May also declare `ingest`** so messages become stored signals. | Telegram (exists), WhatsApp, Slack |

So **Telegram = `channel` + `ingest`**, **Google Calendar = oauth + `ingest` + `tools(native)`**, **a third-party MCP server = `tools(mcp)`**. One uniform catalog, one "Enable" button, wildly different internals.

## Architecture — `backend/src/pragya_assistant/connectors/`

- **`spec.py`** — the declarative contract: `ConnectorSpec` (identity + `auth` + `config_schema` + `capabilities`), `AuthStrategy` (`oauth2 | secret | managed_widget | none`), `Capability` enum, and `Field` (typed config: `text | secret | url | select | bool | number`, with `required`/`help`/`placeholder`).
- **`base.py`** — the runtime `Connector` Protocol (all methods optional per declared capability):

  ```python
  @dataclass(frozen=True)
  class ConnectorSpec:
      key: str                       # "google_calendar"
      name: str; category: str       # "Google Calendar", "Calendar"
      icon: str; pitch: str          # marketplace card
      auth: AuthStrategy             # oauth2 | secret | managed_widget | none
      config_schema: list[Field]     # typed fields → auto-generated form
      capabilities: set[Capability]  # {ingest, tools, channel}

  class Connector(Protocol):
      async def test_connection(self, inst: ConnectorInstance) -> Health: ...
      async def sync(self, inst: ConnectorInstance) -> SyncResult: ...        # if `ingest`
      def build_tools(self, inst: ConnectorInstance) -> list[Tool]: ...       # if tools+native
      def mcp_mount(self, inst: ConnectorInstance) -> McpMount | None: ...    # if tools+mcp
      def channel_worker(self, inst: ConnectorInstance) -> ChannelWorker: ... # if `channel`
  ```

- **`registry.py`** — every `ConnectorSpec` + impl registers here; this **is** the "list of available connectors." Each connector lives in its own package (`connectors/google_calendar/…`). Existing modules (`calendars/`, `email_inbox/`, `finance/`) stay put and keep working — migrated onto the contract in fast-follow, not now.
- **`models.py` / `store.py`** — `ConnectorInstance` (the enabled state) + async CRUD. The `config` column is **encrypted at rest via the existing shared `pragya_assistant/crypto.py`** (Fernet / `APP_SECRET_KEY` — already top-level, already used by Finance for Plaid tokens; no new crypto). A tiny transient `ConnectorOAuthFlow` table holds in-flight `state` + PKCE `code_verifier`.
- **`manager.py` — `ConnectorManager` (the heart):** merges registry + instances → `catalog()`; handles `enable` / `disable` / `update_config`; on any change **re-resolves the runtime with no restart**. The agent resolves its toolset **from the manager per turn** (cheap, single-user), so a freshly-connected connector's tools appear on the very next message; the digest reads its contributors from the manager at run time; channel workers are started/stopped by the manager.
- **`oauth.py` — OAuth service:** generic **authorization-code + PKCE + refresh rotation**. `start(key) -> authorize_url` (persists `state` + verifier in `ConnectorOAuthFlow`); one shared callback dispatches by `state`; `get_access_token(inst)` auto-refreshes via the refresh token. Per-provider endpoints/scopes come from the spec; the user's one-time `client_id`/`secret` live (encrypted) in the instance config. Redirect target: `{APP_BASE_URL}/connectors/oauth/callback`.

### `ConnectorInstance` (Postgres)

`id`, `connector_key`, `enabled` (bool), `status` (`connected | needs_reconnect | error | disabled`), `config` *(encrypted JSON — secrets + OAuth tokens + settings)*, `granted_scopes` (text[]), `last_sync_at`, `last_error`, `created_at`, `updated_at`. **Unique on `connector_key`** (single-user: one instance per connector).

### env → DB seeding (back-compat, zero-downtime)

On boot, any **existing** connector that has env creds set but **no** DB instance gets auto-seeded as an enabled instance (e.g. `CALENDAR_ICS_URL`, `EMAIL_*`, `PLAID_*`). Nothing breaks on deploy; the UI shows it *Connected* immediately. After that, **DB is the source of truth**; env is just bootstrap.

## API — `api/routes/connectors.py` (behind existing Bearer auth)

`GET /connectors` (catalog) · `GET /connectors/{key}` (detail, **secrets redacted**) · `POST …/enable` (secret/widget) · `POST …/oauth/start` + `GET /connectors/oauth/callback` (OAuth) · `PATCH …` (settings) · `POST …/sync` (ingest now — the existing **cron sidecar** calls this) · `POST …/test` (health) · `POST …/disable` · `DELETE …`. Secrets are **write-only** everywhere (show `configured ••••`, never echoed). Schemas in `api/schemas.py`.

## Frontend — Connectors Marketplace (new tab in `Workspace`)

- **Catalog gallery** — connector cards (icon, category chip, one-line pitch, status badge: *Connected / Available / Needs reconnect / Error*, capability chips: *Ingests · Tools · Channel*). Search + category filter.
- **Detail drawer (auth-aware)** — OAuth → **[Connect with Google]** (+ collapsible first-time "Provider setup" for `client_id`/`secret` with a help link) → then granted scopes + Reconnect/Disconnect; Secret → **auto-generated form from `config_schema`**; Widget → embedded widget (reuse Finance's Plaid Link). Plus a **Health panel** (last sync, counts, last error, "Sync now" / "Test").
- New `lib/api.ts` functions follow the existing fetch + Bearer pattern. The **`frontend-design`** skill is used at build time to hit the "claw plus" bar.

## Block diagram

```
                       ┌──────────────────────────┐
                       │       You · browser        │
                       └─────────────┬──────────────┘
        ┌────────────────────────────▼───────────────────────────┐
        │  FRONTEND · Connectors Marketplace  (new "Connectors" tab)│
        │  catalog gallery  +  auth-aware detail drawer            │
        │  [Connect with Google] · secret form · embed widget      │
        └────────────────────────────┬───────────────────────────┘
                                     │  fetch + Bearer
        ┌────────────────────────────▼───────────────────────────┐
        │  API · FastAPI · /connectors                            │
        │  catalog·enable·oauth/start·oauth/callback·sync·test·…   │
        └────────────────────────────┬───────────────────────────┘
        ┌────────────────────────────▼───────────────────────────┐
        │  CORE · ConnectorManager (the heart)                    │
        │  merges registry+instances · enable/disable ·           │
        │  RE-WIRES runtime, NO restart                           │
        └───┬───────────┬────────────┬─────────────┬─────────────┘
       ┌────▼────┐ ┌────▼─────┐ ┌────▼─────┐ ┌─────▼──────┐
       │Registry │ │Instance  │ │OAuth svc │ │ crypto.py  │
       │avail.   │ │store·DB  │ │PKCE +    │ │ Fernet /   │
       │specs    │ │enc. cfg  │ │refresh   │ │ app secret │
       └─────────┘ └──────────┘ └──────────┘ └────────────┘
        ┌────────────────────────────▼───────────────────────────┐
        │  CONNECTORS · capabilities: ingest · tools[native|mcp] · │
        │  channel  (composable)                                  │
        │   ★ Google Calendar [oauth·ingest·tools] ◄ SLICE        │
        │     Telegram[channel·ingest]·MCP[tools·mcp]·… (future)  │
        └───┬─────────────────────────────────────────┬─────────┘
            │ sync()→download                  tools → │
       ┌────▼─────────────┐  ┌───────────────┐  ┌──────▼────────┐
       │ Postgres         │  │ Agent          │  │ Digest        │
       │ connector_       │  │ toolset per-   │  │ contributors  │
       │ instances + per- │  │ turn fr. mgr   │  │ from manager  │
       │ connector tables │  └───────────────┘  └───────────────┘
       └──────────────────┘
   cron sidecar ─► POST …/sync     External APIs (Google Calendar · OAuth)
```

**Key flows:** (1) **Enable secret/widget** → `/enable` → validate vs `config_schema` → encrypt+store → `test_connection` → *Connected*. (2) **Enable OAuth** → `/oauth/start` (PKCE) → consent → `/oauth/callback` → exchange → store tokens encrypted → re-wire. (3) **Ingest** → cron → `/sync` → `connector.sync()` → external API → bespoke table → digest. (4) **Agent turn** → Agent asks manager for current toolset (native+mcp) → tool calls hit provider / read bespoke store.

## Vertical slice — Google Calendar (OAuth)

`connectors/google_calendar/`: `auth=oauth2` (Google endpoints + **read-only** Calendar scope), `capabilities={ingest, tools}`, config for which calendars + sync window. `sync()` pulls events into its **own** `calendar_events` table; `build_tools()` → `agenda` / `upcoming_events`; contributes a line to the digest. One-time setup: the user creates a Google Cloud OAuth client and pastes `client_id`/`secret` once (documented). This single slice exercises the **entire** platform: registry, encrypted instance, OAuth start→callback→refresh, manager re-wiring, catalog API, the marketplace OAuth flow, bespoke ingest, digest contribution, and health.

## Decisions

- **Google Calendar starts read-only** (`calendar.readonly`) — matches the email connector's "no send/delete, enforced by a test" ethos. Event creation comes later, confirmation-gated.
- **The new Google Calendar connector sits *alongside* the existing `.ics` calendar** — the old one keeps working until a deliberate migration; we don't rip it out in the slice.
- **OAuth is first-class but pluggable** — the same framework still handles pasted secrets and managed widgets, so an `.ics` URL never gets a redirect dance.
- **Per-connector bespoke storage** — the framework standardizes discovery / enable / auth / lifecycle / health / UI, **not** the data schema. Cross-source unified semantic search is a deliberate non-goal (seam left: a connector may later embed its items into the existing pgvector store).
- **No-restart re-wiring** — agent toolset resolved from the manager per turn (single-user simple); revisit only if it ever shows up in latency.

## Out of scope (YAGNI — contract supports, slice doesn't build)

Multi-user / per-user vaults · unified cross-source semantic search · migrating the other 4 connectors onto the contract · channel runtime / Telegram-on-the-contract (incl. the `telegram_poller` container question) · the MCP-client adapter that surfaces `tools(mcp)` to the loop engines · OAuth specs for providers beyond Google.

## Testing (TDD; strict mypy + ruff)

- **Unit:** registry; `ConnectorManager` enable/disable/re-wire; `ConnectorInstance` config **encrypt round-trip**; `config_schema` validation; OAuth service (authorize-URL build, code exchange + refresh rotation via `respx` mocks, `state`/PKCE handling).
- **Connector:** `google_calendar` `sync()` against a mocked Google API + fixtures; `agenda`/`upcoming_events` tools; `health`.
- **API:** connectors routes — auth required, **secrets redacted**, OAuth callback happy + sad (bad `state`, denied consent) paths.
- **Safety:** a test asserting the Google Calendar connector requests **only the read-only scope** (mirrors the email no-send safety test).
- **Frontend:** minimal, following existing conventions.

## Config / dependencies / migration

- **Settings:** add `APP_BASE_URL` (for the OAuth redirect URI). No per-connector env keys are *required* anymore (they remain honored as bootstrap → seeded into DB).
- **Backend deps:** an async HTTP client is already present (`httpx`); no new heavy deps for the slice (Google Calendar via REST + the generic OAuth service). MCP-client dep deferred to the first `tools(mcp)` connector.
- **`.env.example`:** document `APP_BASE_URL`; note that connector creds now live in the in-app vault.
- **Alembic:** new migration — `connector_instances` + `connector_oauth_flow` + `calendar_events`.

## Build slices (→ implementation plan)

1. `spec.py` + `base.py` contract; `registry.py`; unit tests for the contract.
2. `ConnectorInstance` + `ConnectorOAuthFlow` models + migration + `store.py` (encrypted config round-trip).
3. `ConnectorManager` (catalog / enable / disable / re-wire) + env→DB seeding; wire agent toolset + digest to resolve from the manager.
4. Generic OAuth service (PKCE, start, callback, refresh) with `respx` tests.
5. `connectors/google_calendar/` — spec, OAuth wiring, `sync()` + `calendar_events`, tools, digest line, read-only safety test.
6. API router `api/routes/connectors.py` + schemas (catalog, enable, oauth, sync, test, disable, delete).
7. Frontend marketplace: catalog gallery + auth-aware detail drawer + health panel + `lib/api.ts` (uses `frontend-design`).
8. End-to-end verification: connect Google Calendar from the UI → events ingested → tools answer → digest line → health/reconnect.

## Risks / open items

- **OAuth redirect URI** must be registered in the Google Cloud OAuth client and match `APP_BASE_URL`; `http://localhost` is allowed for local dev, a real host needed once deployed.
- **Token refresh edge cases** (revoked/expired refresh token) → surface as `needs_reconnect` in the UI.
- **Re-wire model** (per-turn toolset resolution) is the simple choice; if a connector's tool-build becomes expensive, add memoization keyed by instance `updated_at`.
- **Channel runtime** (in-process worker vs the existing separate `telegram_poller` container) is deferred but will need a decision when Telegram moves onto the contract.
