"""Add slide format for consultant training materials."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "059_consultant_training_material_slides"
down_revision = "058_consultant_training_step_materials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consultant_training_material_slides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("material_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultant_training_materials.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("image_prompt", sa.Text(), nullable=True),
        sa.Column("speaker_note", sa.Text(), nullable=True),
        sa.Column("quiz_question", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_consultant_training_material_slides_material_id", "consultant_training_material_slides", ["material_id"])
    op.create_index("ix_consultant_training_material_slides_material_order", "consultant_training_material_slides", ["material_id", "order_index"])
    op.create_index("ix_consultant_training_material_slides_status", "consultant_training_material_slides", ["status"])


def downgrade() -> None:
    op.drop_index("ix_consultant_training_material_slides_status", table_name="consultant_training_material_slides")
    op.drop_index("ix_consultant_training_material_slides_material_order", table_name="consultant_training_material_slides")
    op.drop_index("ix_consultant_training_material_slides_material_id", table_name="consultant_training_material_slides")
    op.drop_table("consultant_training_material_slides")
