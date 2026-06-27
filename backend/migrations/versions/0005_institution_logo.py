"""add institution_logo to plaid_items

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-21

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plaid_items", sa.Column("institution_logo", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("plaid_items", "institution_logo")
