"""connectors platform: instances, oauth flows, calendar events

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-23

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connector_instances",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connector_key", sa.String(100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("config", sa.Text(), nullable=False),
        sa.Column("granted_scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_connector_instances_connector_key",
        "connector_instances",
        ["connector_key"],
        unique=True,
    )

    op.create_table(
        "connector_oauth_flow",
        sa.Column("state", sa.String(128), nullable=False),
        sa.Column("connector_key", sa.String(100), nullable=False),
        sa.Column("code_verifier", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("state"),
    )
    op.create_index(
        "ix_connector_oauth_flow_connector_key",
        "connector_oauth_flow",
        ["connector_key"],
        unique=False,
    )

    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connector_key", sa.String(100), nullable=False),
        sa.Column("uid", sa.String(512), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("start", sa.DateTime(), nullable=False),
        sa.Column("end", sa.DateTime(), nullable=True),
        sa.Column("all_day", sa.Boolean(), nullable=False),
        sa.Column("calendar_id", sa.String(255), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connector_key", "uid", name="uq_calendar_event_connector_uid"),
    )
    op.create_index(
        "ix_calendar_events_connector_key", "calendar_events", ["connector_key"], unique=False
    )
    op.create_index("ix_calendar_events_uid", "calendar_events", ["uid"], unique=False)
    op.create_index("ix_calendar_events_start", "calendar_events", ["start"], unique=False)


def downgrade() -> None:
    op.drop_table("calendar_events")
    op.drop_index("ix_connector_oauth_flow_connector_key", table_name="connector_oauth_flow")
    op.drop_table("connector_oauth_flow")
    op.drop_index("ix_connector_instances_connector_key", table_name="connector_instances")
    op.drop_table("connector_instances")
