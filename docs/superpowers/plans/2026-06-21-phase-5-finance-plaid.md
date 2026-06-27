# Phase 5: Finance (Plaid) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Pragya read-only awareness of the user's US finances (balances, transactions, investment holdings, liabilities) via Plaid, surfaced through chat tools and the digest — no money movement.

**Architecture:** A new `finance/` module (client/store/service/tools) following the `tasks/` + `email_inbox/` patterns. ORM models live in `memory/models.py` alongside `Task`. Plaid access tokens are encrypted at rest with a Fernet helper keyed by `APP_SECRET_KEY`. The whole pipeline is built and tested against **Plaid Sandbox** (no UI, no real creds); going live = real keys + linking accounts once.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Alembic, `plaid-python`, `cryptography` (already a dep), pytest; Next.js + `react-plaid-link` for the connect page.

## Global Constraints

- Package is `pragya_assistant`; tests run with `TEST_DATABASE_URL=postgresql+asyncpg://pragya:pragya@localhost:5432/pragya_test`.
- Gates that must stay green after every task: `uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest` (run from `backend/`). Line length 100.
- Strict mypy: annotate everything; untyped third-party libs go in the `[[tool.mypy.overrides]]` `ignore_missing_imports` list in `backend/pyproject.toml`.
- TDD: every code change starts with a failing test. Money fields use `Numeric(12, 2)` → `Decimal`.
- **Read-only**: only Plaid read products. No transfer/payment endpoints anywhere in `finance/`.
- **Secrets**: `PLAID_SECRET` and the Plaid access token are never logged. Access token is encrypted at rest.
- **Commits are local only** (do not `git push`) per project policy.
- Expose every new routine as a `make` target where one would naturally be added.

---

### Task 1: Token-encryption helper

**Files:**
- Create: `backend/src/pragya_assistant/crypto.py`
- Test: `backend/tests/test_crypto.py`

**Interfaces:**
- Produces: `encrypt_secret(plaintext: str, app_secret_key: str) -> str`, `decrypt_secret(token: str, app_secret_key: str) -> str` — Fernet round-trip, key derived from `app_secret_key`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_crypto.py
import pytest

from pragya_assistant.crypto import decrypt_secret, encrypt_secret

KEY = "a-test-secret-key-long-enough"


def test_round_trip() -> None:
    token = encrypt_secret("access-sandbox-123", KEY)
    assert token != "access-sandbox-123"  # actually encrypted
    assert decrypt_secret(token, KEY) == "access-sandbox-123"


def test_wrong_key_fails() -> None:
    token = encrypt_secret("secret", KEY)
    with pytest.raises(Exception):
        decrypt_secret(token, "a-different-secret-key-entirely")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_crypto.py -q`
Expected: FAIL — `ModuleNotFoundError: pragya_assistant.crypto`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/src/pragya_assistant/crypto.py
"""Symmetric encryption for secrets at rest (e.g. Plaid access tokens).

The Fernet key is derived from APP_SECRET_KEY so no extra key management is
needed for a single-user deploy.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet


def _key(app_secret_key: str) -> bytes:
    digest = hashlib.sha256(app_secret_key.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_secret(plaintext: str, app_secret_key: str) -> str:
    return Fernet(_key(app_secret_key)).encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str, app_secret_key: str) -> str:
    return Fernet(_key(app_secret_key)).decrypt(token.encode()).decode()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_crypto.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/src/pragya_assistant/crypto.py backend/tests/test_crypto.py
git commit -m "feat(crypto): Fernet secret encryption keyed by APP_SECRET_KEY"
```

---

### Task 2: Plaid settings + dependency

**Files:**
- Modify: `backend/pyproject.toml` (add `plaid-python` dep + mypy override)
- Modify: `backend/src/pragya_assistant/config.py` (add fields)
- Modify: `.env.example` (document keys)
- Test: `backend/tests/test_config.py` (add a case; create if absent)

**Interfaces:**
- Produces: `Settings.plaid_client_id: str | None`, `Settings.plaid_secret: str | None`, `Settings.plaid_env: str = "sandbox"`, `Settings.finance_sync_hour: int = 6`, `Settings.finance_sync_minute: int = 30`.

- [ ] **Step 1: Add the dependency**

Run: `cd backend && uv add "plaid-python>=18"`
Then add to the `[[tool.mypy.overrides]]` `module` list in `backend/pyproject.toml`: `"plaid.*",`

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_config.py  (add this test; keep existing ones)
from pragya_assistant.config import Settings


def test_plaid_defaults_off() -> None:
    s = Settings(
        app_secret_key="x" * 16,
        api_auth_token="x" * 16,
        database_url="postgresql+asyncpg://u:p@localhost/db",
    )
    assert s.plaid_client_id is None
    assert s.plaid_env == "sandbox"
    assert s.finance_sync_hour == 6
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_config.py::test_plaid_defaults_off -q`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'plaid_env'`.

- [ ] **Step 4: Add the fields**

In `backend/src/pragya_assistant/config.py`, after the Web search block (near the email block), add:

```python
    # --- Finance (Plaid; read-only, feature off until configured) ---
    plaid_client_id: str | None = None
    plaid_secret: str | None = None
    plaid_env: str = "sandbox"  # sandbox | production
    finance_sync_hour: int = 6
    finance_sync_minute: int = 30
```

- [ ] **Step 5: Document in `.env.example`** (after the Email block)

```bash
# ---- Finance (Plaid; read-only, feature off until set) ----
# Personal-use Trial keys from dashboard.plaid.com. Treat the secret like a password.
PLAID_CLIENT_ID=
PLAID_SECRET=
PLAID_ENV=sandbox
```

- [ ] **Step 6: Run test + gates**

Run: `cd backend && uv run pytest tests/test_config.py -q && uv run mypy src`
Expected: PASS, mypy clean.

- [ ] **Step 7: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/src/pragya_assistant/config.py backend/tests/test_config.py .env.example
git commit -m "feat(finance): Plaid settings + plaid-python dependency"
```

---

### Task 3: Finance ORM models + migration 0004

**Files:**
- Modify: `backend/src/pragya_assistant/memory/models.py` (append 5 models)
- Create: `backend/migrations/versions/0004_finance.py`
- Test: `backend/tests/finance/test_models.py` (+ `backend/tests/finance/__init__.py`)

**Interfaces:**
- Produces ORM classes (all importable from `pragya_assistant.memory.models`):
  - `PlaidItem(id:int, institution_name:str, access_token:str, item_id:str, transactions_cursor:str|None, last_synced_at:datetime|None, created_at:datetime)`
  - `Account(id:int, item_id:int FK, plaid_account_id:str, name:str, official_name:str|None, type:str, subtype:str|None, mask:str|None, current_balance:Decimal|None, available_balance:Decimal|None, iso_currency:str|None, updated_at:datetime)`
  - `Transaction(id:int, account_id:int FK, plaid_txn_id:str, date:date, name:str, merchant_name:str|None, amount:Decimal, category:str|None, pending:bool)`
  - `Holding(id:int, account_id:int FK, security_name:str, ticker:str|None, quantity:Decimal, price:Decimal|None, value:Decimal|None, iso_currency:str|None)`
  - `Liability(id:int, account_id:int FK, kind:str, apr:Decimal|None, next_payment_due:date|None, next_payment_amount:Decimal|None, balance:Decimal|None)`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/finance/test_models.py
import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.memory.models import Account, PlaidItem, Transaction


async def test_item_account_transaction_persist(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as s:
        item = PlaidItem(institution_name="Chase", access_token="enc", item_id="it_1")
        s.add(item)
        await s.flush()
        acct = Account(
            item_id=item.id, plaid_account_id="ac_1", name="Checking", type="depository",
            current_balance=Decimal("100.50"),
        )
        s.add(acct)
        await s.flush()
        s.add(Transaction(
            account_id=acct.id, plaid_txn_id="tx_1", date=dt.date(2026, 6, 20),
            name="Coffee", amount=Decimal("4.25"), pending=False,
        ))
        await s.commit()

    async with session_factory() as s:
        txns = list((await s.execute(select(Transaction))).scalars().all())
        assert txns[0].name == "Coffee" and txns[0].amount == Decimal("4.25")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://pragya:pragya@localhost:5432/pragya_test uv run pytest tests/finance/test_models.py -q`
Expected: FAIL — `ImportError: cannot import name 'PlaidItem'`.

- [ ] **Step 3: Add the models** to `backend/src/pragya_assistant/memory/models.py`

Add `Numeric` to the sqlalchemy import line and `Decimal` import at top (`from decimal import Decimal`), then append:

```python
class PlaidItem(Base):
    __tablename__ = "plaid_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_name: Mapped[str] = mapped_column(String(200))
    access_token: Mapped[str] = mapped_column(Text)  # encrypted
    item_id: Mapped[str] = mapped_column(String(100))
    transactions_cursor: Mapped[str | None] = mapped_column(Text, default=None)
    last_synced_at: Mapped[dt.datetime | None] = mapped_column(default=None)
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("plaid_items.id", ondelete="CASCADE"), index=True)
    plaid_account_id: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(200))
    official_name: Mapped[str | None] = mapped_column(String(200), default=None)
    type: Mapped[str] = mapped_column(String(50))
    subtype: Mapped[str | None] = mapped_column(String(50), default=None)
    mask: Mapped[str | None] = mapped_column(String(20), default=None)
    current_balance: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)
    available_balance: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)
    iso_currency: Mapped[str | None] = mapped_column(String(3), default=None)
    updated_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    plaid_txn_id: Mapped[str] = mapped_column(String(100), index=True)
    date: Mapped[dt.date] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(Text)
    merchant_name: Mapped[str | None] = mapped_column(String(200), default=None)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    category: Mapped[str | None] = mapped_column(String(100), default=None)
    pending: Mapped[bool] = mapped_column(default=False)


class Holding(Base):
    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    security_name: Mapped[str] = mapped_column(String(200))
    ticker: Mapped[str | None] = mapped_column(String(20), default=None)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)
    value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)
    iso_currency: Mapped[str | None] = mapped_column(String(3), default=None)


class Liability(Base):
    __tablename__ = "liabilities"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # mortgage | credit | student
    apr: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), default=None)
    next_payment_due: Mapped[dt.date | None] = mapped_column(default=None)
    next_payment_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)
    balance: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)
```

- [ ] **Step 4: Create the migration** `backend/migrations/versions/0004_finance.py`

```python
"""finance tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-21

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plaid_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("institution_name", sa.String(length=200), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("item_id", sa.String(length=100), nullable=False),
        sa.Column("transactions_cursor", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("plaid_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plaid_account_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("official_name", sa.String(length=200), nullable=True),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("subtype", sa.String(length=50), nullable=True),
        sa.Column("mask", sa.String(length=20), nullable=True),
        sa.Column("current_balance", sa.Numeric(14, 2), nullable=True),
        sa.Column("available_balance", sa.Numeric(14, 2), nullable=True),
        sa.Column("iso_currency", sa.String(length=3), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_accounts_item_id", "accounts", ["item_id"])
    op.create_index("ix_accounts_plaid_account_id", "accounts", ["plaid_account_id"])
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plaid_txn_id", sa.String(length=100), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("merchant_name", sa.String(length=200), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("pending", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_transactions_account_id", "transactions", ["account_id"])
    op.create_index("ix_transactions_plaid_txn_id", "transactions", ["plaid_txn_id"])
    op.create_index("ix_transactions_date", "transactions", ["date"])
    op.create_table(
        "holdings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("security_name", sa.String(length=200), nullable=False),
        sa.Column("ticker", sa.String(length=20), nullable=True),
        sa.Column("quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("price", sa.Numeric(14, 2), nullable=True),
        sa.Column("value", sa.Numeric(14, 2), nullable=True),
        sa.Column("iso_currency", sa.String(length=3), nullable=True),
    )
    op.create_index("ix_holdings_account_id", "holdings", ["account_id"])
    op.create_table(
        "liabilities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("apr", sa.Numeric(6, 3), nullable=True),
        sa.Column("next_payment_due", sa.Date(), nullable=True),
        sa.Column("next_payment_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("balance", sa.Numeric(14, 2), nullable=True),
    )
    op.create_index("ix_liabilities_account_id", "liabilities", ["account_id"])


def downgrade() -> None:
    op.drop_table("liabilities")
    op.drop_table("holdings")
    op.drop_table("transactions")
    op.drop_table("accounts")
    op.drop_table("plaid_items")
```

- [ ] **Step 5: Run test to verify it passes** (the conftest creates tables from `Base.metadata`)

Run: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://pragya:pragya@localhost:5432/pragya_test uv run pytest tests/finance/test_models.py -q`
Expected: PASS.

- [ ] **Step 6: Verify the migration applies** against a scratch DB

Run: `cd backend && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: no errors (upgrade → downgrade → upgrade clean).

- [ ] **Step 7: Commit**

```bash
git add backend/src/pragya_assistant/memory/models.py backend/migrations/versions/0004_finance.py backend/tests/finance/
git commit -m "feat(finance): ORM models + migration 0004 (items/accounts/txns/holdings/liabilities)"
```

---

### Task 4: Plaid value types + client interface (fake-first)

**Files:**
- Create: `backend/src/pragya_assistant/finance/__init__.py`, `backend/src/pragya_assistant/finance/client.py`
- Test: `backend/tests/finance/test_fake_client.py`

**Interfaces:**
- Produces dataclasses + a `PlaidClient` Protocol so the service is testable without the SDK:
  - `LinkResult(access_token:str, item_id:str, institution_name:str)`
  - `RawAccount(plaid_account_id, name, official_name, type, subtype, mask, current_balance:Decimal|None, available_balance:Decimal|None, iso_currency)`
  - `RawTxn(plaid_txn_id, account_plaid_id, date:dt.date, name, merchant_name, amount:Decimal, category, pending)`
  - `RawHolding(account_plaid_id, security_name, ticker, quantity:Decimal, price, value, iso_currency)`
  - `RawLiability(account_plaid_id, kind, apr, next_payment_due, next_payment_amount, balance)`
  - `SyncPage(added:list[RawTxn], modified:list[RawTxn], removed:list[str], next_cursor:str, has_more:bool)`
  - `PlaidClient(Protocol)`: `create_link_token() -> str`; `exchange_public_token(public_token:str) -> LinkResult`; `get_accounts(access_token:str) -> list[RawAccount]`; `sync_transactions(access_token:str, cursor:str|None) -> SyncPage`; `get_holdings(access_token:str) -> list[RawHolding]`; `get_liabilities(access_token:str) -> list[RawLiability]`.

- [ ] **Step 1: Write the failing test** (defines the dataclasses' shape via a fake)

```python
# backend/tests/finance/test_fake_client.py
import datetime as dt
from decimal import Decimal

from pragya_assistant.finance.client import LinkResult, RawAccount, RawTxn, SyncPage


def test_value_types_construct() -> None:
    link = LinkResult(access_token="enc", item_id="it", institution_name="Chase")
    acct = RawAccount(
        plaid_account_id="ac", name="Checking", official_name=None, type="depository",
        subtype="checking", mask="1234", current_balance=Decimal("10"),
        available_balance=None, iso_currency="USD",
    )
    page = SyncPage(
        added=[RawTxn("tx", "ac", dt.date(2026, 6, 1), "Coffee", None, Decimal("4"), "Food", False)],
        modified=[], removed=[], next_cursor="c1", has_more=False,
    )
    assert link.institution_name == "Chase"
    assert acct.current_balance == Decimal("10")
    assert page.added[0].name == "Coffee"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/finance/test_fake_client.py -q`
Expected: FAIL — `ModuleNotFoundError: pragya_assistant.finance.client`.

- [ ] **Step 3: Write the value types + Protocol** in `backend/src/pragya_assistant/finance/client.py`

```python
"""Plaid value types + the read-only client interface (Protocol).

The concrete SDK adapter (PlaidApiClient) lives below; tests and the service
depend on the Protocol so they run without the SDK or network.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class LinkResult:
    access_token: str
    item_id: str
    institution_name: str


@dataclass(frozen=True)
class RawAccount:
    plaid_account_id: str
    name: str
    official_name: str | None
    type: str
    subtype: str | None
    mask: str | None
    current_balance: Decimal | None
    available_balance: Decimal | None
    iso_currency: str | None


@dataclass(frozen=True)
class RawTxn:
    plaid_txn_id: str
    account_plaid_id: str
    date: dt.date
    name: str
    merchant_name: str | None
    amount: Decimal
    category: str | None
    pending: bool


@dataclass(frozen=True)
class RawHolding:
    account_plaid_id: str
    security_name: str
    ticker: str | None
    quantity: Decimal
    price: Decimal | None
    value: Decimal | None
    iso_currency: str | None


@dataclass(frozen=True)
class RawLiability:
    account_plaid_id: str
    kind: str
    apr: Decimal | None
    next_payment_due: dt.date | None
    next_payment_amount: Decimal | None
    balance: Decimal | None


@dataclass(frozen=True)
class SyncPage:
    added: list[RawTxn]
    modified: list[RawTxn]
    removed: list[str]
    next_cursor: str
    has_more: bool


class PlaidClient(Protocol):
    def create_link_token(self) -> str: ...
    def exchange_public_token(self, public_token: str) -> LinkResult: ...
    def get_accounts(self, access_token: str) -> list[RawAccount]: ...
    def sync_transactions(self, access_token: str, cursor: str | None) -> SyncPage: ...
    def get_holdings(self, access_token: str) -> list[RawHolding]: ...
    def get_liabilities(self, access_token: str) -> list[RawLiability]: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/finance/test_fake_client.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/pragya_assistant/finance/__init__.py backend/src/pragya_assistant/finance/client.py backend/tests/finance/test_fake_client.py
git commit -m "feat(finance): Plaid value types + read-only client Protocol"
```

---

### Task 5: FinanceStore (upsert + queries)

**Files:**
- Create: `backend/src/pragya_assistant/finance/store.py`
- Test: `backend/tests/finance/test_store.py`

**Interfaces:**
- Consumes: ORM models (Task 3); `RawAccount/RawTxn/RawHolding/RawLiability` (Task 4).
- Produces `FinanceStore(session_factory)`:
  - `save_item(institution_name, encrypted_token, item_id) -> int` (returns item id)
  - `set_cursor(item_id:int, cursor:str) -> None`, `get_cursor(item_id:int) -> str | None`, `list_items() -> list[PlaidItem]`
  - `upsert_accounts(item_id:int, accounts:list[RawAccount]) -> None` (keyed by plaid_account_id)
  - `apply_txn_sync(item_id:int, added:list[RawTxn], modified:list[RawTxn], removed:list[str]) -> None`
  - `replace_holdings(item_id:int, holdings:list[RawHolding]) -> None`, `replace_liabilities(item_id:int, liabilities:list[RawLiability]) -> None`
  - queries: `account_balances() -> list[Account]`, `spending_by_category(start:dt.date, end:dt.date) -> dict[str, Decimal]`, `search_transactions(text:str|None, start:dt.date|None, end:dt.date|None, limit:int) -> list[Transaction]`, `all_holdings() -> list[Holding]`, `all_liabilities() -> list[Liability]`, `net_worth() -> Decimal`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/finance/test_store.py
import datetime as dt
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.finance.client import RawAccount, RawTxn
from pragya_assistant.finance.store import FinanceStore


def _acct(pid: str, name: str, bal: str, type_: str = "depository") -> RawAccount:
    return RawAccount(pid, name, None, type_, None, None, Decimal(bal), None, "USD")


def _txn(tid: str, acct: str, amount: str, cat: str, day: int) -> RawTxn:
    return RawTxn(tid, acct, dt.date(2026, 6, day), tid, None, Decimal(amount), cat, False)


async def test_upsert_accounts_and_balances(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = FinanceStore(session_factory)
    item_id = await store.save_item("Chase", "enc", "it_1")
    await store.upsert_accounts(item_id, [_acct("ac1", "Checking", "100.00")])
    await store.upsert_accounts(item_id, [_acct("ac1", "Checking", "150.00")])  # update, not dup
    balances = await store.account_balances()
    assert len(balances) == 1 and balances[0].current_balance == Decimal("150.00")


async def test_txn_sync_and_spending(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    store = FinanceStore(session_factory)
    item_id = await store.save_item("Chase", "enc", "it_1")
    await store.upsert_accounts(item_id, [_acct("ac1", "Checking", "100")])
    await store.apply_txn_sync(item_id, added=[
        _txn("t1", "ac1", "4.00", "Food", 1), _txn("t2", "ac1", "6.00", "Food", 2),
        _txn("t3", "ac1", "20.00", "Transport", 3),
    ], modified=[], removed=[])
    spend = await store.spending_by_category(dt.date(2026, 6, 1), dt.date(2026, 6, 30))
    assert spend["Food"] == Decimal("10.00") and spend["Transport"] == Decimal("20.00")
    await store.apply_txn_sync(item_id, added=[], modified=[], removed=["t1"])
    spend2 = await store.spending_by_category(dt.date(2026, 6, 1), dt.date(2026, 6, 30))
    assert spend2["Food"] == Decimal("6.00")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://pragya:pragya@localhost:5432/pragya_test uv run pytest tests/finance/test_store.py -q`
Expected: FAIL — `ModuleNotFoundError: pragya_assistant.finance.store`.

- [ ] **Step 3: Write the store** in `backend/src/pragya_assistant/finance/store.py`

```python
"""Async persistence + queries for finance data. No Plaid calls here."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.finance.client import RawAccount, RawHolding, RawLiability, RawTxn
from pragya_assistant.memory.models import Account, Holding, Liability, PlaidItem, Transaction


class FinanceStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save_item(self, institution_name: str, encrypted_token: str, item_id: str) -> int:
        async with self._session_factory() as s:
            item = PlaidItem(
                institution_name=institution_name, access_token=encrypted_token, item_id=item_id
            )
            s.add(item)
            await s.commit()
            await s.refresh(item)
            return item.id

    async def list_items(self) -> list[PlaidItem]:
        async with self._session_factory() as s:
            return list((await s.execute(select(PlaidItem))).scalars().all())

    async def get_cursor(self, item_id: int) -> str | None:
        async with self._session_factory() as s:
            return (await s.get(PlaidItem, item_id)).transactions_cursor  # type: ignore[union-attr]

    async def set_cursor(self, item_id: int, cursor: str) -> None:
        async with self._session_factory() as s:
            item = await s.get(PlaidItem, item_id)
            if item is not None:
                item.transactions_cursor = cursor
                item.last_synced_at = dt.datetime.now(dt.UTC).replace(tzinfo=None)
                await s.commit()

    async def _account_pk(self, s: AsyncSession, item_id: int, plaid_account_id: str) -> int | None:
        stmt = select(Account.id).where(
            Account.item_id == item_id, Account.plaid_account_id == plaid_account_id
        )
        return (await s.execute(stmt)).scalar_one_or_none()

    async def upsert_accounts(self, item_id: int, accounts: list[RawAccount]) -> None:
        async with self._session_factory() as s:
            for a in accounts:
                pk = await self._account_pk(s, item_id, a.plaid_account_id)
                if pk is None:
                    s.add(Account(
                        item_id=item_id, plaid_account_id=a.plaid_account_id, name=a.name,
                        official_name=a.official_name, type=a.type, subtype=a.subtype, mask=a.mask,
                        current_balance=a.current_balance, available_balance=a.available_balance,
                        iso_currency=a.iso_currency,
                    ))
                else:
                    acct = await s.get(Account, pk)
                    assert acct is not None
                    acct.current_balance = a.current_balance
                    acct.available_balance = a.available_balance
                    acct.name = a.name
            await s.commit()

    async def apply_txn_sync(
        self, item_id: int, added: list[RawTxn], modified: list[RawTxn], removed: list[str]
    ) -> None:
        async with self._session_factory() as s:
            for t in [*added, *modified]:
                acct_pk = await self._account_pk(s, item_id, t.account_plaid_id)
                if acct_pk is None:
                    continue
                existing = (await s.execute(
                    select(Transaction).where(Transaction.plaid_txn_id == t.plaid_txn_id)
                )).scalar_one_or_none()
                if existing is None:
                    s.add(Transaction(
                        account_id=acct_pk, plaid_txn_id=t.plaid_txn_id, date=t.date, name=t.name,
                        merchant_name=t.merchant_name, amount=t.amount, category=t.category,
                        pending=t.pending,
                    ))
                else:
                    existing.amount = t.amount
                    existing.category = t.category
                    existing.pending = t.pending
            if removed:
                await s.execute(delete(Transaction).where(Transaction.plaid_txn_id.in_(removed)))
            await s.commit()

    async def replace_holdings(self, item_id: int, holdings: list[RawHolding]) -> None:
        async with self._session_factory() as s:
            acct_ids = (await s.execute(
                select(Account.id).where(Account.item_id == item_id)
            )).scalars().all()
            if acct_ids:
                await s.execute(delete(Holding).where(Holding.account_id.in_(acct_ids)))
            for h in holdings:
                pk = await self._account_pk(s, item_id, h.account_plaid_id)
                if pk is not None:
                    s.add(Holding(
                        account_id=pk, security_name=h.security_name, ticker=h.ticker,
                        quantity=h.quantity, price=h.price, value=h.value, iso_currency=h.iso_currency,
                    ))
            await s.commit()

    async def replace_liabilities(self, item_id: int, liabilities: list[RawLiability]) -> None:
        async with self._session_factory() as s:
            acct_ids = (await s.execute(
                select(Account.id).where(Account.item_id == item_id)
            )).scalars().all()
            if acct_ids:
                await s.execute(delete(Liability).where(Liability.account_id.in_(acct_ids)))
            for liab in liabilities:
                pk = await self._account_pk(s, item_id, liab.account_plaid_id)
                if pk is not None:
                    s.add(Liability(
                        account_id=pk, kind=liab.kind, apr=liab.apr,
                        next_payment_due=liab.next_payment_due,
                        next_payment_amount=liab.next_payment_amount, balance=liab.balance,
                    ))
            await s.commit()

    async def account_balances(self) -> list[Account]:
        async with self._session_factory() as s:
            return list((await s.execute(select(Account).order_by(Account.name))).scalars().all())

    async def spending_by_category(self, start: dt.date, end: dt.date) -> dict[str, Decimal]:
        async with self._session_factory() as s:
            stmt = select(Transaction).where(
                Transaction.date >= start, Transaction.date <= end, Transaction.amount > 0
            )
            totals: dict[str, Decimal] = {}
            for t in (await s.execute(stmt)).scalars().all():
                key = t.category or "Uncategorized"
                totals[key] = totals.get(key, Decimal("0")) + t.amount
            return totals

    async def search_transactions(
        self, text: str | None, start: dt.date | None, end: dt.date | None, limit: int
    ) -> list[Transaction]:
        async with self._session_factory() as s:
            stmt = select(Transaction).order_by(Transaction.date.desc())
            if text:
                stmt = stmt.where(Transaction.name.ilike(f"%{text}%"))
            if start:
                stmt = stmt.where(Transaction.date >= start)
            if end:
                stmt = stmt.where(Transaction.date <= end)
            return list((await s.execute(stmt.limit(limit))).scalars().all())

    async def all_holdings(self) -> list[Holding]:
        async with self._session_factory() as s:
            return list((await s.execute(select(Holding))).scalars().all())

    async def all_liabilities(self) -> list[Liability]:
        async with self._session_factory() as s:
            return list((await s.execute(select(Liability))).scalars().all())

    async def net_worth(self) -> Decimal:
        async with self._session_factory() as s:
            assets = Decimal("0")
            for a in (await s.execute(select(Account))).scalars().all():
                if a.current_balance is None:
                    continue
                # liabilities (credit/loan/mortgage) are debts; depository/investment are assets
                if a.type in {"credit", "loan"}:
                    assets -= a.current_balance
                else:
                    assets += a.current_balance
            return assets
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://pragya:pragya@localhost:5432/pragya_test uv run pytest tests/finance/test_store.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/src/pragya_assistant/finance/store.py backend/tests/finance/test_store.py
git commit -m "feat(finance): FinanceStore upsert + spending/balance/net-worth queries"
```

---

### Task 6: FinanceService (link + sync orchestration)

**Files:**
- Create: `backend/src/pragya_assistant/finance/service.py`
- Test: `backend/tests/finance/test_service.py`

**Interfaces:**
- Consumes: `PlaidClient` Protocol (Task 4), `FinanceStore` (Task 5), `encrypt_secret`/`decrypt_secret` (Task 1).
- Produces `FinanceService(client, store, app_secret_key)`:
  - `async link(public_token:str) -> str` — exchange, encrypt+save item, pull accounts; returns institution name.
  - `async sync() -> int` — for every item: decrypt token, `sync_transactions` loop (cursor, `has_more`), refresh accounts/holdings/liabilities; returns count of items synced.
  - query passthroughs used by tools: `account_balances`, `spending_by_category`, `search_transactions`, `holdings`, `liabilities`, `net_worth` (delegate to store; sync wrappers run via `asyncio.to_thread` for the blocking SDK in `link`/`sync`).
- Produces `build_finance_service(settings, session_factory) -> FinanceService | None` (None when `plaid_client_id`/`plaid_secret` unset).

- [ ] **Step 1: Write the failing test** (fake client; verifies link + multi-page sync)

```python
# backend/tests/finance/test_service.py
import datetime as dt
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.finance.client import (
    LinkResult, RawAccount, RawTxn, SyncPage,
)
from pragya_assistant.finance.service import FinanceService
from pragya_assistant.finance.store import FinanceStore

KEY = "x" * 16


class FakePlaid:
    def __init__(self) -> None:
        self.exchanged: str | None = None
        self._cursors: list[str | None] = []

    def create_link_token(self) -> str:
        return "link-sandbox-tok"

    def exchange_public_token(self, public_token: str) -> LinkResult:
        self.exchanged = public_token
        return LinkResult(access_token="access-sandbox-1", item_id="it_1", institution_name="Chase")

    def get_accounts(self, access_token: str) -> list[RawAccount]:
        return [RawAccount("ac1", "Checking", None, "depository", "checking", "1", Decimal("500"), None, "USD")]

    def sync_transactions(self, access_token: str, cursor: str | None) -> SyncPage:
        self._cursors.append(cursor)
        if cursor is None:
            return SyncPage(
                added=[RawTxn("t1", "ac1", dt.date(2026, 6, 1), "Coffee", None, Decimal("4"), "Food", False)],
                modified=[], removed=[], next_cursor="c1", has_more=True,
            )
        return SyncPage(added=[], modified=[], removed=[], next_cursor="c2", has_more=False)

    def get_holdings(self, access_token: str) -> list:
        return []

    def get_liabilities(self, access_token: str) -> list:
        return []


async def test_link_then_sync(session_factory: async_sessionmaker[AsyncSession]) -> None:
    store = FinanceStore(session_factory)
    fake = FakePlaid()
    svc = FinanceService(fake, store, app_secret_key=KEY)

    name = await svc.link("public-sandbox-tok")
    assert name == "Chase" and fake.exchanged == "public-sandbox-tok"

    # token persisted ENCRYPTED, not in plaintext
    items = await store.list_items()
    assert items[0].access_token != "access-sandbox-1"

    synced = await svc.sync()
    assert synced == 1
    # paged until has_more=False (cursor None then "c1")
    assert fake._cursors == [None, "c1"]
    balances = await svc.account_balances()
    assert balances[0].current_balance == Decimal("500")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://pragya:pragya@localhost:5432/pragya_test uv run pytest tests/finance/test_service.py -q`
Expected: FAIL — `ModuleNotFoundError: pragya_assistant.finance.service`.

- [ ] **Step 3: Write the service** in `backend/src/pragya_assistant/finance/service.py`

```python
"""Async finance service: orchestrates Plaid client + store. Read-only + sync."""

from __future__ import annotations

import asyncio
import datetime as dt
from decimal import Decimal

from pragya_assistant.config import Settings
from pragya_assistant.crypto import decrypt_secret, encrypt_secret
from pragya_assistant.finance.client import PlaidClient
from pragya_assistant.finance.store import FinanceStore
from pragya_assistant.memory.models import Account, Holding, Liability, Transaction


class FinanceService:
    def __init__(self, client: PlaidClient, store: FinanceStore, *, app_secret_key: str) -> None:
        self._client = client
        self._store = store
        self._key = app_secret_key

    async def create_link_token(self) -> str:
        return await asyncio.to_thread(self._client.create_link_token)

    async def link(self, public_token: str) -> str:
        result = await asyncio.to_thread(self._client.exchange_public_token, public_token)
        item_id = await self._store.save_item(
            result.institution_name, encrypt_secret(result.access_token, self._key), result.item_id
        )
        accounts = await asyncio.to_thread(self._client.get_accounts, result.access_token)
        await self._store.upsert_accounts(item_id, accounts)
        return result.institution_name

    async def sync(self) -> int:
        items = await self._store.list_items()
        for item in items:
            token = decrypt_secret(item.access_token, self._key)
            accounts = await asyncio.to_thread(self._client.get_accounts, token)
            await self._store.upsert_accounts(item.id, accounts)

            cursor = item.transactions_cursor
            while True:
                page = await asyncio.to_thread(self._client.sync_transactions, token, cursor)
                await self._store.apply_txn_sync(item.id, page.added, page.modified, page.removed)
                cursor = page.next_cursor
                if not page.has_more:
                    break
            await self._store.set_cursor(item.id, cursor)

            await self._store.replace_holdings(
                item.id, await asyncio.to_thread(self._client.get_holdings, token)
            )
            await self._store.replace_liabilities(
                item.id, await asyncio.to_thread(self._client.get_liabilities, token)
            )
        return len(items)

    # --- query passthroughs (used by tools + digest) ---
    async def account_balances(self) -> list[Account]:
        return await self._store.account_balances()

    async def spending_by_category(self, start: dt.date, end: dt.date) -> dict[str, Decimal]:
        return await self._store.spending_by_category(start, end)

    async def search_transactions(
        self, text: str | None, start: dt.date | None, end: dt.date | None, limit: int = 25
    ) -> list[Transaction]:
        return await self._store.search_transactions(text, start, end, limit)

    async def holdings(self) -> list[Holding]:
        return await self._store.all_holdings()

    async def liabilities(self) -> list[Liability]:
        return await self._store.all_liabilities()

    async def net_worth(self) -> Decimal:
        return await self._store.net_worth()


def build_finance_service(
    settings: Settings, session_factory: object
) -> FinanceService | None:
    if not (settings.plaid_client_id and settings.plaid_secret):
        return None
    from pragya_assistant.finance.plaid_api import PlaidApiClient  # Task 11 (lazy import)

    client = PlaidApiClient(
        client_id=settings.plaid_client_id, secret=settings.plaid_secret, env=settings.plaid_env
    )
    return FinanceService(client, FinanceStore(session_factory), app_secret_key=settings.app_secret_key)  # type: ignore[arg-type]
```

Note: `build_finance_service` imports `PlaidApiClient` lazily so this task's tests (fake client) don't need the SDK; the real adapter is Task 11.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://pragya:pragya@localhost:5432/pragya_test uv run pytest tests/finance/test_service.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/pragya_assistant/finance/service.py backend/tests/finance/test_service.py
git commit -m "feat(finance): FinanceService link + cursor sync (token encrypted at rest)"
```

---

### Task 7: Finance tools (chat)

**Files:**
- Create: `backend/src/pragya_assistant/finance/tools.py`
- Test: `backend/tests/finance/test_tools.py`

**Interfaces:**
- Consumes: `FinanceService` (Task 6), `Tool` from `pragya_assistant.agent.tools`.
- Produces `build_finance_tools(service) -> list[Tool]`: `account_balances`, `spending_summary`, `search_transactions`, `net_worth`, `holdings`, `upcoming_bills`. Each handler is `async (dict) -> str`. **No sync/transfer tool.**

- [ ] **Step 1: Write the failing test** (fake service via the store fake from Task 5/6 reused)

```python
# backend/tests/finance/test_tools.py
import datetime as dt
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pragya_assistant.agent.tools import ToolHandler
from pragya_assistant.finance.client import RawAccount, RawTxn
from pragya_assistant.finance.service import FinanceService
from pragya_assistant.finance.store import FinanceStore


class _NoClient:  # tools never call the client; sync isn't exercised here
    def create_link_token(self) -> str: ...
    def exchange_public_token(self, public_token: str): ...
    def get_accounts(self, access_token: str): return []
    def sync_transactions(self, access_token: str, cursor): ...
    def get_holdings(self, access_token: str): return []
    def get_liabilities(self, access_token: str): return []


def _handler(tools: list, name: str) -> ToolHandler:
    return next(t for t in tools if t.name == name).handler


async def _seeded(session_factory: async_sessionmaker[AsyncSession]) -> FinanceService:
    store = FinanceStore(session_factory)
    item_id = await store.save_item("Chase", "enc", "it_1")
    await store.upsert_accounts(item_id, [
        RawAccount("ac1", "Checking", None, "depository", "checking", "1", Decimal("500"), None, "USD"),
    ])
    await store.apply_txn_sync(item_id, added=[
        RawTxn("t1", "ac1", dt.date(2026, 6, 1), "Cafe", None, Decimal("4"), "Food", False),
    ], modified=[], removed=[])
    return FinanceService(_NoClient(), store, app_secret_key="x" * 16)


async def test_balances_and_net_worth(session_factory: async_sessionmaker[AsyncSession]) -> None:
    from pragya_assistant.finance.tools import build_finance_tools
    tools = build_finance_tools(await _seeded(session_factory))
    bal = await _handler(tools, "account_balances")({})
    assert "Checking" in bal and "500" in bal
    nw = await _handler(tools, "net_worth")({})
    assert "500" in nw


async def test_spending_summary(session_factory: async_sessionmaker[AsyncSession]) -> None:
    from pragya_assistant.finance.tools import build_finance_tools
    tools = build_finance_tools(await _seeded(session_factory))
    out = await _handler(tools, "spending_summary")({"start": "2026-06-01", "end": "2026-06-30"})
    assert "Food" in out and "4" in out


def test_no_transfer_or_sync_tool(session_factory: async_sessionmaker[AsyncSession]) -> None:
    from pragya_assistant.finance.tools import build_finance_tools
    # build with a throwaway service object is fine; only names are inspected
    import asyncio
    svc = asyncio.get_event_loop().run_until_complete(_seeded(session_factory))
    names = {t.name for t in build_finance_tools(svc)}
    assert names == {
        "account_balances", "spending_summary", "search_transactions",
        "net_worth", "holdings", "upcoming_bills",
    }
    assert not any(("transfer" in n) or ("pay" in n) or ("sync" in n) for n in names)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://pragya:pragya@localhost:5432/pragya_test uv run pytest tests/finance/test_tools.py -q`
Expected: FAIL — `ModuleNotFoundError: pragya_assistant.finance.tools`.

- [ ] **Step 3: Write the tools** in `backend/src/pragya_assistant/finance/tools.py`

```python
"""Finance tools — model-facing, read-only. No transfer/sync tool exists."""

from __future__ import annotations

import datetime as dt
from typing import Any

from pragya_assistant.agent.tools import Tool
from pragya_assistant.finance.service import FinanceService


def build_finance_tools(service: FinanceService) -> list[Tool]:
    async def account_balances(args: dict[str, Any]) -> str:
        accounts = await service.account_balances()
        if not accounts:
            return "No connected accounts."
        return "\n".join(
            f"- {a.name} ({a.subtype or a.type}): {a.current_balance} {a.iso_currency or ''}".strip()
            for a in accounts
        )

    async def spending_summary(args: dict[str, Any]) -> str:
        start = dt.date.fromisoformat(str(args["start"]))
        end = dt.date.fromisoformat(str(args["end"]))
        totals = await service.spending_by_category(start, end)
        if not totals:
            return "No spending in that range."
        lines = [f"- {cat}: {amt}" for cat, amt in sorted(totals.items(), key=lambda kv: -kv[1])]
        return f"Spending {start}–{end}:\n" + "\n".join(lines)

    async def search_transactions(args: dict[str, Any]) -> str:
        start = dt.date.fromisoformat(str(args["start"])) if args.get("start") else None
        end = dt.date.fromisoformat(str(args["end"])) if args.get("end") else None
        txns = await service.search_transactions(
            args.get("text"), start, end, int(args.get("limit", 25))
        )
        if not txns:
            return "No matching transactions."
        return "\n".join(f"- {t.date} {t.name}: {t.amount} ({t.category or '—'})" for t in txns)

    async def net_worth(args: dict[str, Any]) -> str:
        return f"Estimated net worth (cash + investments − debts): {await service.net_worth()}"

    async def holdings(args: dict[str, Any]) -> str:
        rows = await service.holdings()
        if not rows:
            return "No investment holdings."
        return "\n".join(
            f"- {h.ticker or h.security_name}: {h.quantity} @ {h.price} = {h.value}" for h in rows
        )

    async def upcoming_bills(args: dict[str, Any]) -> str:
        rows = await service.liabilities()
        due = [liab for liab in rows if liab.next_payment_due is not None]
        if not due:
            return "No upcoming bills on record."
        due.sort(key=lambda x: x.next_payment_due)  # type: ignore[arg-type,return-value]
        return "\n".join(
            f"- {liab.kind}: {liab.next_payment_amount} due {liab.next_payment_due}"
            f" (APR {liab.apr}%)" for liab in due
        )

    return [
        Tool(name="account_balances", description="Show balances across all connected accounts.",
             input_schema=_object({}, []), handler=account_balances),
        Tool(name="spending_summary",
             description="Total spending by category for a date range.",
             input_schema=_object(
                 {"start": _string("Start date YYYY-MM-DD"), "end": _string("End date YYYY-MM-DD")},
                 ["start", "end"]),
             handler=spending_summary),
        Tool(name="search_transactions",
             description="Search transactions by text and/or date range.",
             input_schema=_object(
                 {"text": _string("Merchant/description substring"),
                  "start": _string("Start date YYYY-MM-DD"), "end": _string("End date YYYY-MM-DD"),
                  "limit": _integer("Max results (default 25)")}, []),
             handler=search_transactions),
        Tool(name="net_worth", description="Estimate net worth (assets − debts).",
             input_schema=_object({}, []), handler=net_worth),
        Tool(name="holdings", description="List investment holdings/positions.",
             input_schema=_object({}, []), handler=holdings),
        Tool(name="upcoming_bills",
             description="List upcoming liability/loan/mortgage payments and due dates.",
             input_schema=_object({}, []), handler=upcoming_bills),
    ]


def _object(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required,
            "additionalProperties": False}


def _string(description: str) -> dict[str, str]:
    return {"type": "string", "description": description}


def _integer(description: str) -> dict[str, str]:
    return {"type": "integer", "description": description}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://pragya:pragya@localhost:5432/pragya_test uv run pytest tests/finance/test_tools.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/pragya_assistant/finance/tools.py backend/tests/finance/test_tools.py
git commit -m "feat(finance): read-only chat tools (balances/spending/search/net-worth/holdings/bills)"
```

---

### Task 8: Wire finance tools into every engine

**Files:**
- Modify: `backend/src/pragya_assistant/agent/toolset.py` (add `finance_service` param)
- Modify: `backend/src/pragya_assistant/agent/factory.py` (`build_engine` param + pass-through; Codex `_codex_mcp_env` forwards `PLAID_*`)
- Modify: `backend/src/pragya_assistant/mcp_memory.py` (build + pass finance service)
- Test: `backend/tests/agent/test_toolset.py` (extend)

**Interfaces:**
- Consumes: `build_finance_tools` (Task 7), `FinanceService` (Task 6).
- Produces: `build_agent_tools(memory, task_store=None, calendar_service=None, email_service=None, finance_service=None)`.

- [ ] **Step 1: Write the failing test** (extend `test_includes_all_tool_families`)

Add to `backend/tests/agent/test_toolset.py` a finance fake + assertion:

```python
class _FakeFinance:
    async def account_balances(self): return []
    async def spending_by_category(self, start, end): return {}
    async def search_transactions(self, text, start, end, limit=25): return []
    async def holdings(self): return []
    async def liabilities(self): return []
    async def net_worth(self): return 0


async def test_includes_finance_tools(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tools = build_agent_tools(_memory(session_factory), finance_service=_FakeFinance())
    names = {t.name for t in tools}
    assert {"account_balances", "net_worth", "upcoming_bills"} <= names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://pragya:pragya@localhost:5432/pragya_test uv run pytest tests/agent/test_toolset.py::test_includes_finance_tools -q`
Expected: FAIL — `build_agent_tools() got an unexpected keyword argument 'finance_service'`.

- [ ] **Step 3: Implement** — in `toolset.py` add the import + param:

```python
from pragya_assistant.finance.service import FinanceService
from pragya_assistant.finance.tools import build_finance_tools
```
Add parameter `finance_service: FinanceService | None = None` to `build_agent_tools`, and before `return tools`:
```python
    if finance_service is not None:
        tools += build_finance_tools(finance_service)
```

In `factory.py`: add `finance_service: FinanceService | None = None` to `build_engine`, pass it into `build_agent_tools(...)`, import `FinanceService`, and in `_codex_mcp_env` add:
```python
    if settings.plaid_client_id and settings.plaid_secret:
        env["PLAID_CLIENT_ID"] = settings.plaid_client_id
        env["PLAID_SECRET"] = settings.plaid_secret
        env["PLAID_ENV"] = settings.plaid_env
```

In `mcp_memory.py`: build the service and pass it:
```python
from pragya_assistant.finance.service import build_finance_service
# ...
finance_service = build_finance_service(settings, session_factory)
server = create_memory_server(
    build_agent_tools(memory, task_store, calendar_service, email_service, finance_service)
)
```

- [ ] **Step 4: Run the test + full suite to verify it passes**

Run: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://pragya:pragya@localhost:5432/pragya_test uv run pytest tests/agent/test_toolset.py -q && uv run mypy src`
Expected: PASS, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add backend/src/pragya_assistant/agent/toolset.py backend/src/pragya_assistant/agent/factory.py backend/src/pragya_assistant/mcp_memory.py backend/tests/agent/test_toolset.py
git commit -m "feat(finance): wire finance tools into build_agent_tools + all engines"
```

---

### Task 9: API routes (Link flow + sync) + deps wiring

**Files:**
- Create: `backend/src/pragya_assistant/api/routes/finance.py`
- Modify: `backend/src/pragya_assistant/api/app.py` (mount router)
- Modify: `backend/src/pragya_assistant/api/deps.py` (build `finance` + getter)
- Modify: `backend/src/pragya_assistant/api/schemas.py` (response/request models)
- Test: `backend/tests/api/test_finance_api.py`

**Interfaces:**
- Consumes: `FinanceService` (Task 6), `require_token` auth, `get_components`.
- Produces routes (all `Depends(require_token)`):
  - `POST /finance/link/token` → `{"link_token": str}`
  - `POST /finance/link/exchange` body `{"public_token": str}` → `{"institution": str}`
  - `POST /finance/sync` → `{"items_synced": int}`
  - `GET /finance/accounts` → `list[AccountOut]`
- `deps.AppComponents.finance: FinanceService | None`; `get_finance(request) -> FinanceService` (503 if unconfigured).

- [ ] **Step 1: Write the failing test** (uses `build_test_app` with an injected fake finance service — see note)

```python
# backend/tests/api/test_finance_api.py
import httpx
from httpx import ASGITransport

AUTH = {"Authorization": "Bearer token"}


async def test_finance_requires_token(build_test_app) -> None:  # type: ignore[no-untyped-def]
    app = build_test_app_with_finance := build_test_app  # see conftest extension in Step 3
    app = build_test_app()
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/finance/sync")
    assert resp.status_code in (401, 503)
```

Note: the existing `build_test_app` fixture builds components without Plaid configured, so `/finance/*` returns 503 when unconfigured and 401 without a token. A fuller integration test against Sandbox is Task 12.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://pragya:pragya@localhost:5432/pragya_test uv run pytest tests/api/test_finance_api.py -q`
Expected: FAIL — 404 (route not mounted yet).

- [ ] **Step 3: Add schemas** to `backend/src/pragya_assistant/api/schemas.py`

```python
class ExchangeIn(BaseModel):
    public_token: str


class AccountOut(BaseModel):
    name: str
    type: str
    subtype: str | None
    current_balance: Decimal | None
    iso_currency: str | None
```
(Add `from decimal import Decimal` if not present.)

- [ ] **Step 4: Add deps wiring** in `backend/src/pragya_assistant/api/deps.py`

Import `from pragya_assistant.finance.service import build_finance_service`; add `finance: FinanceService | None = None` to `AppComponents`; in `build_components` add `finance = build_finance_service(settings, session_factory)` and include `finance=finance` in the return; add:
```python
def get_finance(request: Request) -> FinanceService:
    finance = get_components(request).finance
    if finance is None:
        raise HTTPException(status_code=503, detail="Finance not configured")
    return finance
```
(import `HTTPException` from fastapi if not already.)

- [ ] **Step 5: Write the router** `backend/src/pragya_assistant/api/routes/finance.py`

```python
"""Finance endpoints — Plaid Link flow + manual sync + accounts (read-only)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from pragya_assistant.api.auth import require_token
from pragya_assistant.api.deps import get_finance
from pragya_assistant.api.schemas import AccountOut, ExchangeIn
from pragya_assistant.finance.service import FinanceService

router = APIRouter(tags=["finance"], dependencies=[Depends(require_token)])


@router.post("/finance/link/token")
async def link_token(finance: Annotated[FinanceService, Depends(get_finance)]) -> dict[str, str]:
    return {"link_token": await finance.create_link_token()}


@router.post("/finance/link/exchange")
async def link_exchange(
    body: ExchangeIn, finance: Annotated[FinanceService, Depends(get_finance)]
) -> dict[str, str]:
    return {"institution": await finance.link(body.public_token)}


@router.post("/finance/sync")
async def sync(finance: Annotated[FinanceService, Depends(get_finance)]) -> dict[str, int]:
    return {"items_synced": await finance.sync()}


@router.get("/finance/accounts", response_model=list[AccountOut])
async def accounts(finance: Annotated[FinanceService, Depends(get_finance)]) -> list[AccountOut]:
    return [
        AccountOut(
            name=a.name, type=a.type, subtype=a.subtype,
            current_balance=a.current_balance, iso_currency=a.iso_currency,
        )
        for a in await finance.account_balances()
    ]
```

Mount in `backend/src/pragya_assistant/api/app.py` (add import `finance` to the routes import + `app.include_router(finance.router)`).

- [ ] **Step 6: Run test + gates**

Run: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://pragya:pragya@localhost:5432/pragya_test uv run pytest tests/api/test_finance_api.py -q && uv run mypy src`
Expected: PASS, mypy clean.

- [ ] **Step 7: Commit**

```bash
git add backend/src/pragya_assistant/api backend/tests/api/test_finance_api.py
git commit -m "feat(finance): Link/exchange/sync/accounts API routes + deps wiring"
```

---

### Task 10: Digest integration (daily line + weekly finance digest)

**Files:**
- Modify: `backend/src/pragya_assistant/agent/prompts.py` (daily digest mentions finance; add `build_weekly_finance_prompt`)
- Modify: `backend/src/pragya_assistant/digests/service.py` (add `run_weekly_finance()` if a separate stored digest is wanted) OR reuse `run()` with a prompt selector
- Test: `backend/tests/digests/test_prompts.py` (add assertions)

**Interfaces:**
- Produces: `build_weekly_finance_prompt(today: str) -> str`; daily digest prompt updated to include a finance line.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/digests/test_prompts.py  (add)
from pragya_assistant.agent.prompts import build_digest_prompt, build_weekly_finance_prompt


def test_daily_digest_mentions_finance() -> None:
    p = build_digest_prompt("2026-06-21")
    assert "balance" in p.lower() or "bills" in p.lower()


def test_weekly_finance_prompt() -> None:
    p = build_weekly_finance_prompt("2026-06-21")
    assert "spending" in p.lower() and "2026-06-21" in p
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/digests/test_prompts.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_weekly_finance_prompt'`.

- [ ] **Step 3: Implement** in `backend/src/pragya_assistant/agent/prompts.py`

Append to `build_digest_prompt`'s list of sections a finance clause (add before "Keep it brief"): `"; a one-line finance check — notable account balances and any bills due in the next few days"`. Then add:

```python
def build_weekly_finance_prompt(today: str) -> str:
    """Prompt for the weekly finance digest."""
    return (
        f"Compose my weekly finance summary for the week ending {today}. Using your finance "
        "tools, cover: total spending by category this week (top few), current balances across "
        "accounts, net worth, and any bills due in the next 7 days. Be concise and friendly; "
        "omit any section with no data."
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/digests/test_prompts.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/pragya_assistant/agent/prompts.py backend/tests/digests/test_prompts.py
git commit -m "feat(finance): finance line in daily digest + weekly finance prompt"
```

---

### Task 11: Real Plaid SDK adapter (`PlaidApiClient`)

**Files:**
- Create: `backend/src/pragya_assistant/finance/plaid_api.py`
- Test: `backend/tests/finance/test_plaid_api_sandbox.py` (marked `@pytest.mark.integration`, skipped without creds)

**Interfaces:**
- Produces `PlaidApiClient(client_id, secret, env)` implementing the `PlaidClient` Protocol, wrapping `plaid-python`.

> **Docs to check:** `plaid-python` README + API reference (https://github.com/plaid/plaid-python). The request/response model classes (`LinkTokenCreateRequest`, `ItemPublicTokenExchangeRequest`, `AccountsBalanceGetRequest`, `TransactionsSyncRequest`, `InvestmentsHoldingsGetRequest`, `LiabilitiesGetRequest`) and field names must be verified against the installed SDK version — the Sandbox test in Step 4 validates them.

- [ ] **Step 1: Write the integration test** (skipped unless `PLAID_CLIENT_ID`/`PLAID_SECRET` set)

```python
# backend/tests/finance/test_plaid_api_sandbox.py
import os

import pytest

from pragya_assistant.finance.plaid_api import PlaidApiClient

pytestmark = pytest.mark.skipif(
    not (os.getenv("PLAID_CLIENT_ID") and os.getenv("PLAID_SECRET")),
    reason="Plaid Sandbox creds not set",
)


def test_sandbox_link_exchange_sync() -> None:
    client = PlaidApiClient(
        client_id=os.environ["PLAID_CLIENT_ID"],
        secret=os.environ["PLAID_SECRET"],
        env="sandbox",
    )
    public_token = client.sandbox_public_token()  # helper below, Sandbox only
    link = client.exchange_public_token(public_token)
    assert link.access_token.startswith("access-sandbox")
    accounts = client.get_accounts(link.access_token)
    assert accounts and accounts[0].current_balance is not None
    page = client.sync_transactions(link.access_token, None)
    assert page.next_cursor
```

- [ ] **Step 2: Run test to verify it fails** (or skips without creds)

Run: `cd backend && uv run pytest tests/finance/test_plaid_api_sandbox.py -q`
Expected: FAIL (ImportError) — or SKIP if creds unset. Implement until, with Sandbox creds exported, it PASSES.

- [ ] **Step 3: Write the adapter** in `backend/src/pragya_assistant/finance/plaid_api.py`

```python
"""Concrete Plaid SDK adapter. Read-only products only (no transfer endpoints).

Verify exact request/response model imports against the installed plaid-python;
the Sandbox integration test exercises every method.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import plaid
from plaid.api import plaid_api
from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.liabilities_get_request import LiabilitiesGetRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.investments_holdings_get_request import InvestmentsHoldingsGetRequest
from plaid.model.products import Products
from plaid.model.transactions_sync_request import TransactionsSyncRequest

from pragya_assistant.finance.client import (
    LinkResult, RawAccount, RawHolding, RawLiability, RawTxn, SyncPage,
)

_HOSTS = {
    "sandbox": plaid.Environment.Sandbox,
    "production": plaid.Environment.Production,
}


def _dec(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


class PlaidApiClient:
    def __init__(self, *, client_id: str, secret: str, env: str) -> None:
        configuration = plaid.Configuration(
            host=_HOSTS[env], api_key={"clientId": client_id, "secret": secret}
        )
        self._api = plaid_api.PlaidApi(plaid.ApiClient(configuration))

    def create_link_token(self) -> str:
        req = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(client_user_id="pragya-user"),
            client_name="Pragya",
            products=[Products("transactions")],
            country_codes=[CountryCode("US")],
            language="en",
        )
        return self._api.link_token_create(req).link_token

    def exchange_public_token(self, public_token: str) -> LinkResult:
        resp = self._api.item_public_token_exchange(
            ItemPublicTokenExchangeRequest(public_token=public_token)
        )
        return LinkResult(
            access_token=resp.access_token, item_id=resp.item_id, institution_name="Connected bank"
        )

    def get_accounts(self, access_token: str) -> list[RawAccount]:
        resp = self._api.accounts_balance_get(AccountsBalanceGetRequest(access_token=access_token))
        out = []
        for a in resp.accounts:
            out.append(RawAccount(
                plaid_account_id=a.account_id, name=a.name, official_name=a.official_name,
                type=str(a.type), subtype=(None if a.subtype is None else str(a.subtype)),
                mask=a.mask, current_balance=_dec(a.balances.current),
                available_balance=_dec(a.balances.available),
                iso_currency=a.balances.iso_currency_code,
            ))
        return out

    def sync_transactions(self, access_token: str, cursor: str | None) -> SyncPage:
        req = TransactionsSyncRequest(access_token=access_token)
        if cursor:
            req.cursor = cursor
        resp = self._api.transactions_sync(req)

        def conv(t: object) -> RawTxn:
            return RawTxn(
                plaid_txn_id=t.transaction_id, account_plaid_id=t.account_id,  # type: ignore[attr-defined]
                date=t.date if isinstance(t.date, dt.date) else dt.date.fromisoformat(str(t.date)),  # type: ignore[attr-defined]
                name=t.name, merchant_name=t.merchant_name,  # type: ignore[attr-defined]
                amount=Decimal(str(t.amount)),  # type: ignore[attr-defined]
                category=(t.personal_finance_category.primary  # type: ignore[attr-defined]
                          if t.personal_finance_category else None),
                pending=bool(t.pending),  # type: ignore[attr-defined]
            )

        return SyncPage(
            added=[conv(t) for t in resp.added], modified=[conv(t) for t in resp.modified],
            removed=[r.transaction_id for r in resp.removed],
            next_cursor=resp.next_cursor, has_more=resp.has_more,
        )

    def get_holdings(self, access_token: str) -> list[RawHolding]:
        try:
            resp = self._api.investments_holdings_get(
                InvestmentsHoldingsGetRequest(access_token=access_token)
            )
        except plaid.ApiException:
            return []  # product not available for this item
        secs = {s.security_id: s for s in resp.securities}
        out = []
        for h in resp.holdings:
            sec = secs.get(h.security_id)
            out.append(RawHolding(
                account_plaid_id=h.account_id,
                security_name=(sec.name if sec and sec.name else (sec.ticker_symbol if sec else "")) or "",
                ticker=(sec.ticker_symbol if sec else None),
                quantity=Decimal(str(h.quantity)), price=_dec(h.institution_price),
                value=_dec(h.institution_value), iso_currency=h.iso_currency_code,
            ))
        return out

    def get_liabilities(self, access_token: str) -> list[RawLiability]:
        try:
            resp = self._api.liabilities_get(LiabilitiesGetRequest(access_token=access_token))
        except plaid.ApiException:
            return []
        out: list[RawLiability] = []
        liabilities = resp.liabilities
        for m in (liabilities.mortgage or []):
            out.append(RawLiability(
                account_plaid_id=m.account_id, kind="mortgage",
                apr=_dec(getattr(m.interest_rate, "percentage", None)),
                next_payment_due=_date(m.next_payment_due_date),
                next_payment_amount=_dec(m.next_monthly_payment), balance=None,
            ))
        for c in (liabilities.credit or []):
            out.append(RawLiability(
                account_plaid_id=c.account_id, kind="credit", apr=None,
                next_payment_due=_date(c.next_payment_due_date),
                next_payment_amount=_dec(c.minimum_payment_amount), balance=None,
            ))
        return out

    def sandbox_public_token(self) -> str:
        """Sandbox-only: mint a public_token without the Link UI (for tests)."""
        from plaid.model.sandbox_public_token_create_request import (
            SandboxPublicTokenCreateRequest,
        )
        req = SandboxPublicTokenCreateRequest(
            institution_id="ins_109508", initial_products=[Products("transactions")]
        )
        return self._api.sandbox_public_token_create(req).public_token


def _date(value: object) -> dt.date | None:
    if value is None:
        return None
    return value if isinstance(value, dt.date) else dt.date.fromisoformat(str(value))
```

- [ ] **Step 4: Run the Sandbox integration test** (export Sandbox creds first)

Run: `cd backend && PLAID_CLIENT_ID=... PLAID_SECRET=... uv run pytest tests/finance/test_plaid_api_sandbox.py -q`
Expected: PASS. Fix model imports/fields against the installed `plaid-python` until green.

- [ ] **Step 5: Add a safety test** `backend/tests/finance/test_safety.py`

```python
import pathlib


def test_no_transfer_endpoints() -> None:
    pkg = pathlib.Path(__file__).resolve().parents[2] / "src/pragya_assistant/finance"
    src = "\n".join(p.read_text() for p in pkg.glob("*.py"))
    for forbidden in ("transfer_create", "transfer_authorization", "/transfer", "payment_initiation"):
        assert forbidden not in src, f"finance must never reference {forbidden!r}"
```

- [ ] **Step 6: Run gates + commit**

Run: `cd backend && uv run ruff check . && uv run mypy src && uv run pytest -q`
```bash
git add backend/src/pragya_assistant/finance/plaid_api.py backend/tests/finance/test_plaid_api_sandbox.py backend/tests/finance/test_safety.py backend/pyproject.toml
git commit -m "feat(finance): Plaid SDK adapter (read-only) + Sandbox integration + safety test"
```

---

### Task 12: Scheduler sync job + Makefile + .env

**Files:**
- Modify: `backend/src/pragya_assistant/scheduling/scheduler.py` (add finance job)
- Modify: `backend/src/pragya_assistant/api/app.py` lifespan (pass finance to `build_scheduler`)
- Modify: `Makefile` (a `finance-sync` target hitting `POST /finance/sync`)
- Test: `backend/tests/scheduling/test_scheduler.py` (extend)

**Interfaces:**
- Consumes: `FinanceService` (Task 6). Produces: `build_scheduler(settings, digests, finance=None)` registering a `finance_sync` cron job when `finance` is provided.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/scheduling/test_scheduler.py  (add)
from pragya_assistant.scheduling.scheduler import build_scheduler


def test_finance_job_registered(settings_factory) -> None:  # type: ignore[no-untyped-def]
    settings = settings_factory(digest_enabled=True)

    class _F:
        async def sync(self) -> int: return 0

    sched = build_scheduler(settings, _digests(), finance=_F())  # _digests helper as in existing tests
    assert sched is not None and sched.get_job("finance_sync") is not None
```
(Use the existing test's pattern for constructing settings + a digests stub; mirror `test_scheduler.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/scheduling/test_scheduler.py::test_finance_job_registered -q`
Expected: FAIL — `build_scheduler() got an unexpected keyword argument 'finance'`.

- [ ] **Step 3: Implement** — extend `build_scheduler` signature with `finance: FinanceService | None = None` and, after the digest job (inside the `if not settings.digest_enabled` guard rework so a scheduler is created when EITHER digests or finance is enabled), add:

```python
    if finance is not None:
        scheduler.add_job(
            finance.sync,
            CronTrigger(
                hour=settings.finance_sync_hour, minute=settings.finance_sync_minute,
                timezone=settings.digest_timezone,
            ),
            id="finance_sync", replace_existing=True,
        )
```
Update the app lifespan (where `build_scheduler` is called) to pass `finance=components.finance`. Add a Makefile target:
```makefile
finance-sync:  ## Trigger a Plaid sync now
	@curl -fsS -X POST localhost:$(APP_PORT)/finance/sync -H "Authorization: Bearer $(API_AUTH_TOKEN)" && echo
```

- [ ] **Step 4: Run test + gates to verify pass**

Run: `cd backend && uv run pytest tests/scheduling/ -q && uv run mypy src`
Expected: PASS, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add backend/src/pragya_assistant/scheduling/scheduler.py backend/src/pragya_assistant/api/app.py Makefile backend/tests/scheduling/test_scheduler.py
git commit -m "feat(finance): daily Plaid sync job + make finance-sync"
```

---

### Task 13: Frontend — Connect a bank

**Files:**
- Modify: `frontend/package.json` (add `react-plaid-link`)
- Create: `frontend/app/Finance.tsx`
- Modify: `frontend/lib/api.ts` (link/exchange/accounts calls)
- Modify: `frontend/app/Workspace.tsx` (a "Finance" tab/section rendering `Finance`)
- Test: `frontend/` — a vitest for the api client function (mirror existing `lib/api` tests)

**Interfaces:**
- Consumes: `POST /finance/link/token`, `POST /finance/link/exchange`, `GET /finance/accounts`.
- Produces: `createLinkToken(token)`, `exchangePublicToken(publicToken, token)`, `listAccounts(token)` in `lib/api.ts`; a `Finance` component using `usePlaidLink`.

- [ ] **Step 1: Add dependency**

Run: `cd frontend && npm install react-plaid-link`

- [ ] **Step 2: Write the failing api-client test** (mirror the existing `lib/api` test file)

```typescript
// frontend/lib/api.finance.test.ts
import { describe, expect, it, vi } from "vitest";
import { listAccounts } from "./api";

describe("listAccounts", () => {
  it("sends bearer token and returns accounts", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, json: async () => [{ name: "Checking", type: "depository", subtype: "checking", current_balance: "500", iso_currency: "USD" }],
    });
    vi.stubGlobal("fetch", fetchMock);
    const accounts = await listAccounts("tok", "http://api");
    expect(accounts[0].name).toBe("Checking");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://api/finance/accounts",
      expect.objectContaining({ headers: expect.objectContaining({ Authorization: "Bearer tok" }) }),
    );
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npm test -- api.finance`
Expected: FAIL — `listAccounts` not exported.

- [ ] **Step 4: Implement the api client** in `frontend/lib/api.ts`

```typescript
export interface FinanceAccount {
  name: string; type: string; subtype: string | null;
  current_balance: string | null; iso_currency: string | null;
}

export async function createLinkToken(token: string, apiBase?: string): Promise<string> {
  const base = resolveApiBase(apiBase);
  const r = await fetch(`${base}/finance/link/token`, {
    method: "POST", headers: { Authorization: `Bearer ${token}` },
  });
  if (!r.ok) throw new Error(`link token failed: ${r.status}`);
  return (await r.json()).link_token;
}

export async function exchangePublicToken(publicToken: string, token: string, apiBase?: string): Promise<string> {
  const base = resolveApiBase(apiBase);
  const r = await fetch(`${base}/finance/link/exchange`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ public_token: publicToken }),
  });
  if (!r.ok) throw new Error(`exchange failed: ${r.status}`);
  return (await r.json()).institution;
}

export async function listAccounts(token: string, apiBase?: string): Promise<FinanceAccount[]> {
  const base = resolveApiBase(apiBase);
  const r = await fetch(`${base}/finance/accounts`, { headers: { Authorization: `Bearer ${token}` } });
  if (!r.ok) throw new Error(`accounts failed: ${r.status}`);
  return await r.json();
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npm test -- api.finance`
Expected: PASS.

- [ ] **Step 6: Build the component** `frontend/app/Finance.tsx`

```tsx
"use client";
import { useCallback, useEffect, useState } from "react";
import { usePlaidLink } from "react-plaid-link";
import { createLinkToken, exchangePublicToken, listAccounts, type FinanceAccount } from "../lib/api";

export function Finance({ token }: { token: string }) {
  const [linkToken, setLinkToken] = useState<string | null>(null);
  const [accounts, setAccounts] = useState<FinanceAccount[]>([]);

  const refresh = useCallback(() => { listAccounts(token).then(setAccounts).catch(() => {}); }, [token]);
  useEffect(() => { refresh(); }, [refresh]);

  const onSuccess = useCallback(async (publicToken: string) => {
    await exchangePublicToken(publicToken, token); refresh();
  }, [token, refresh]);

  const { open, ready } = usePlaidLink({ token: linkToken, onSuccess });

  return (
    <div>
      <button onClick={async () => { setLinkToken(await createLinkToken(token)); }}>
        Prepare bank connection
      </button>
      <button disabled={!ready} onClick={() => open()}>Connect a bank</button>
      <ul>
        {accounts.map((a) => (
          <li key={a.name}>{a.name} ({a.subtype ?? a.type}): {a.current_balance} {a.iso_currency}</li>
        ))}
      </ul>
    </div>
  );
}
```

Render it from `Workspace.tsx` (add a "Finance" view alongside chat, following the existing tab/section pattern).

- [ ] **Step 7: Run frontend gates**

Run: `cd frontend && npm run lint && npm test && npm run build`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add frontend/
git commit -m "feat(finance): Connect-a-bank page (Plaid Link) + accounts view"
```

---

### Task 14: Full verification + docs

**Files:**
- Modify: `docs/ARCHITECTURE.md` (add finance module/topology + roadmap mark)
- Modify: `.env.example` already done (Task 2); verify representative
- Run: full backend + frontend suites, `make docs-check`

- [ ] **Step 1: Full gates**

Run: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest -q`
Then: `cd frontend && npm run lint && npm test && npm run build`
Then: `make docs-check`
Expected: all green.

- [ ] **Step 2: Live Sandbox smoke** (with Sandbox creds in `.env`, `PLAID_ENV=sandbox`)

Run: `make up` then exercise: `POST /finance/sync` (after linking a Sandbox item via the web Connect-a-bank using Plaid's `user_good`/`pass_good`), then a chat: *"what are my account balances and how much did I spend this month?"*
Expected: balances + spending returned from stored Sandbox data.

- [ ] **Step 3: Update `docs/ARCHITECTURE.md`** — add the `finance` module to the components table, the Plaid Link flow to the topology, and mark Phase 5 in the roadmap. Re-run `make docs-check`.

- [ ] **Step 4: Commit**

```bash
git add docs/ARCHITECTURE.md
git commit -m "docs(finance): ARCHITECTURE — finance module, Plaid flow, Phase 5"
```

---

## Self-Review

**Spec coverage:** accounts/balances (Tasks 3,5,7,9), transactions + categorized spending (5,7,11), investments/holdings + net worth (5,7,11), liabilities/mortgage + upcoming bills (5,7,11), Link flow (6,9,13), sync cursor (6,11), encryption of token (1,6), read-only safety test (11), daily + weekly digest (10), scheduler job (12), sandbox-first testing (11,14), config/deps/migration (2,3). All spec sections map to tasks.

**Placeholder scan:** no TBD/TODO; every code step has complete code. The one external-API caveat (plaid-python exact model names) is explicitly flagged with a docs link and validated by the Sandbox integration test (Task 11) — not a silent placeholder.

**Type consistency:** `PlaidClient` Protocol methods (Task 4) match `FakePlaid` (Task 6), `PlaidApiClient` (Task 11), and `FinanceService` calls. Store method names used by the service (Task 6) and tools (Task 7) match Task 5 definitions. `build_agent_tools(..., finance_service=)` matches across Tasks 7/8. `build_finance_service(settings, session_factory)` signature matches deps (Task 9) and mcp_memory (Task 8).

**Open follow-ups (not v1):** column-level encryption of transaction details; OAuth-bank redirect config for production; institution_name enrichment on exchange (currently a placeholder string — refine via `/institutions/get_by_id` in a later pass).
