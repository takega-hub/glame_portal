"""Add app_settings table for runtime configuration (e.g., OpenRouter model)

Revision ID: 005_add_app_settings
Revises: 004_add_content_tables
Create Date: 2026-01-28 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "005_add_app_settings"
down_revision = "004_add_content_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=100), primary_key=True),
        sa.Column("value", sa.String(length=500), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("app_settings")

