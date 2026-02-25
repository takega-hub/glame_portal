"""add product_article to purchase_history

Revision ID: 020_add_product_article_to_purchases
Revises: 019_add_product_stocks
Create Date: 2025-01-29 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '020_add_product_article_to_purchases'
down_revision = '019_add_product_stocks'
branch_labels = None
depends_on = None


def upgrade():
    # Добавляем поле product_article в purchase_history
    op.add_column('purchase_history', sa.Column('product_article', sa.String(100), nullable=True))
    
    # Создаем индекс для быстрого поиска по артикулу
    op.create_index('ix_purchase_history_product_article', 'purchase_history', ['product_article'])
    
    # Добавляем индекс для product_id, если его еще нет
    try:
        op.create_index('ix_purchase_history_product_id', 'purchase_history', ['product_id'])
    except:
        pass  # Индекс уже существует


def downgrade():
    # Удаляем индекс
    op.drop_index('ix_purchase_history_product_article', table_name='purchase_history')
    
    # Удаляем поле
    op.drop_column('purchase_history', 'product_article')
