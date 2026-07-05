"""add look styling fields

Revision ID: 037_add_look_styling_fields
Revises: 036_add_stylist_chat_messages
Create Date: 2026-05-05 11:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "037_add_look_styling_fields"
down_revision = "036_add_stylist_chat_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("looks", sa.Column("style_dna", sa.String(length=100), nullable=True))
    op.add_column("looks", sa.Column("radical", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("looks", "radical")
    op.drop_column("looks", "style_dna")
