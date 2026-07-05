"""add app store coordinates

Revision ID: 034_add_app_store_coordinates
Revises: 033_add_app_stores
Create Date: 2026-05-02 16:02:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "034_add_app_store_coordinates"
down_revision = "033_add_app_stores"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("app_stores", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("app_stores", sa.Column("longitude", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("app_stores", "longitude")
    op.drop_column("app_stores", "latitude")
