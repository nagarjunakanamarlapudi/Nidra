"""scenarios — competing, falsifiable predictions of the user's next actions

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-28

A ScenarioBatch groups the branches generated from one point-in-time context
snapshot. The verifier resolves each branch by corroboration against real
activity (confirmed | refuted | expired); only a competing sibling being
corroborated can refute a branch (otherwise the batch expires — weak signal,
never a negative). Scenarios are written here ONLY (never user_model_snapshots);
resolved batches are the RSI track record. scenario_lessons holds the low-weight,
decaying in-context exemplars the reconciler produces from mis-ranked batches.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scenario_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("context_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("due_at", sa.DateTime(), nullable=False),
        sa.Column("diagnosis", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("lessons_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_scenario_batches_status_due", "scenario_batches", ["status", "due_at"]
    )

    op.create_table(
        "scenarios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "batch_id",
            sa.Integer(),
            sa.ForeignKey("scenario_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("checkpoints", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("prior", sa.Float(), nullable=False, server_default="0"),
        sa.Column("rank", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deadline_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("outcome", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("derivation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_scenarios_batch", "scenarios", ["batch_id"])
    op.create_index("ix_scenarios_status", "scenarios", ["status"])
    op.create_index("ix_scenarios_deadline_at", "scenarios", ["deadline_at"])

    op.create_table(
        "scenario_lessons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "batch_id",
            sa.Integer(),
            sa.ForeignKey("scenario_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("predicted_branches", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("what_happened", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("hypothesized_missing_context", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("base_weight", sa.Float(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_scenario_lessons_batch", "scenario_lessons", ["batch_id"])


def downgrade() -> None:
    op.drop_index("ix_scenario_lessons_batch", table_name="scenario_lessons")
    op.drop_table("scenario_lessons")
    op.drop_index("ix_scenarios_deadline_at", table_name="scenarios")
    op.drop_index("ix_scenarios_status", table_name="scenarios")
    op.drop_index("ix_scenarios_batch", table_name="scenarios")
    op.drop_table("scenarios")
    op.drop_index("ix_scenario_batches_status_due", table_name="scenario_batches")
    op.drop_table("scenario_batches")
