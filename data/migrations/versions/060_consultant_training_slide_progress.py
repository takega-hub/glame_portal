"""Add consultant training material slide progress

Revision ID: 060_consultant_training_slide_progress
Revises: 059_consultant_training_material_slides
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "060_consultant_training_slide_progress"
down_revision = "059_consultant_training_material_slides"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consultant_training_material_slide_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultant_training_materials.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slide_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultant_training_material_slides.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seller_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("slide_id", "seller_user_id", name="uq_consultant_training_slide_progress_seller"),
    )
    op.create_index("ix_consultant_training_slide_progress_material_seller", "consultant_training_material_slide_progress", ["material_id", "seller_user_id"])
    op.create_index("ix_consultant_training_slide_progress_slide_seller", "consultant_training_material_slide_progress", ["slide_id", "seller_user_id"])
    op.create_index("ix_consultant_training_material_slide_progress_material_id", "consultant_training_material_slide_progress", ["material_id"])
    op.create_index("ix_consultant_training_material_slide_progress_slide_id", "consultant_training_material_slide_progress", ["slide_id"])
    op.create_index("ix_consultant_training_material_slide_progress_seller_user_id", "consultant_training_material_slide_progress", ["seller_user_id"])


def downgrade() -> None:
    op.drop_index("ix_consultant_training_material_slide_progress_seller_user_id", table_name="consultant_training_material_slide_progress")
    op.drop_index("ix_consultant_training_material_slide_progress_slide_id", table_name="consultant_training_material_slide_progress")
    op.drop_index("ix_consultant_training_material_slide_progress_material_id", table_name="consultant_training_material_slide_progress")
    op.drop_index("ix_consultant_training_slide_progress_slide_seller", table_name="consultant_training_material_slide_progress")
    op.drop_index("ix_consultant_training_slide_progress_material_seller", table_name="consultant_training_material_slide_progress")
    op.drop_table("consultant_training_material_slide_progress")
