"""Add extraction metadata to consultant training materials.

Revision ID: 061_consultant_training_material_extraction_metadata
Revises: 060_consultant_training_slide_progress
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "061_consultant_training_material_extraction_metadata"
down_revision = "060_consultant_training_slide_progress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "consultant_training_materials",
        sa.Column(
            "extraction_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index(
        "ix_consultant_training_materials_extraction_metadata",
        "consultant_training_materials",
        ["extraction_metadata"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_consultant_training_materials_extraction_metadata", table_name="consultant_training_materials")
    op.drop_column("consultant_training_materials", "extraction_metadata")
