"""add cost_basis and lots to holdings

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-21

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("holdings", sa.Column("cost_basis", sa.Numeric(14, 2), nullable=True))
    op.add_column(
        "holdings",
        sa.Column("lots", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("holdings", "lots")
    op.drop_column("holdings", "cost_basis")
