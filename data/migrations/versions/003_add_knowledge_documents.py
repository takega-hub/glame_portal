"""Add knowledge_documents table

Revision ID: 003_knowledge_documents
Revises: 002_add_1c_sync
Create Date: 2024-01-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003_knowledge_documents'
down_revision = '002_add_1c_sync'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create knowledge_documents table
    op.create_table(
        'knowledge_documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('file_type', sa.String(50), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(255), nullable=True),
        sa.Column('total_items', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('uploaded_items', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_items', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('vector_document_ids', postgresql.JSON, nullable=True),
        sa.Column('document_metadata', postgresql.JSON, nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='completed'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    
    # Create indexes
    op.create_index('ix_knowledge_documents_filename', 'knowledge_documents', ['filename'])
    op.create_index('ix_knowledge_documents_status', 'knowledge_documents', ['status'])
    op.create_index('ix_knowledge_documents_created_at', 'knowledge_documents', ['created_at'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_knowledge_documents_created_at', table_name='knowledge_documents')
    op.drop_index('ix_knowledge_documents_status', table_name='knowledge_documents')
    op.drop_index('ix_knowledge_documents_filename', table_name='knowledge_documents')
    
    # Drop table
    op.drop_table('knowledge_documents')
