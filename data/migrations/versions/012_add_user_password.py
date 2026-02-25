"""Add password_hash field to users table

Revision ID: 012_add_user_password
Revises: 011_add_stores
Create Date: 2026-01-28 16:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "012_add_user_password"
down_revision = "011_add_stores"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "password_hash")
