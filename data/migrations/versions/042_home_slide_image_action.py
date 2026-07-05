"""add image action to app home slides

Revision ID: 042_home_slide_image_action
Revises: 041_home_slide_title_nullable
Create Date: 2026-05-06 19:45:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "042_home_slide_image_action"
down_revision = "041_home_slide_title_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_home_slides",
        sa.Column("image_action_link", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "app_home_slides",
        sa.Column("image_action_type", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "app_home_slides",
        sa.Column("image_action_payload", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("app_home_slides", "image_action_payload")
    op.drop_column("app_home_slides", "image_action_type")
    op.drop_column("app_home_slides", "image_action_link")
