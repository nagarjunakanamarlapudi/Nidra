# Phase 5: Finance (Plaid) — Design

**Status:** Approved design — 2026-06-21.
**Summary:** Read-only personal-finance awareness for Pragya via **Plaid**. Pull balances, transactions, investment holdings, and liabilities (incl. mortgage) from the user's US institutions; surface them through chat tools and the digest. **No money movement, ever.**

## Goal

Let Pragya answer money questions and brief the user proactively: *"what's my checking balance?"*, *"how much did I spend on dining last month?"*, *"what's my net worth?"*, *"when's my mortgage payment due and how much?"* — and fold balances / bills-due / notable spend into the daily digest, with a deeper weekly finance digest.

## Scope (full v1)

- Connect US institutions via **Plaid Link** — personal-use **Trial** (free, ≤10 institutions; bundles Transactions, Balance, Investments, Liabilities).
- Pull + persist: **accounts & balances**, **transactions** (Plaid-categorized), **investment holdings**, **liabilities** (mortgage/credit/student: APR, next payment).
- Surface via: **chat tools** + a **finance line in the daily digest** + a **weekly finance digest**.
- **Sandbox-first**: build/test the whole pipeline against Plaid Sandbox; go live by adding real keys + linking accounts.

## Non-goals

- No transfers / payments / money movement — we use only Plaid **read** products; no transfer product is enabled.
- No full Plaid **Production** plan (only needed for >10 institutions or products outside the Trial bundle).
- No column-level encryption of transaction details in v1 (see Security decision).
- Not multi-user; single-user self-hosted assumptions hold.

## Architecture — `backend/src/pragya_assistant/finance/`

Mirrors the `email_inbox/` layout (clear, testable units):

- **`client.py`** — `PlaidClient`, a thin wrapper over the official `plaid-python` SDK, injectable so tests use a fake or Sandbox. Methods: `create_link_token()`, `exchange_public_token(public_token)`, `get_accounts(token)`, `sync_transactions(token, cursor)`, `get_holdings(token)`, `get_liabilities(token)`.
- **`models.py`** — SQLAlchemy ORM: `PlaidItem`, `Account`, `Transaction`, `Holding`, `Liability`.
- **`store.py`** — `FinanceStore`: async upsert + query over `session_factory` (no Plaid calls — queries read Postgres).
- **`service.py`** — `FinanceService`: orchestrates `sync()` (client → store) and answers queries (spending, net worth, bills); `build_finance_service(settings, session_factory)` returns `None` when Plaid is unconfigured.
- **`tools.py`** — `build_finance_tools(service)`: model-facing chat tools (read-only).
- **`crypto.py`** — `encrypt_token` / `decrypt_token` (Fernet keyed by `APP_SECRET_KEY`).
- **`api/finance.py`** — routes for the Link flow + manual sync + accounts list (for the web UI).
- **Frontend** — a **"Connect a bank"** page (`react-plaid-link`) + a simple accounts view.
- **Wiring** — `FinanceService` built in `api/deps.py` + `mcp_memory.py`; finance tools added to `build_agent_tools(...)`; a daily **sync job** registered on the existing APScheduler.

## Data model (Postgres — durable, needed for trends)

- **PlaidItem** — one per connected institution: `id`, `institution_name`, `access_token` *(encrypted)*, `item_id`, `transactions_cursor`, `created_at`, `last_synced_at`.
- **Account** — `id`, `item_id` (FK), `plaid_account_id`, `name`, `official_name`, `type`, `subtype` (checking/savings/credit/brokerage/mortgage/…), `mask`, `current_balance`, `available_balance`, `iso_currency`, `updated_at`.
- **Transaction** — `id`, `account_id` (FK), `plaid_txn_id`, `date`, `name`, `merchant_name`, `amount`, `category`, `pending`.
- **Holding** — `id`, `account_id` (FK), `security_name`, `ticker`, `quantity`, `price`, `value`, `iso_currency`.
- **Liability** — `id`, `account_id` (FK), `type` (mortgage/credit/student), `apr`, `next_payment_due_date`, `next_payment_amount`, `last_payment_amount`, `principal`/`balance`.

## The Link flow (one-time per institution)

1. Web app → `POST /finance/link/token` → backend `create_link_token()` → returns `link_token`.
2. **Plaid Link** widget opens → user authenticates with the bank *inside Plaid* → returns a `public_token`.
3. Web app → `POST /finance/link/exchange {public_token}` → backend `exchange_public_token()` → permanent **`access_token`** → **encrypt + store** as a `PlaidItem`, then pull + store initial accounts.

## Sync strategy

- **`transactions/sync`** (cursor-based, incremental): store `transactions_cursor` per item; apply `added` / `modified` / `removed` to the DB.
- Refresh **balances**, **holdings**, **liabilities** on each sync.
- **Cadence:** a **daily** APScheduler job (`finance_sync`) + a **"sync now"** endpoint and tool. All chat/digest queries read Postgres — never a Plaid call per question.

## Surfacing

**Chat tools** (read-only):
- `account_balances` — balances across accounts.
- `spending_summary` — totals by category / period.
- `search_transactions` — by merchant / amount / date range.
- `net_worth` — total account balances minus credit/loan debts (investment balances already include holdings).
- `holdings` — portfolio positions + values.
- `upcoming_bills` — liability due dates + amounts, credit-card payments.

**Digest:**
- **Daily** digest gains a concise finance line (key balances, bills due in N days, notable/large transactions).
- **Weekly** finance digest (own scheduled job): spending by category, net-worth change week-over-week, upcoming bills.

## Security

- **Access token encrypted at rest** (Fernet via `APP_SECRET_KEY`); never logged.
- `PLAID_CLIENT_ID` / `PLAID_SECRET` via `Settings`, under the fail-fast secrets guard when `APP_ENV != local`.
- **Read-only**: only Plaid read products; no transfer/payment product enabled. A safety test asserts the module references no transfer endpoints.
- **Decision (encryption scope):** encrypt the **access token only**. Account/transaction/holding/liability rows are stored as normal columns in the single-user, access-controlled Postgres so spending **aggregation works in SQL**. Column-level encryption of amounts/descriptions would disable in-DB aggregation — deferred as possible future hardening, not in v1.

## Testing (sandbox-first, TDD)

- **Plaid Sandbox** `/sandbox/public_token/create` lets us test the **entire** flow (create item → exchange → sync → query) **automatically — no UI, no real credentials.**
- **Unit tests:** `FinanceStore`, `FinanceService`, and tools against a **fake `PlaidClient`** + fixtures (accounts, transactions, holdings, liabilities).
- **Integration (marked):** an optional live-Sandbox test for the real API shape.
- **Safety test:** no transfer/payment Plaid endpoints referenced in `finance/`.

## Config / dependencies / migration

- **Backend dep:** `plaid-python`. **Frontend dep:** `react-plaid-link`.
- **Settings:** `plaid_client_id`, `plaid_secret`, `plaid_env` (default `"sandbox"`). Feature off when client_id/secret unset.
- **`.env.example`:** document `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENV`.
- **Alembic `0004`:** create the five finance tables.

## Build slices (→ implementation plan)

1. Config + deps + `PlaidClient` (Sandbox) + token crypto.
2. Data model + migration + `FinanceStore`.
3. Link flow (backend routes) + exchange + store accounts; frontend "Connect a bank".
4. `transactions/sync` + `spending_summary` / `search_transactions` / `account_balances` tools.
5. Investments (holdings) + `net_worth` / `holdings` tools.
6. Liabilities (mortgage) + `upcoming_bills` tool.
7. Digest: daily finance line + weekly finance digest job.
8. Scheduler sync job; wire finance tools into all engines; full live-Sandbox verification.

## Decisions

- **Encryption:** access token only (v1) — rationale above.
- **Weekly finance digest:** included in v1 (full scope; no rush to ship).

## Risks / open items

- **Plaid Trial terms** (ongoing vs time-boxed; exact free limits) — confirm at signup; the Sandbox build is unaffected either way.
- **OAuth banks** (Chase, etc.) need an allowlisted redirect URI for production — handle at go-live.
- **Categorization quality** — rely on Plaid's personal-finance categories; refine later if needed.
