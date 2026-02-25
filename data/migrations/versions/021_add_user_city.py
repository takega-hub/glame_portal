"""add city to users

Revision ID: 021_add_user_city
Revises: 020_add_product_article_to_purchases
Create Date: 2025-01-29 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '021_add_user_city'
down_revision = '020_add_product_article_to_purchases'
branch_labels = None
depends_on = None


def upgrade():
    # Добавляем поле city в users
    op.add_column('users', sa.Column('city', sa.String(100), nullable=True))


def downgrade():
    # Удаляем поле
    op.drop_column('users', 'city')
