"""Add selectable background mode to home slides

Revision ID: 018_home_slide_background_mode
Revises: 017_glm_treasury_refill_checks
"""

from alembic import op
import sqlalchemy as sa


revision = "018_home_slide_background_mode"
down_revision = "017_glm_treasury_refill_checks"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "app_home_slides",
        sa.Column(
            "background_mode",
            sa.String(length=16),
            nullable=False,
            server_default="image",
        ),
    )
    op.add_column(
        "app_home_slides",
        sa.Column("background_color_hex", sa.String(length=7), nullable=True),
    )
    op.add_column(
        "app_home_slides",
        sa.Column("background_color_ral", sa.String(length=32), nullable=True),
    )
    op.alter_column("app_home_slides", "background_mode", server_default=None)


def downgrade():
    op.drop_column("app_home_slides", "background_color_ral")
    op.drop_column("app_home_slides", "background_color_hex")
    op.drop_column("app_home_slides", "background_mode")
