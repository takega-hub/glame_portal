"""app admin content tables

Revision ID: 026_app_admin_content
Revises: 025_inv_snap_period
Create Date: 2026-03-25 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "026_app_admin_content"
down_revision = "025_inv_snap_period"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_banners",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("image_url", sa.String(length=500), nullable=False),
        sa.Column("link_url", sa.String(length=500), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_app_banners_active_order", "app_banners", ["is_active", "sort_order"], unique=False)
    op.create_index("ix_app_banners_updated_at", "app_banners", ["updated_at"], unique=False)

    op.create_table(
        "app_lookbooks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("cover_image_url", sa.String(length=500), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("items", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_app_lookbooks_published", "app_lookbooks", ["is_published"], unique=False)
    op.create_index("ix_app_lookbooks_updated_at", "app_lookbooks", ["updated_at"], unique=False)

    op.create_table(
        "app_promotions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("banner_image_url", sa.String(length=500), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_app_promotions_status", "app_promotions", ["status"], unique=False)
    op.create_index("ix_app_promotions_updated_at", "app_promotions", ["updated_at"], unique=False)

    op.create_table(
        "app_news",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("preview_image_url", sa.String(length=500), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_app_news_status", "app_news", ["status"], unique=False)
    op.create_index("ix_app_news_published_at", "app_news", ["published_at"], unique=False)
    op.create_index("ix_app_news_updated_at", "app_news", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_app_news_updated_at", table_name="app_news")
    op.drop_index("ix_app_news_published_at", table_name="app_news")
    op.drop_index("ix_app_news_status", table_name="app_news")
    op.drop_table("app_news")

    op.drop_index("ix_app_promotions_updated_at", table_name="app_promotions")
    op.drop_index("ix_app_promotions_status", table_name="app_promotions")
    op.drop_table("app_promotions")

    op.drop_index("ix_app_lookbooks_updated_at", table_name="app_lookbooks")
    op.drop_index("ix_app_lookbooks_published", table_name="app_lookbooks")
    op.drop_table("app_lookbooks")

    op.drop_index("ix_app_banners_updated_at", table_name="app_banners")
    op.drop_index("ix_app_banners_active_order", table_name="app_banners")
    op.drop_table("app_banners")

