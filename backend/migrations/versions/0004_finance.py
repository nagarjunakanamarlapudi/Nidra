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
    op.create_index("ix_plaid_items_item_id", "plaid_items", ["item_id"], unique=True)
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "item_id",
            sa.Integer(),
            sa.ForeignKey("plaid_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
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
    op.create_index("ix_accounts_plaid_account_id", "accounts", ["plaid_account_id"], unique=True)
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("plaid_txn_id", sa.String(length=100), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("merchant_name", sa.String(length=200), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("pending", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_transactions_account_id", "transactions", ["account_id"])
    op.create_index("ix_transactions_plaid_txn_id", "transactions", ["plaid_txn_id"], unique=True)
    op.create_index("ix_transactions_date", "transactions", ["date"])
    op.create_table(
        "holdings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
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
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
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
