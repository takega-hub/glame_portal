"""add consultant training modules and steps

Revision ID: 050_consultant_training_modules_steps
Revises: 049_consultant_training_programs
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "050_consultant_training_modules_steps"
down_revision = "049_consultant_training_programs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consultant_training_modules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["program_id"], ["consultant_training_programs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_consultant_training_modules_program_id", "consultant_training_modules", ["program_id"])

    op.create_table(
        "consultant_training_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("lesson_text", sa.Text(), nullable=True),
        sa.Column("practice_text", sa.Text(), nullable=True),
        sa.Column("answer_template", sa.Text(), nullable=True),
        sa.Column("assessment_rubric", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("competencies", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("unlock_rule", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["module_id"], ["consultant_training_modules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_consultant_training_steps_module_id", "consultant_training_steps", ["module_id"])


def downgrade() -> None:
    op.drop_index("ix_consultant_training_steps_module_id", table_name="consultant_training_steps")
    op.drop_table("consultant_training_steps")
    op.drop_index("ix_consultant_training_modules_program_id", table_name="consultant_training_modules")
    op.drop_table("consultant_training_modules")
