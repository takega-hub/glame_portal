"""add sales records

Revision ID: 015_add_sales_records
Revises: 014_add_marketing_campaigns
Create Date: 2025-01-29 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '015_add_sales_records'
down_revision = '014_add_marketing_campaigns'
branch_labels = None
depends_on = None


def upgrade():
    # Создание таблицы sales_records
    op.create_table(
        'sales_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sale_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('external_id', sa.String(255), nullable=True),
        sa.Column('document_id', sa.String(255), nullable=True),
        sa.Column('store_id', sa.String(255), nullable=True),
        sa.Column('customer_id', sa.String(255), nullable=True),
        sa.Column('product_id', sa.String(255), nullable=True),
        sa.Column('organization_id', sa.String(255), nullable=True),
        sa.Column('revenue', sa.Float(), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('revenue_without_discount', sa.Float(), nullable=True),
        sa.Column('channel', sa.String(64), nullable=True),
        sa.Column('raw_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('synced_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('sync_batch_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Создание индексов
    op.create_index('ix_sales_records_sale_date', 'sales_records', ['sale_date'])
    op.create_index('ix_sales_records_external_id', 'sales_records', ['external_id'], unique=True)
    op.create_index('ix_sales_records_document_id', 'sales_records', ['document_id'])
    op.create_index('ix_sales_records_store_id', 'sales_records', ['store_id'])
    op.create_index('ix_sales_records_customer_id', 'sales_records', ['customer_id'])
    op.create_index('ix_sales_records_product_id', 'sales_records', ['product_id'])
    op.create_index('ix_sales_records_synced_at', 'sales_records', ['synced_at'])
    op.create_index('ix_sales_records_sync_batch_id', 'sales_records', ['sync_batch_id'])
    op.create_index('ix_sales_records_date_store', 'sales_records', ['sale_date', 'store_id'])
    op.create_index('ix_sales_records_date_customer', 'sales_records', ['sale_date', 'customer_id'])
    op.create_index('ix_sales_records_date_product', 'sales_records', ['sale_date', 'product_id'])


def downgrade():
    # Удаление индексов
    op.drop_index('ix_sales_records_date_product', table_name='sales_records')
    op.drop_index('ix_sales_records_date_customer', table_name='sales_records')
    op.drop_index('ix_sales_records_date_store', table_name='sales_records')
    op.drop_index('ix_sales_records_sync_batch_id', table_name='sales_records')
    op.drop_index('ix_sales_records_synced_at', table_name='sales_records')
    op.drop_index('ix_sales_records_product_id', table_name='sales_records')
    op.drop_index('ix_sales_records_customer_id', table_name='sales_records')
    op.drop_index('ix_sales_records_store_id', table_name='sales_records')
    op.drop_index('ix_sales_records_document_id', table_name='sales_records')
    op.drop_index('ix_sales_records_external_id', table_name='sales_records')
    op.drop_index('ix_sales_records_sale_date', table_name='sales_records')
    
    # Удаление таблицы
    op.drop_table('sales_records')
