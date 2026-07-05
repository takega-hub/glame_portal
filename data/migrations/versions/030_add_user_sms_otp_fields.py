"""add sms otp fields to users

Revision ID: 030_add_user_sms_otp_fields
Revises: 029_ecommerce_orders_payments
Create Date: 2026-03-25 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "030_add_user_sms_otp_fields"
down_revision = "029_ecommerce_orders_payments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("sms_otp_code", sa.String(length=4), nullable=True))
    op.add_column("users", sa.Column("sms_otp_expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "sms_otp_expires_at")
    op.drop_column("users", "sms_otp_code")
