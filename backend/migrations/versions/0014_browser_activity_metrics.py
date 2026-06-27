"""browser activity engagement metrics (dwell time + scroll/read depth)

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-28

The extension already measures dwellMs / scrollPct / readPct per page and ships
them in each event, but the ingest schema had no home for them so they were
dropped. This adds the ``metrics`` JSONB column that captures the engagement
signal — letting the dreamer tell "actually read" from "bounced".

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "browser_activity_events",
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("browser_activity_events", "metrics")
