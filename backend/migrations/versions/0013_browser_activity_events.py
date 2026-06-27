"""browser activity events (Browser Activity connector ingest store)

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-28

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "browser_activity_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("connector_key", sa.String(length=100), nullable=False),
        sa.Column("client_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("redacted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("connector_key", "client_id", name="uq_browser_activity_client"),
    )
    op.create_index(
        "ix_browser_activity_events_connector_key", "browser_activity_events", ["connector_key"]
    )
    op.create_index(
        "ix_browser_activity_events_client_id", "browser_activity_events", ["client_id"]
    )
    op.create_index(
        "ix_browser_activity_events_event_type", "browser_activity_events", ["event_type"]
    )
    op.create_index("ix_browser_activity_events_ts", "browser_activity_events", ["ts"])
    op.create_index("ix_browser_activity_events_domain", "browser_activity_events", ["domain"])


def downgrade() -> None:
    op.drop_index("ix_browser_activity_events_domain", table_name="browser_activity_events")
    op.drop_index("ix_browser_activity_events_ts", table_name="browser_activity_events")
    op.drop_index("ix_browser_activity_events_event_type", table_name="browser_activity_events")
    op.drop_index("ix_browser_activity_events_client_id", table_name="browser_activity_events")
    op.drop_index("ix_browser_activity_events_connector_key", table_name="browser_activity_events")
    op.drop_table("browser_activity_events")
