"""make app home slide title nullable

Revision ID: 041_home_slide_title_nullable
Revises: 040_add_app_home_slides
Create Date: 2026-05-06 19:10:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "041_home_slide_title_nullable"
down_revision = "040_add_app_home_slides"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "app_home_slides",
        "title",
        existing_type=sa.String(length=255),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "app_home_slides",
        "title",
        existing_type=sa.String(length=255),
        nullable=False,
    )
