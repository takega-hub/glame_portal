"""Add catalog_sections table

Revision ID: 017_add_catalog_sections
Revises: 016_add_store_external_id
Create Date: 2024-01-15 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '017_add_catalog_sections'
down_revision = '016_add_store_external_id'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create catalog_sections table
    op.create_table(
        'catalog_sections',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('external_id', sa.String(255), nullable=False, unique=True),
        sa.Column('external_code', sa.String(100), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('parent_external_id', sa.String(255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('onec_metadata', postgresql.JSONB, nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('sync_status', sa.String(50), nullable=True),
        sa.Column('sync_metadata', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    
    # Create indexes
    op.create_index('ix_catalog_sections_external_id', 'catalog_sections', ['external_id'])
    op.create_index('ix_catalog_sections_external_code', 'catalog_sections', ['external_code'])
    op.create_index('ix_catalog_sections_parent_external_id', 'catalog_sections', ['parent_external_id'])
    op.create_index('ix_catalog_sections_is_active', 'catalog_sections', ['is_active'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_catalog_sections_is_active', table_name='catalog_sections')
    op.drop_index('ix_catalog_sections_parent_external_id', table_name='catalog_sections')
    op.drop_index('ix_catalog_sections_external_code', table_name='catalog_sections')
    op.drop_index('ix_catalog_sections_external_id', table_name='catalog_sections')
    
    # Drop table
    op.drop_table('catalog_sections')
