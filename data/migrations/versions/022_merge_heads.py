"""Merge multiple heads (017_add_catalog_sections and 021_add_user_city)

Revision ID: 022_merge_heads
Revises: 017_add_catalog_sections, 021_add_user_city
Create Date: 2025-02-25 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '022_merge_heads'
down_revision = ('017_add_catalog_sections', '021_add_user_city')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
