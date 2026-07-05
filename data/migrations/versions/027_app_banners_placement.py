"""app banners placement

Revision ID: 027_app_banners_placement
Revises: 026_app_admin_content
Create Date: 2026-03-25 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "027_app_banners_placement"
down_revision = "026_app_admin_content"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_banners",
        sa.Column("placement", sa.String(length=64), nullable=False, server_default="home_hero"),
    )
    op.create_index(
        "ix_app_banners_placement_active_order",
        "app_banners",
        ["placement", "is_active", "sort_order"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_app_banners_placement_active_order", table_name="app_banners")
    op.drop_column("app_banners", "placement")

