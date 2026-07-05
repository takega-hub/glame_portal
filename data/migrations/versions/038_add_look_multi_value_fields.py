"""add look multi value fields

Revision ID: 038_add_look_multi_value_fields
Revises: 037_add_look_styling_fields
Create Date: 2026-05-05 13:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "038_add_look_multi_value_fields"
down_revision = "037_add_look_styling_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("looks", sa.Column("style_values", sa.JSON(), nullable=True))
    op.add_column("looks", sa.Column("mood_values", sa.JSON(), nullable=True))
    op.add_column("looks", sa.Column("style_dna_values", sa.JSON(), nullable=True))
    op.add_column("looks", sa.Column("radical_values", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("looks", "radical_values")
    op.drop_column("looks", "style_dna_values")
    op.drop_column("looks", "mood_values")
    op.drop_column("looks", "style_values")
