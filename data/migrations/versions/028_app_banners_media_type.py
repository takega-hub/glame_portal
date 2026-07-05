"""app banners media type

Revision ID: 028_app_banners_media_type
Revises: 027_app_banners_placement
Create Date: 2026-03-25 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "028_app_banners_media_type"
down_revision = "027_app_banners_placement"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_banners",
        sa.Column("media_type", sa.String(length=16), nullable=False, server_default="image"),
    )
    op.add_column(
        "app_banners",
        sa.Column("video_url", sa.String(length=500), nullable=True),
    )
    op.create_index(
        "ix_app_banners_placement_media",
        "app_banners",
        ["placement", "media_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_app_banners_placement_media", table_name="app_banners")
    op.drop_column("app_banners", "video_url")
    op.drop_column("app_banners", "media_type")

