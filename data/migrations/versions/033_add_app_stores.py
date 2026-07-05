"""add app stores

Revision ID: 033_add_app_stores
Revises: 032_add_look_feed_fields
Create Date: 2026-05-02 14:05:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "033_add_app_stores"
down_revision = "032_add_look_feed_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_stores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("city", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("address", sa.String(length=500), nullable=False),
        sa.Column("working_hours", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=80), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_app_stores_active_order", "app_stores", ["is_active", "sort_order"], unique=False)
    op.create_index("ix_app_stores_updated_at", "app_stores", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_app_stores_updated_at", table_name="app_stores")
    op.drop_index("ix_app_stores_active_order", table_name="app_stores")
    op.drop_table("app_stores")
