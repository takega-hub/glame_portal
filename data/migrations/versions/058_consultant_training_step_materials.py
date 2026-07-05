"""consultant training step materials

Revision ID: 058_consultant_training_step_materials
Revises: 057_consultant_training_material_status_history
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "058_consultant_training_step_materials"
down_revision = "057_consultant_training_material_status_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consultant_training_step_materials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultant_training_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("module_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultant_training_modules.id", ondelete="CASCADE"), nullable=True),
        sa.Column("step_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultant_training_steps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultant_training_materials.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=80), nullable=False, server_default="primary_lesson"),
        sa.Column("required_to_complete", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("meta", postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("step_id", "material_id", "role", name="uq_consultant_training_step_material_role"),
    )
    op.create_index("ix_consultant_training_step_materials_step_order", "consultant_training_step_materials", ["step_id", "order_index"])
    op.create_index("ix_consultant_training_step_materials_program", "consultant_training_step_materials", ["program_id"])
    op.create_index("ix_consultant_training_step_materials_material", "consultant_training_step_materials", ["material_id"])


def downgrade() -> None:
    op.drop_index("ix_consultant_training_step_materials_material", table_name="consultant_training_step_materials")
    op.drop_index("ix_consultant_training_step_materials_program", table_name="consultant_training_step_materials")
    op.drop_index("ix_consultant_training_step_materials_step_order", table_name="consultant_training_step_materials")
    op.drop_table("consultant_training_step_materials")
