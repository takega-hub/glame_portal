"""Route closed Meganom customer requests to MRIYA.

Revision ID: 073_close_meganom_customer_requests
Revises: 072_customer_requests
"""
from alembic import op

revision = "073_close_meganom_customer_requests"
down_revision = "072_customer_requests"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE customer_requests SET physical_store = 'МРИЯ', crm_store = 'YALTA' WHERE upper(coalesce(physical_store, '')) = 'MEGANOM'")
    op.execute("UPDATE users SET preferred_store_name = 'МРИЯ', preferred_store_external_id = NULL WHERE lower(coalesce(preferred_store_name, '')) LIKE '%меганом%' OR upper(coalesce(preferred_store_name, '')) LIKE '%MEGANOM%'")
    op.execute("UPDATE users SET secondary_store_name = 'МРИЯ' WHERE lower(coalesce(secondary_store_name, '')) LIKE '%меганом%' OR upper(coalesce(secondary_store_name, '')) LIKE '%MEGANOM%'")


def downgrade():
    # A closed store reassignment is a business data migration and is not reversible safely.
    pass
