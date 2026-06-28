"""SQLAlchemy ORM models — the structured half of memory."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.orm import relationship as orm_relationship

# DB schema dimension for note embeddings. Must equal settings.llm_embedding_dim;
# validated at startup so a misconfigured embedder fails loudly, not silently.
EMBEDDING_DIM = 1536


class Base(DeclarativeBase):
    pass


class Person(Base):
    __tablename__ = "people"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    relationship: Mapped[str | None] = mapped_column(String(255), default=None)
    birthday: Mapped[dt.date | None] = mapped_column(default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), default=None)
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())


class Preference(Base):
    __tablename__ = "preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    value: Mapped[str] = mapped_column(Text)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())

    messages: Mapped[list[ConversationMessage]] = orm_relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.id",
    )


class Digest(Base):
    __tablename__ = "digests"

    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    delivered: Mapped[str] = mapped_column(String(20), default="stored")
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    due_date: Mapped[dt.date | None] = mapped_column(default=None)
    done: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())


class ConversationMessage(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())

    conversation: Mapped[Conversation] = orm_relationship(back_populates="messages")


class PlaidItem(Base):
    __tablename__ = "plaid_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    institution_name: Mapped[str] = mapped_column(String(200))
    institution_logo: Mapped[str | None] = mapped_column(Text, default=None)
    institution_color: Mapped[str | None] = mapped_column(Text, default=None)
    access_token: Mapped[str] = mapped_column(Text)  # encrypted
    item_id: Mapped[str] = mapped_column(String(100), unique=True)
    transactions_cursor: Mapped[str | None] = mapped_column(Text, default=None)
    last_synced_at: Mapped[dt.datetime | None] = mapped_column(default=None)
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("plaid_items.id", ondelete="CASCADE"), index=True
    )
    plaid_account_id: Mapped[str] = mapped_column(String(100), unique=True)
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
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    plaid_txn_id: Mapped[str] = mapped_column(String(100), unique=True)
    date: Mapped[dt.date] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(Text)
    merchant_name: Mapped[str | None] = mapped_column(String(200), default=None)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    category: Mapped[str | None] = mapped_column(String(100), default=None)
    pending: Mapped[bool] = mapped_column(default=False)


class Holding(Base):
    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    security_id: Mapped[str | None] = mapped_column(String(100), default=None, index=True)
    security_name: Mapped[str] = mapped_column(String(200))
    ticker: Mapped[str | None] = mapped_column(String(20), default=None)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)
    value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)
    iso_currency: Mapped[str | None] = mapped_column(String(3), default=None)
    cost_basis: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True, default=None)
    lots: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB, nullable=True, default=None)


class Liability(Base):
    __tablename__ = "liabilities"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(30))  # mortgage | credit | student
    apr: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), default=None)
    next_payment_due: Mapped[dt.date | None] = mapped_column(default=None)
    next_payment_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)
    balance: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)


class ConnectorInstance(Base):
    """The *enabled* state of a connector — what env vars used to be, now a row.

    ``config`` is an encrypted JSON blob (secrets + OAuth tokens + settings),
    decrypted only in memory by the store. One instance per connector (single-user).
    """

    __tablename__ = "connector_instances"

    id: Mapped[int] = mapped_column(primary_key=True)
    connector_key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(20), default="disabled")
    config: Mapped[str] = mapped_column(Text, default="")  # encrypted JSON
    granted_scopes: Mapped[list[str] | None] = mapped_column(JSONB, default=None)
    last_sync_at: Mapped[dt.datetime | None] = mapped_column(default=None)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class ConnectorAccount(Base):
    """One linked external account for a connector (enables multi-account).

    A connector (e.g. Google Calendar) may have several accounts — one per Google
    login. ``config`` is encrypted JSON (OAuth tokens); ``external_account_id`` is
    the provider's stable identity (e.g. the email) used to dedupe re-connects so
    connecting the same account again updates it rather than creating a duplicate.
    """

    __tablename__ = "connector_accounts"
    __table_args__ = (
        UniqueConstraint(
            "connector_key", "external_account_id", name="uq_connector_account_identity"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    connector_key: Mapped[str] = mapped_column(String(100), index=True)
    external_account_id: Mapped[str] = mapped_column(String(255))
    label: Mapped[str] = mapped_column(String(255))
    config: Mapped[str] = mapped_column(Text, default="")  # encrypted JSON (OAuth tokens)
    granted_scopes: Mapped[list[str] | None] = mapped_column(JSONB, default=None)
    status: Mapped[str] = mapped_column(String(20), default="connected")
    last_sync_at: Mapped[dt.datetime | None] = mapped_column(default=None)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class ConnectorAppCredential(Base):
    """Shared OAuth *app* credentials (client id/secret) for a provider, set once
    from the UI so connecting becomes one-click. ``config`` is encrypted JSON.
    Provider-keyed so sibling connectors (Google Calendar + Gmail) reuse one app.
    """

    __tablename__ = "connector_app_credentials"

    provider: Mapped[str] = mapped_column(String(50), primary_key=True)
    config: Mapped[str] = mapped_column(Text)  # encrypted JSON {client_id, client_secret}
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class ConnectorOAuthFlow(Base):
    """A short-lived in-flight OAuth authorization (state + PKCE verifier).

    Created when the consent redirect is launched, consumed (deleted) at callback.
    """

    __tablename__ = "connector_oauth_flow"

    state: Mapped[str] = mapped_column(String(128), primary_key=True)
    connector_key: Mapped[str] = mapped_column(String(100), index=True)
    code_verifier: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())


class CalendarEvent(Base):
    """An ingested calendar event (one connector's bespoke store).

    All-day events are stored as midnight datetimes with ``all_day=True``.
    """

    __tablename__ = "calendar_events"
    __table_args__ = (
        UniqueConstraint(
            "connector_key",
            "account_label",
            "uid",
            name="uq_calendar_event_connector_account_uid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    connector_key: Mapped[str] = mapped_column(String(100), index=True)
    # Which linked account these events came from (the email); "" for single-account.
    account_label: Mapped[str] = mapped_column(String(255), default="", server_default="")
    uid: Mapped[str] = mapped_column(String(512), index=True)
    summary: Mapped[str] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text, default=None)
    start: Mapped[dt.datetime] = mapped_column(index=True)
    end: Mapped[dt.datetime | None] = mapped_column(default=None)
    all_day: Mapped[bool] = mapped_column(default=False)
    calendar_id: Mapped[str | None] = mapped_column(String(255), default=None)
    updated_at: Mapped[dt.datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class InvestmentTransaction(Base):
    __tablename__ = "investment_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    plaid_investment_txn_id: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    security_id: Mapped[str | None] = mapped_column(String(100), default=None, index=True)
    ticker: Mapped[str | None] = mapped_column(String(20), default=None)
    name: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(50))
    subtype: Mapped[str | None] = mapped_column(String(50), default=None)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    fees: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), default=None)
    date: Mapped[dt.date] = mapped_column(index=True)


class BrowserActivityEvent(Base):
    """One ingested browser-activity signal pushed from the Nidra extension.

    The structured half of ambient capture: a reading / search / email /
    calendar / page event, redacted client-side before it is sent. ``data``
    holds the type-specific payload. Deduped by ``(connector_key, client_id)``
    so a page's load + flush upsert into a single row instead of double-counting.
    """

    __tablename__ = "browser_activity_events"
    __table_args__ = (
        UniqueConstraint("connector_key", "client_id", name="uq_browser_activity_client"),
        # Correlates impression -> interaction -> action within one page load.
        # btree (not JSONB GIN) because the lookup is equality on (connector_key, context_id).
        Index("ix_browser_activity_context", "connector_key", "context_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    connector_key: Mapped[str] = mapped_column(String(100), index=True)
    client_id: Mapped[str] = mapped_column(String(128), index=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    ts: Mapped[dt.datetime] = mapped_column(index=True)
    source: Mapped[str | None] = mapped_column(String(64), default=None)
    domain: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    url: Mapped[str | None] = mapped_column(Text, default=None)
    title: Mapped[str | None] = mapped_column(Text, default=None)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    # Engagement signal measured client-side: dwellMs (real time-on-page),
    # scrollPct / readPct (how far the page was scrolled / read). Lets the dreamer
    # tell "actually read" from "bounced" rather than just "visited".
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    # Page-load correlation id (the extension's currentPageId). Ties the
    # impression/interaction/action events of one decision together.
    context_id: Mapped[str | None] = mapped_column(String(36), default=None)
    redacted: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())


class UserModelSnapshot(Base):
    """A point-in-time derived trait/preference about the user.

    The distilled, durable half of the holistic user model: where
    ``BrowserActivityEvent`` is the raw substrate, this is what the
    derivation/dreamer pass *concluded* (e.g. "decisiveness", "prefers Apple
    Pay"). Append-only — each pass writes fresh rows so a trait can be tracked
    as it evolves; the "current model" is the latest row per ``trait``.
    """

    __tablename__ = "user_model_snapshots"
    __table_args__ = (Index("ix_user_model_trait_time", "trait", "computed_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    trait: Mapped[str] = mapped_column(String(100), index=True)
    value: Mapped[Any] = mapped_column(JSONB)  # scalar | label | struct
    confidence: Mapped[float] = mapped_column(default=0.0)
    evidence: Mapped[int] = mapped_column(default=0)
    provenance: Mapped[list[str] | None] = mapped_column(JSONB, default=None)
    # Evidence chain: {formula, inputs, event_ids} — traces the trait to its facts.
    derivation: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    computed_at: Mapped[dt.datetime] = mapped_column(server_default=func.now(), index=True)


class Dream(Base):
    """A speculative hypothesis/foresight the dreamer produced ON TOP of Opinions.

    NOT a belief: dreams live here, never in ``user_model_snapshots``. A dream is
    surfaced (e.g. as a digest item), then resolved by a REAL outcome — acted /
    corroborated (→ confirmed) or dismissed (→ refuted); unacted dreams expire via
    TTL. Resolved dreams are the recursive-self-improvement track record.
    """

    __tablename__ = "dreams"
    __table_args__ = (Index("ix_dreams_status", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    hypothesis: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(32))  # foresight | suggestion | need
    confidence: Mapped[float] = mapped_column(default=0.0)
    provenance: Mapped[list[str] | None] = mapped_column(JSONB, default=None)
    # proposed → surfaced → (confirmed | refuted | expired)
    status: Mapped[str] = mapped_column(String(16), default="proposed")
    outcome: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    created_at: Mapped[dt.datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[dt.datetime | None] = mapped_column(default=None)
    resolved_at: Mapped[dt.datetime | None] = mapped_column(default=None)
