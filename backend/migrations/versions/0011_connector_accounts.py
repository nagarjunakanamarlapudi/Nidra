"""connector accounts (multi-account per connector)

Revision ID: 0011
Revises: 0010
Create Date: 2026-06-25

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connector_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connector_key", sa.String(100), nullable=False),
        sa.Column("external_account_id", sa.String(255), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("config", sa.Text(), nullable=False, server_default=""),
        sa.Column("granted_scopes", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="connected"),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connector_key", "external_account_id", name="uq_connector_account_identity"
        ),
    )
    op.create_index("ix_connector_accounts_connector_key", "connector_accounts", ["connector_key"])


def downgrade() -> None:
    op.drop_index("ix_connector_accounts_connector_key", table_name="connector_accounts")
    op.drop_table("connector_accounts")
