"""consultant training step submissions

Revision ID: 051_consultant_training_step_submissions
Revises: 050_consultant_training_modules_steps
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "051_consultant_training_step_submissions"
down_revision = "050_consultant_training_modules_steps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consultant_training_step_submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultant_training_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultant_training_steps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultant_training_enrollments.id", ondelete="CASCADE"), nullable=True),
        sa.Column("seller_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("practice_answer", sa.Text(), nullable=False),
        sa.Column("evening_review", sa.Text(), nullable=True),
        sa.Column("ai_score", sa.Integer(), nullable=True),
        sa.Column("ai_evaluation", postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("review_status", sa.String(length=50), nullable=False, server_default="review_pending"),
        sa.Column("manager_feedback", sa.Text(), nullable=True),
        sa.Column("consultant_feedback", sa.Text(), nullable=True),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_to_consultant_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_consultant_training_step_submissions_program_id", "consultant_training_step_submissions", ["program_id"])
    op.create_index("ix_consultant_training_step_submissions_step_id", "consultant_training_step_submissions", ["step_id"])
    op.create_index("ix_consultant_training_step_submissions_seller_user_id", "consultant_training_step_submissions", ["seller_user_id"])
    op.create_index("ix_consultant_training_step_submissions_review", "consultant_training_step_submissions", ["review_status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_consultant_training_step_submissions_review", table_name="consultant_training_step_submissions")
    op.drop_index("ix_consultant_training_step_submissions_seller_user_id", table_name="consultant_training_step_submissions")
    op.drop_index("ix_consultant_training_step_submissions_step_id", table_name="consultant_training_step_submissions")
    op.drop_index("ix_consultant_training_step_submissions_program_id", table_name="consultant_training_step_submissions")
    op.drop_table("consultant_training_step_submissions")
