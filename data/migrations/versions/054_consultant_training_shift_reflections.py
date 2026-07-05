"""consultant training shift reflections

Revision ID: 054_consultant_training_shift_reflections
Revises: 053_consultant_training_mentor_messages
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "054_consultant_training_shift_reflections"
down_revision = "053_consultant_training_mentor_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consultant_training_shift_reflections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("seller_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shift_date", sa.Date(), nullable=True),
        sa.Column("store_name", sa.String(length=255), nullable=True),
        sa.Column("daily_focus_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("reflection_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("ai_score", sa.Integer(), nullable=True),
        sa.Column("ai_evaluation", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="submitted"),
        sa.Column("risk_flags", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("manager_note", sa.Text(), nullable=True),
        sa.Column("manager_feedback", sa.Text(), nullable=True),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_consultant_training_shift_reflections_seller_date", "consultant_training_shift_reflections", ["seller_user_id", "shift_date"])
    op.create_index("ix_consultant_training_shift_reflections_status_created", "consultant_training_shift_reflections", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_consultant_training_shift_reflections_status_created", table_name="consultant_training_shift_reflections")
    op.drop_index("ix_consultant_training_shift_reflections_seller_date", table_name="consultant_training_shift_reflections")
    op.drop_table("consultant_training_shift_reflections")
