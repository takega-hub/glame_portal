"""Widen alembic_version.version_num for long revision IDs (default is 32 chars)

Revision ID: 019_widen_alembic_version
Revises: 019_create_purchase_history
Create Date: 2025-02-25 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '019_widen_alembic_version'
down_revision = '019_create_purchase_history'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Default alembic_version.version_num is VARCHAR(32); our revision IDs are longer
    op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)")


def downgrade() -> None:
    op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(32)")
