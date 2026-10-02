"""Add public Tilda gift-certificate purchase journal.

Revision ID: 079_tilda_gift_certificate_purchases
Revises: 078_tilda_gift_checkout_payment_lookup
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "079_tilda_gift_certificate_purchases"
down_revision = "078_tilda_gift_checkout_payment_lookup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tilda_gift_certificate_purchases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status_token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("nominal_amount", sa.Integer(), nullable=False),
        sa.Column("design", sa.String(32), nullable=False),
        sa.Column("recipient_name", sa.String(80), nullable=False),
        sa.Column("recipient_email", sa.String(255), nullable=False),
        sa.Column("sender_name", sa.String(80), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("delivery_mode", sa.String(16), nullable=False),
        sa.Column("send_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("buyer_contact", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("return_url", sa.String(2000), nullable=False),
        sa.Column("payment_id", sa.String(128), nullable=True, unique=True),
        sa.Column("confirmation_url", sa.String(2000), nullable=True),
        sa.Column("certificate_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    for name, cols in (("status", ["status"]), ("send_at", ["send_at"]), ("payment_id", ["payment_id"]), ("certificate_id", ["certificate_id"]), ("created_at", ["created_at"])):
        op.create_index(f"ix_tilda_gift_certificate_purchases_{name}", "tilda_gift_certificate_purchases", cols)


def downgrade() -> None:
    op.drop_table("tilda_gift_certificate_purchases")
