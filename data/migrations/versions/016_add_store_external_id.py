"""add store external_id

Revision ID: 016_add_store_external_id
Revises: 015_add_sales_records
Create Date: 2025-01-29 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '016_add_store_external_id'
down_revision = '015_add_sales_records'
branch_labels = None
depends_on = None


def upgrade():
    # Добавляем поле external_id для связи с 1С
    op.add_column('stores', sa.Column('external_id', sa.String(255), nullable=True))
    
    # Создаем индекс для быстрого поиска
    op.create_index('ix_stores_external_id', 'stores', ['external_id'])


def downgrade():
    # Удаляем индекс
    op.drop_index('ix_stores_external_id', table_name='stores')
    
    # Удаляем поле
    op.drop_column('stores', 'external_id')
