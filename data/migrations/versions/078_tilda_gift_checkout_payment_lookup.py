"""Index YooKassa payment lookup for Tilda certificate checkout callbacks.

Revision ID: 078_tilda_gift_checkout_payment_lookup
Revises: 077_tilda_gift_certificate_operations
Create Date: 2026-09-30
"""

from alembic import op


revision = "078_tilda_gift_checkout_payment_lookup"
down_revision = "077_tilda_gift_certificate_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_tilda_gift_certificate_operations_payment_id",
        "tilda_gift_certificate_operations",
        ["payment_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tilda_gift_certificate_operations_payment_id",
        table_name="tilda_gift_certificate_operations",
    )
