"""user model snapshots (distilled, durable traits/preferences)

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-27

Append-only snapshots of what the derivation/dreamer pass concluded about the
user. The "current model" is the latest row per trait; history is preserved so
traits can be tracked as they evolve.

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_model_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trait", sa.String(length=100), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("evidence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("computed_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_model_snapshots_trait", "user_model_snapshots", ["trait"])
    op.create_index(
        "ix_user_model_trait_time", "user_model_snapshots", ["trait", "computed_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_user_model_trait_time", table_name="user_model_snapshots")
    op.drop_index("ix_user_model_snapshots_trait", table_name="user_model_snapshots")
    op.drop_table("user_model_snapshots")
