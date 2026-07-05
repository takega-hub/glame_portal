"""add consultant training module

Revision ID: 048_consultant_training
Revises: 047_customer_favorite_products
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "048_consultant_training"
down_revision = "047_customer_favorite_products"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consultant_training_topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lesson_date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("theme", sa.String(length=500), nullable=True),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("material_text", sa.Text(), nullable=True),
        sa.Column("assignment_text", sa.Text(), nullable=True),
        sa.Column("focus_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column("approval_comment", sa.Text(), nullable=True),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lesson_date", name="uq_consultant_training_topics_lesson_date"),
    )
    op.create_index("ix_consultant_training_topics_lesson_date", "consultant_training_topics", ["lesson_date"])
    op.create_index("ix_consultant_training_topics_status", "consultant_training_topics", ["status"])
    op.create_index("ix_consultant_training_topics_status_date", "consultant_training_topics", ["status", "lesson_date"])

    op.create_table(
        "consultant_training_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seller_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="not_opened"),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["seller_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_id"], ["consultant_training_topics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("topic_id", "seller_user_id", name="uq_consultant_training_assignment_topic_seller"),
    )
    op.create_index("ix_consultant_training_assignments_topic_id", "consultant_training_assignments", ["topic_id"])
    op.create_index("ix_consultant_training_assignments_seller_user_id", "consultant_training_assignments", ["seller_user_id"])
    op.create_index("ix_consultant_training_assignments_status", "consultant_training_assignments", ["status"])

    op.create_table(
        "consultant_training_submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("seller_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("practice_answer", sa.Text(), nullable=False),
        sa.Column("evening_review", sa.Text(), nullable=True),
        sa.Column("ai_score", sa.Integer(), nullable=True),
        sa.Column("ai_evaluation", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("review_status", sa.String(length=50), nullable=False, server_default="review_pending"),
        sa.Column("manager_feedback", sa.Text(), nullable=True),
        sa.Column("consultant_feedback", sa.Text(), nullable=True),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_to_consultant_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["assignment_id"], ["consultant_training_assignments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["seller_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_id"], ["consultant_training_topics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_consultant_training_submissions_topic_id", "consultant_training_submissions", ["topic_id"])
    op.create_index("ix_consultant_training_submissions_assignment_id", "consultant_training_submissions", ["assignment_id"])
    op.create_index("ix_consultant_training_submissions_seller_user_id", "consultant_training_submissions", ["seller_user_id"])
    op.create_index("ix_consultant_training_submissions_review_status", "consultant_training_submissions", ["review_status"])
    op.create_index("ix_consultant_training_submissions_review", "consultant_training_submissions", ["review_status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_consultant_training_submissions_review", table_name="consultant_training_submissions")
    op.drop_index("ix_consultant_training_submissions_review_status", table_name="consultant_training_submissions")
    op.drop_index("ix_consultant_training_submissions_seller_user_id", table_name="consultant_training_submissions")
    op.drop_index("ix_consultant_training_submissions_assignment_id", table_name="consultant_training_submissions")
    op.drop_index("ix_consultant_training_submissions_topic_id", table_name="consultant_training_submissions")
    op.drop_table("consultant_training_submissions")
    op.drop_index("ix_consultant_training_assignments_status", table_name="consultant_training_assignments")
    op.drop_index("ix_consultant_training_assignments_seller_user_id", table_name="consultant_training_assignments")
    op.drop_index("ix_consultant_training_assignments_topic_id", table_name="consultant_training_assignments")
    op.drop_table("consultant_training_assignments")
    op.drop_index("ix_consultant_training_topics_status_date", table_name="consultant_training_topics")
    op.drop_index("ix_consultant_training_topics_status", table_name="consultant_training_topics")
    op.drop_index("ix_consultant_training_topics_lesson_date", table_name="consultant_training_topics")
    op.drop_table("consultant_training_topics")
