"""add consultant training programs

Revision ID: 049_consultant_training_programs
Revises: 048_consultant_training
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "049_consultant_training_programs"
down_revision = "048_consultant_training"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consultant_training_programs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("program_type", sa.String(length=80), nullable=False, server_default="custom"),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
        sa.Column("audience_rules", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_consultant_training_programs_code"),
    )
    op.create_index("ix_consultant_training_programs_code", "consultant_training_programs", ["code"])
    op.create_index("ix_consultant_training_programs_type_status", "consultant_training_programs", ["program_type", "status"])

    op.create_table(
        "consultant_training_enrollments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seller_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="available"),
        sa.Column("current_topic_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("average_score", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["current_topic_id"], ["consultant_training_topics.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["program_id"], ["consultant_training_programs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["seller_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("program_id", "seller_user_id", name="uq_consultant_training_enrollment_program_seller"),
    )
    op.create_index("ix_consultant_training_enrollments_program_id", "consultant_training_enrollments", ["program_id"])
    op.create_index("ix_consultant_training_enrollments_seller_user_id", "consultant_training_enrollments", ["seller_user_id"])
    op.create_index("ix_consultant_training_enrollments_status", "consultant_training_enrollments", ["status"])


def downgrade() -> None:
    op.drop_index("ix_consultant_training_enrollments_status", table_name="consultant_training_enrollments")
    op.drop_index("ix_consultant_training_enrollments_seller_user_id", table_name="consultant_training_enrollments")
    op.drop_index("ix_consultant_training_enrollments_program_id", table_name="consultant_training_enrollments")
    op.drop_table("consultant_training_enrollments")
    op.drop_index("ix_consultant_training_programs_type_status", table_name="consultant_training_programs")
    op.drop_index("ix_consultant_training_programs_code", table_name="consultant_training_programs")
    op.drop_table("consultant_training_programs")
