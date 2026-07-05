"""Add consultant training coaching actions

Revision ID: 055_consultant_training_coaching_actions
Revises: 054_consultant_training_shift_reflections
Create Date: 2026-06-01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "055_consultant_training_coaching_actions"
down_revision = "054_consultant_training_shift_reflections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consultant_training_coaching_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reflection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultant_training_shift_reflections.id", ondelete="SET NULL"), nullable=True),
        sa.Column("seller_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="new"),
        sa.Column("planned_for", sa.Date(), nullable=True),
        sa.Column("store_name", sa.String(length=255), nullable=True),
        sa.Column("coaching_topic", sa.Text(), nullable=False),
        sa.Column("competency", sa.String(length=255), nullable=True),
        sa.Column("kpi_metric", sa.String(length=255), nullable=True),
        sa.Column("risk_flags", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("manager_script", sa.Text(), nullable=True),
        sa.Column("seller_next_step", sa.Text(), nullable=True),
        sa.Column("manager_result", sa.Text(), nullable=True),
        sa.Column("seller_visible_feedback", sa.Text(), nullable=True),
        sa.Column("discussed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_consultant_training_coaching_actions_seller_status", "consultant_training_coaching_actions", ["seller_user_id", "status"])
    op.create_index("ix_consultant_training_coaching_actions_status_planned", "consultant_training_coaching_actions", ["status", "planned_for"])
    op.create_index("ix_consultant_training_coaching_actions_reflection_id", "consultant_training_coaching_actions", ["reflection_id"])
    op.create_index("ix_consultant_training_coaching_actions_store_name", "consultant_training_coaching_actions", ["store_name"])
    op.create_index("ix_consultant_training_coaching_actions_competency", "consultant_training_coaching_actions", ["competency"])


def downgrade() -> None:
    op.drop_index("ix_consultant_training_coaching_actions_competency", table_name="consultant_training_coaching_actions")
    op.drop_index("ix_consultant_training_coaching_actions_store_name", table_name="consultant_training_coaching_actions")
    op.drop_index("ix_consultant_training_coaching_actions_reflection_id", table_name="consultant_training_coaching_actions")
    op.drop_index("ix_consultant_training_coaching_actions_status_planned", table_name="consultant_training_coaching_actions")
    op.drop_index("ix_consultant_training_coaching_actions_seller_status", table_name="consultant_training_coaching_actions")
    op.drop_table("consultant_training_coaching_actions")
