"""add sms otp limits fields

Revision ID: 031_add_sms_otp_limits_fields
Revises: 030_add_user_sms_otp_fields
Create Date: 2026-03-25 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "031_add_sms_otp_limits_fields"
down_revision = "030_add_user_sms_otp_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("sms_otp_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("sms_otp_last_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("users", "sms_otp_attempts", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "sms_otp_last_sent_at")
    op.drop_column("users", "sms_otp_attempts")
