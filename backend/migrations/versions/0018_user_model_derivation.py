"""user model snapshot derivation (the evidence chain)

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-27

Records HOW each trait was derived — {formula, inputs, event_ids} — so an opinion
is traceable to the exact signals behind it (not just a coarse source label).

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_model_snapshots",
        sa.Column("derivation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_model_snapshots", "derivation")
