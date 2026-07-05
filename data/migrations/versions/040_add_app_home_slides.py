"""add app home slides

Revision ID: 040_add_app_home_slides
Revises: 039_add_app_store_image_urls
Create Date: 2026-05-06 16:20:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "040_add_app_home_slides"
down_revision = "039_add_app_store_image_urls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_home_slides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("block_key", sa.String(length=64), nullable=False, server_default="style_inside"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("subtitle", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=False),
        sa.Column("primary_button_text", sa.String(length=120), nullable=True),
        sa.Column("primary_button_link", sa.String(length=500), nullable=True),
        sa.Column("primary_button_action_type", sa.String(length=32), nullable=True),
        sa.Column("primary_button_action_payload", sa.JSON(), nullable=True),
        sa.Column("secondary_button_text", sa.String(length=120), nullable=True),
        sa.Column("secondary_button_link", sa.String(length=500), nullable=True),
        sa.Column("secondary_button_action_type", sa.String(length=32), nullable=True),
        sa.Column("secondary_button_action_payload", sa.JSON(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index(
        "ix_app_home_slides_block_active_order",
        "app_home_slides",
        ["block_key", "is_active", "sort_order"],
        unique=False,
    )
    op.create_index("ix_app_home_slides_updated_at", "app_home_slides", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_app_home_slides_updated_at", table_name="app_home_slides")
    op.drop_index("ix_app_home_slides_block_active_order", table_name="app_home_slides")
    op.drop_table("app_home_slides")
