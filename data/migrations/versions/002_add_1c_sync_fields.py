"""Add 1C sync fields to products

Revision ID: 002_add_1c_sync
Revises: 001_initial
Create Date: 2024-01-15 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_add_1c_sync'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавляем поля для интеграции с 1С
    op.add_column('products', sa.Column('external_id', sa.String(255), nullable=True))
    op.add_column('products', sa.Column('external_code', sa.String(100), nullable=True))
    op.add_column('products', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('products', sa.Column('sync_status', sa.String(50), nullable=True))
    op.add_column('products', sa.Column('sync_metadata', postgresql.JSON, nullable=True))
    
    # Создаем индексы для быстрого поиска
    op.create_index('ix_products_external_id', 'products', ['external_id'], unique=True)
    op.create_index('ix_products_external_code', 'products', ['external_code'])


def downgrade() -> None:
    # Удаляем индексы
    op.drop_index('ix_products_external_code', table_name='products')
    op.drop_index('ix_products_external_id', table_name='products')
    
    # Удаляем колонки
    op.drop_column('products', 'sync_metadata')
    op.drop_column('products', 'sync_status')
    op.drop_column('products', 'is_active')
    op.drop_column('products', 'external_code')
    op.drop_column('products', 'external_id')
