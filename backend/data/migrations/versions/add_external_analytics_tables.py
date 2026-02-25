"""Add external analytics tables

Revision ID: add_external_analytics
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_external_analytics'
down_revision = None  # Update this to the previous migration
branch_labels = None
depends_on = None


def upgrade():
    # Create social_media_metrics table
    op.create_table(
        'social_media_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('platform', sa.String(64), nullable=False, index=True),
        sa.Column('metric_type', sa.String(64), nullable=False, index=True),
        sa.Column('post_id', sa.String(255), nullable=True),
        sa.Column('date', sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column('value', sa.Float, nullable=False, default=0.0),
        sa.Column('likes', sa.Integer, nullable=True),
        sa.Column('comments', sa.Integer, nullable=True),
        sa.Column('shares', sa.Integer, nullable=True),
        sa.Column('views', sa.Integer, nullable=True),
        sa.Column('reach', sa.Integer, nullable=True),
        sa.Column('engagement', sa.Float, nullable=True),
        sa.Column('meta_data', postgresql.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    
    # Create indexes for social_media_metrics
    op.create_index('ix_social_media_metrics_platform_date', 'social_media_metrics', ['platform', 'date'])
    op.create_index('ix_social_media_metrics_platform_type', 'social_media_metrics', ['platform', 'metric_type'])
    op.create_index('ix_social_media_metrics_platform_post', 'social_media_metrics', ['platform', 'post_id'])
    
    # Create sales_metrics table
    op.create_table(
        'sales_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('date', sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column('order_id', sa.String(255), nullable=True),
        sa.Column('store_id', postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column('channel', sa.String(64), nullable=True, index=True),
        sa.Column('revenue', sa.Float, nullable=False, default=0.0),
        sa.Column('order_count', sa.Integer, nullable=False, default=0),
        sa.Column('items_sold', sa.Integer, nullable=False, default=0),
        sa.Column('average_order_value', sa.Float, nullable=False, default=0.0),
        sa.Column('returns_count', sa.Integer, nullable=True, default=0),
        sa.Column('returns_amount', sa.Float, nullable=True, default=0.0),
        sa.Column('meta_data', postgresql.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['store_id'], ['stores.id'], ),
    )
    
    # Create indexes for sales_metrics
    op.create_index('ix_sales_metrics_date_channel', 'sales_metrics', ['date', 'channel'])
    op.create_index('ix_sales_metrics_date_store', 'sales_metrics', ['date', 'store_id'])
    op.create_index('ix_sales_metrics_channel_date', 'sales_metrics', ['channel', 'date'])


def downgrade():
    # Drop indexes
    op.drop_index('ix_sales_metrics_channel_date', 'sales_metrics')
    op.drop_index('ix_sales_metrics_date_store', 'sales_metrics')
    op.drop_index('ix_sales_metrics_date_channel', 'sales_metrics')
    op.drop_index('ix_social_media_metrics_platform_post', 'social_media_metrics')
    op.drop_index('ix_social_media_metrics_platform_type', 'social_media_metrics')
    op.drop_index('ix_social_media_metrics_platform_date', 'social_media_metrics')
    
    # Drop tables
    op.drop_table('sales_metrics')
    op.drop_table('social_media_metrics')
