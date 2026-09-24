"""Add customer-request photo attachments.

Revision ID: 074_customer_request_photos
Revises: 073_close_meganom_customer_requests
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "074_customer_request_photos"
down_revision = "073_close_meganom_customer_requests"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "customer_requests",
        sa.Column("photo_urls", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.alter_column("customer_requests", "photo_urls", server_default=None)


def downgrade():
    op.drop_column("customer_requests", "photo_urls")
