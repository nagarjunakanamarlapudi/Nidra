"""calendar events scoped by account (multi-account calendar)

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-25

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "calendar_events",
        sa.Column("account_label", sa.String(255), nullable=False, server_default=""),
    )
    op.drop_constraint("uq_calendar_event_connector_uid", "calendar_events", type_="unique")
    # Events are a re-syncable cache; clear so they repopulate per-account (with the
    # right account_label) on the next sync, avoiding stale unlabelled duplicates.
    op.execute("DELETE FROM calendar_events")
    op.create_unique_constraint(
        "uq_calendar_event_connector_account_uid",
        "calendar_events",
        ["connector_key", "account_label", "uid"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_calendar_event_connector_account_uid", "calendar_events", type_="unique")
    op.drop_column("calendar_events", "account_label")
    op.create_unique_constraint(
        "uq_calendar_event_connector_uid", "calendar_events", ["connector_key", "uid"]
    )
