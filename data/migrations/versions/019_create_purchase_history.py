"""Create purchase_history table (was missing from initial migrations)

Revision ID: 019_create_purchase_history
Revises: 019_add_product_stocks
Create Date: 2025-02-25 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '019_create_purchase_history'
down_revision = '019_add_product_stocks'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'purchase_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('purchase_date', sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column('document_id_1c', sa.String(255), nullable=True),
        sa.Column('store_id_1c', sa.String(255), nullable=True),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('products.id'), nullable=True, index=True),
        sa.Column('product_id_1c', sa.String(255), nullable=True),
        sa.Column('product_name', sa.String(500), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('price', sa.Integer(), nullable=True),
        sa.Column('total_amount', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('brand', sa.String(100), nullable=True),
        sa.Column('sync_metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_purchase_history_user_date', 'purchase_history', ['user_id', 'purchase_date'])
    op.create_index('ix_purchase_history_document_1c', 'purchase_history', ['document_id_1c'])
    op.create_index('ix_purchase_history_product_1c', 'purchase_history', ['product_id_1c'])


def downgrade() -> None:
    op.drop_index('ix_purchase_history_product_1c', table_name='purchase_history')
    op.drop_index('ix_purchase_history_document_1c', table_name='purchase_history')
    op.drop_index('ix_purchase_history_user_date', table_name='purchase_history')
    op.drop_table('purchase_history')
