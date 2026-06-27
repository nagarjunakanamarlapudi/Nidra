"""add security_id to holdings; create investment_transactions table

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-21

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add security_id to holdings for buy/sell linking
    op.add_column(
        "holdings",
        sa.Column("security_id", sa.String(100), nullable=True),
    )
    op.create_index("ix_holdings_security_id", "holdings", ["security_id"], unique=False)

    # Create investment_transactions table
    op.create_table(
        "investment_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("plaid_investment_txn_id", sa.String(200), nullable=False),
        sa.Column("security_id", sa.String(100), nullable=True),
        sa.Column("ticker", sa.String(20), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("subtype", sa.String(50), nullable=True),
        sa.Column("quantity", sa.Numeric(20, 6), nullable=False),
        sa.Column("price", sa.Numeric(14, 2), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("fees", sa.Numeric(14, 2), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_investment_transactions_account_id",
        "investment_transactions",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        "ix_investment_transactions_plaid_investment_txn_id",
        "investment_transactions",
        ["plaid_investment_txn_id"],
        unique=True,
    )
    op.create_index(
        "ix_investment_transactions_security_id",
        "investment_transactions",
        ["security_id"],
        unique=False,
    )
    op.create_index(
        "ix_investment_transactions_date",
        "investment_transactions",
        ["date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("investment_transactions")
    op.drop_index("ix_holdings_security_id", table_name="holdings")
    op.drop_column("holdings", "security_id")
