"""dreams (speculative hypotheses produced on top of Opinions)

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-27

The dreamer writes here ONLY (never user_model_snapshots). Dreams surface, get
resolved by a real outcome (acted/corroborated → confirmed; dismissed → refuted;
unacted → expired via TTL); resolved dreams are the RSI track record.

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dreams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="proposed"),
        sa.Column("outcome", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_dreams_status", "dreams", ["status"])


def downgrade() -> None:
    op.drop_index("ix_dreams_status", table_name="dreams")
    op.drop_table("dreams")
