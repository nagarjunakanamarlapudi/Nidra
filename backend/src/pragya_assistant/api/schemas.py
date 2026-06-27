"""Request/response models for the API."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from pragya_assistant.llm.types import Effort


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, description="The user's message")
    conversation_id: int | None = Field(
        default=None, description="Existing conversation to continue; omit to start a new one"
    )
    effort: Effort | None = Field(
        default=None, description="Reasoning effort for this turn: low / medium / high"
    )


class ChatResponse(BaseModel):
    reply: str
    conversation_id: int


class ConversationSummaryOut(BaseModel):
    id: int
    title: str
    created_at: dt.datetime


class MessageOut(BaseModel):
    role: str
    content: str


class ConversationDetailOut(BaseModel):
    id: int
    messages: list[MessageOut]


class DigestOut(BaseModel):
    id: int
    content: str
    delivered: str
    created_at: dt.datetime


class ExchangeIn(BaseModel):
    public_token: str


class AccountOut(BaseModel):
    account_id: int
    item_id: int
    institution: str
    institution_logo: str | None
    institution_color: str | None
    name: str
    official_name: str | None
    mask: str | None
    type: str
    subtype: str | None
    current_balance: Decimal | None
    iso_currency: str | None


class HoldingOut(BaseModel):
    account_id: int
    ticker: str | None
    security_name: str
    quantity: Decimal
    price: Decimal | None
    value: Decimal | None
    iso_currency: str | None
    cost_basis: Decimal | None = None
    lots: list[dict[str, Any]] | None = None
    security_id: str | None = None


class TransactionOut(BaseModel):
    id: int
    date: dt.date
    name: str
    merchant_name: str | None
    amount: Decimal
    category: str | None
    pending: bool


class InvestmentTransactionOut(BaseModel):
    id: int
    date: dt.date
    name: str
    type: str
    subtype: str | None
    ticker: str | None
    security_id: str | None
    quantity: Decimal
    price: Decimal | None
    amount: Decimal
    fees: Decimal | None


class FxOut(BaseModel):
    usd_inr: Decimal | None
    as_of: str | None


# --- Connectors ---


class ConnectorFieldOut(BaseModel):
    key: str
    label: str
    type: str
    required: bool
    help: str | None = None
    placeholder: str | None = None
    options: list[str] = Field(default_factory=list)
    default: str | int | bool | None = None


class ConnectorAccountOut(BaseModel):
    id: int
    label: str
    status: str
    granted_scopes: list[str] = Field(default_factory=list)


class ConnectorSummaryOut(BaseModel):
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
    configured_fields: list[str]
    oauth_server_configured: bool
    accounts: list[ConnectorAccountOut] = Field(default_factory=list)


class ConnectorDetailOut(ConnectorSummaryOut):
    config_schema: list[ConnectorFieldOut]
    docs_url: str | None


class EnableSecretIn(BaseModel):
    config: dict[str, Any]


class OAuthStartIn(BaseModel):
    config: dict[str, Any]


class OAuthAppIn(BaseModel):
    """Shared OAuth app credentials saved once from the UI (then one-click)."""

    client_id: str = Field(min_length=1)
    client_secret: str = Field(min_length=1)


class OAuthStartOut(BaseModel):
    authorize_url: str


class ConnectorHealthOut(BaseModel):
    ok: bool
    detail: str | None = None
