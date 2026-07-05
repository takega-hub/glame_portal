"""consultant training material status history

Revision ID: 057_consultant_training_material_status_history
Revises: 056_consultant_training_material_library
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "057_consultant_training_material_status_history"
down_revision = "056_consultant_training_material_library"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consultant_training_material_status_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultant_training_materials.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_status", sa.String(length=50), nullable=True),
        sa.Column("to_status", sa.String(length=50), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("changed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index(
        "ix_consultant_training_material_status_history_material_created",
        "consultant_training_material_status_history",
        ["material_id", "created_at"],
    )
    op.create_index(
        "ix_consultant_training_material_status_history_to_status",
        "consultant_training_material_status_history",
        ["to_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_consultant_training_material_status_history_to_status", table_name="consultant_training_material_status_history")
    op.drop_index("ix_consultant_training_material_status_history_material_created", table_name="consultant_training_material_status_history")
    op.drop_table("consultant_training_material_status_history")
