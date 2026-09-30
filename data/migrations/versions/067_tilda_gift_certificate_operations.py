"""Add the idempotent Tilda gift-certificate operation journal.

Revision ID: 067_tilda_gift_certificate_operations
Revises: 066_glame_token_bridge_operations
Create Date: 2026-09-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "067_tilda_gift_certificate_operations"
down_revision = "066_glame_token_bridge_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tilda_gift_certificate_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("certificate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("sync_status", sa.String(length=32), nullable=False, server_default="synced"),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("request_hash", sa.String(length=64), nullable=True),
        sa.Column("validation_token_hash", sa.String(length=64), nullable=True),
        sa.Column("tilda_order_id", sa.String(length=128), nullable=True),
        sa.Column("payment_id", sa.String(length=128), nullable=True),
        sa.Column("refund_id", sa.String(length=128), nullable=True),
        sa.Column("original_operation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cart_total", sa.Integer(), nullable=True),
        sa.Column("cart_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("reservation_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("onec_document_id", sa.String(length=128), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["certificate_id"], ["gift_certificates.id"]),
        sa.ForeignKeyConstraint(["original_operation_id"], ["tilda_gift_certificate_operations.id"]),
        sa.UniqueConstraint("tilda_order_id", "operation_type", name="uq_tilda_gift_operation_order_type"),
    )
    op.create_index("ix_tilda_gift_certificate_operations_certificate_id", "tilda_gift_certificate_operations", ["certificate_id"])
    op.create_index("ix_tilda_gift_certificate_operations_operation_type", "tilda_gift_certificate_operations", ["operation_type"])
    op.create_index("ix_tilda_gift_certificate_operations_status", "tilda_gift_certificate_operations", ["status"])
    op.create_index("ix_tilda_gift_certificate_operations_sync_status", "tilda_gift_certificate_operations", ["sync_status"])
    op.create_index("ix_tilda_gift_certificate_operations_idempotency_key", "tilda_gift_certificate_operations", ["idempotency_key"], unique=True)
    op.create_index("ix_tilda_gift_certificate_operations_validation_token_hash", "tilda_gift_certificate_operations", ["validation_token_hash"], unique=True)
    op.create_index("ix_tilda_gift_certificate_operations_tilda_order_id", "tilda_gift_certificate_operations", ["tilda_order_id"])
    op.create_index("ix_tilda_gift_certificate_operations_refund_id", "tilda_gift_certificate_operations", ["refund_id"])
    op.create_index("ix_tilda_gift_certificate_operations_reservation_expires_at", "tilda_gift_certificate_operations", ["reservation_expires_at"])
    op.create_index("ix_tilda_gift_operations_sync_created", "tilda_gift_certificate_operations", ["sync_status", "created_at"])
    op.create_index("ix_tilda_gift_operations_certificate_type", "tilda_gift_certificate_operations", ["certificate_id", "operation_type"])
    op.alter_column("tilda_gift_certificate_operations", "sync_status", server_default=None)
    op.alter_column("tilda_gift_certificate_operations", "amount", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_tilda_gift_operations_certificate_type", table_name="tilda_gift_certificate_operations")
    op.drop_index("ix_tilda_gift_operations_sync_created", table_name="tilda_gift_certificate_operations")
    op.drop_index("ix_tilda_gift_certificate_operations_reservation_expires_at", table_name="tilda_gift_certificate_operations")
    op.drop_index("ix_tilda_gift_certificate_operations_refund_id", table_name="tilda_gift_certificate_operations")
    op.drop_index("ix_tilda_gift_certificate_operations_tilda_order_id", table_name="tilda_gift_certificate_operations")
    op.drop_index("ix_tilda_gift_certificate_operations_validation_token_hash", table_name="tilda_gift_certificate_operations")
    op.drop_index("ix_tilda_gift_certificate_operations_idempotency_key", table_name="tilda_gift_certificate_operations")
    op.drop_index("ix_tilda_gift_certificate_operations_sync_status", table_name="tilda_gift_certificate_operations")
    op.drop_index("ix_tilda_gift_certificate_operations_status", table_name="tilda_gift_certificate_operations")
    op.drop_index("ix_tilda_gift_certificate_operations_operation_type", table_name="tilda_gift_certificate_operations")
    op.drop_index("ix_tilda_gift_certificate_operations_certificate_id", table_name="tilda_gift_certificate_operations")
    op.drop_table("tilda_gift_certificate_operations")
