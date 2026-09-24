"""Add text color setting to home slides.

Revision ID: 075_home_slide_text_color
Revises: 074_customer_request_photos
"""

from alembic import op
import sqlalchemy as sa


revision = "075_home_slide_text_color"
down_revision = "074_customer_request_photos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_home_slides",
        sa.Column("text_color_hex", sa.String(length=7), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("app_home_slides", "text_color_hex")
