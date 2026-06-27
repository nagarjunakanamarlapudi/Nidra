"""browser activity context_id (correlate impression -> interaction -> action)

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-27

Adds the page-load correlation id that ties one decision's impression /
interaction / action events together. btree on (connector_key, context_id)
because the lookup is equality, not JSONB containment.

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "browser_activity_events",
        sa.Column("context_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_browser_activity_context",
        "browser_activity_events",
        ["connector_key", "context_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_browser_activity_context", table_name="browser_activity_events")
    op.drop_column("browser_activity_events", "context_id")
