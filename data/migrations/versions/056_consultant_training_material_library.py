"""consultant training material library

Revision ID: 056_consultant_training_material_library
Revises: 055_consultant_training_coaching_actions
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "056_consultant_training_material_library"
down_revision = "055_consultant_training_coaching_actions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consultant_training_materials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=False, server_default="Общее"),
        sa.Column("category", sa.String(length=255), nullable=False, server_default="Библиотека GLAME"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("markdown_content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column("tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("source_type", sa.String(length=80), nullable=False, server_default="manual_md"),
        sa.Column("program_code", sa.String(length=80), nullable=True),
        sa.Column("competencies", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("internal_notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_consultant_training_materials_topic_status", "consultant_training_materials", ["topic", "status"])
    op.create_index("ix_consultant_training_materials_category_order", "consultant_training_materials", ["category", "order_index"])
    op.create_index("ix_consultant_training_materials_program_code", "consultant_training_materials", ["program_code"])


def downgrade() -> None:
    op.drop_index("ix_consultant_training_materials_program_code", table_name="consultant_training_materials")
    op.drop_index("ix_consultant_training_materials_category_order", table_name="consultant_training_materials")
    op.drop_index("ix_consultant_training_materials_topic_status", table_name="consultant_training_materials")
    op.drop_table("consultant_training_materials")
