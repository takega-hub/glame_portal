"""Link gift certificates to recipient users.

Revision ID: 063_gift_certificate_recipient_user
Revises: 062_gift_certificates
Create Date: 2026-06-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "063_gift_certificate_recipient_user"
down_revision = "062_gift_certificates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "gift_certificates",
        sa.Column("recipient_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_gift_certificates_recipient_user_id",
        "gift_certificates",
        ["recipient_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_gift_certificates_recipient_status",
        "gift_certificates",
        ["recipient_user_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_gift_certificates_recipient_status", table_name="gift_certificates")
    op.drop_index("ix_gift_certificates_recipient_user_id", table_name="gift_certificates")
    op.drop_column("gift_certificates", "recipient_user_id")
