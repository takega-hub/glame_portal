"""consultant training attestations

Revision ID: 052_consultant_training_attestations
Revises: 051_consultant_training_step_submissions
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "052_consultant_training_attestations"
down_revision = "051_consultant_training_step_submissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consultant_training_attestations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultant_training_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultant_training_enrollments.id", ondelete="CASCADE"), nullable=True),
        sa.Column("seller_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attestation_type", sa.String(length=80), nullable=False, server_default="trainee_final"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column("task_payload", postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("answer_payload", postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("competency_snapshot", postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("ai_score", sa.Integer(), nullable=True),
        sa.Column("ai_evaluation", postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("manager_decision", sa.String(length=50), nullable=True),
        sa.Column("manager_feedback", sa.Text(), nullable=True),
        sa.Column("certified_level", sa.String(length=80), nullable=True),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_consultant_training_attestations_program_id", "consultant_training_attestations", ["program_id"])
    op.create_index("ix_consultant_training_attestations_seller_user_id", "consultant_training_attestations", ["seller_user_id"])
    op.create_index("ix_consultant_training_attestations_review", "consultant_training_attestations", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_consultant_training_attestations_review", table_name="consultant_training_attestations")
    op.drop_index("ix_consultant_training_attestations_seller_user_id", table_name="consultant_training_attestations")
    op.drop_index("ix_consultant_training_attestations_program_id", table_name="consultant_training_attestations")
    op.drop_table("consultant_training_attestations")
