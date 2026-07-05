"""Gift certificates.

Revision ID: 062_gift_certificates
Revises: 061_consultant_training_material_extraction_metadata
Create Date: 2026-06-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "062_gift_certificates"
down_revision = "061_consultant_training_material_extraction_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gift_certificates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("number", sa.String(length=32), nullable=False),
        sa.Column("pin_hash", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="RUB"),
        sa.Column("nominal_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("balance_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserved_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("buyer_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("recipient_name", sa.String(length=255), nullable=True),
        sa.Column("recipient_phone", sa.String(length=32), nullable=True),
        sa.Column("recipient_email", sa.String(length=255), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("onec_certificate_id", sa.String(length=128), nullable=True),
        sa.Column("onec_sale_document_id", sa.String(length=128), nullable=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_gift_certificates_number", "gift_certificates", ["number"], unique=True)
    op.create_index("ix_gift_certificates_status", "gift_certificates", ["status"], unique=False)
    op.create_index("ix_gift_certificates_buyer_user_id", "gift_certificates", ["buyer_user_id"], unique=False)
    op.create_index("ix_gift_certificates_order_id", "gift_certificates", ["order_id"], unique=False)
    op.create_index("ix_gift_certificates_payment_id", "gift_certificates", ["payment_id"], unique=False)
    op.create_index("ix_gift_certificates_created_at", "gift_certificates", ["created_at"], unique=False)
    op.create_index("ix_gift_certificates_buyer_status", "gift_certificates", ["buyer_user_id", "status"], unique=False)
    op.create_index("ix_gift_certificates_order_status", "gift_certificates", ["order_id", "status"], unique=False)

    op.create_table(
        "gift_certificate_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("certificate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transaction_type", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("balance_after", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserved_after", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column("external_operation_id", sa.String(length=128), nullable=True),
        sa.Column("onec_document_id", sa.String(length=128), nullable=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_gift_certificate_transactions_certificate_id", "gift_certificate_transactions", ["certificate_id"], unique=False)
    op.create_index("ix_gift_certificate_transactions_transaction_type", "gift_certificate_transactions", ["transaction_type"], unique=False)
    op.create_index("ix_gift_certificate_transactions_order_id", "gift_certificate_transactions", ["order_id"], unique=False)
    op.create_index("ix_gift_certificate_transactions_store_id", "gift_certificate_transactions", ["store_id"], unique=False)
    op.create_index("ix_gift_certificate_transactions_created_at", "gift_certificate_transactions", ["created_at"], unique=False)
    op.create_index("ix_gift_certificate_transactions_cert_date", "gift_certificate_transactions", ["certificate_id", "created_at"], unique=False)
    op.create_index("ix_gift_certificate_transactions_external", "gift_certificate_transactions", ["source", "external_operation_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_gift_certificate_transactions_external", table_name="gift_certificate_transactions")
    op.drop_index("ix_gift_certificate_transactions_cert_date", table_name="gift_certificate_transactions")
    op.drop_index("ix_gift_certificate_transactions_created_at", table_name="gift_certificate_transactions")
    op.drop_index("ix_gift_certificate_transactions_store_id", table_name="gift_certificate_transactions")
    op.drop_index("ix_gift_certificate_transactions_order_id", table_name="gift_certificate_transactions")
    op.drop_index("ix_gift_certificate_transactions_transaction_type", table_name="gift_certificate_transactions")
    op.drop_index("ix_gift_certificate_transactions_certificate_id", table_name="gift_certificate_transactions")
    op.drop_table("gift_certificate_transactions")
    op.drop_index("ix_gift_certificates_order_status", table_name="gift_certificates")
    op.drop_index("ix_gift_certificates_buyer_status", table_name="gift_certificates")
    op.drop_index("ix_gift_certificates_created_at", table_name="gift_certificates")
    op.drop_index("ix_gift_certificates_payment_id", table_name="gift_certificates")
    op.drop_index("ix_gift_certificates_order_id", table_name="gift_certificates")
    op.drop_index("ix_gift_certificates_buyer_user_id", table_name="gift_certificates")
    op.drop_index("ix_gift_certificates_status", table_name="gift_certificates")
    op.drop_index("ix_gift_certificates_number", table_name="gift_certificates")
    op.drop_table("gift_certificates")
