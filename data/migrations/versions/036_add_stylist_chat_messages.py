"""add stylist chat messages

Revision ID: 036_add_stylist_chat_messages
Revises: 035_admin_role_access
Create Date: 2026-05-04 10:20:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "036_add_stylist_chat_messages"
down_revision = "035_admin_role_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stylist_chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=24), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column(
            "attachments",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_stylist_chat_messages_user_id",
        "stylist_chat_messages",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylist_chat_messages_role",
        "stylist_chat_messages",
        ["role"],
        unique=False,
    )
    op.create_index(
        "ix_stylist_chat_messages_created_at",
        "stylist_chat_messages",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_stylist_chat_user_created",
        "stylist_chat_messages",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_stylist_chat_user_created", table_name="stylist_chat_messages")
    op.drop_index("ix_stylist_chat_messages_created_at", table_name="stylist_chat_messages")
    op.drop_index("ix_stylist_chat_messages_role", table_name="stylist_chat_messages")
    op.drop_index("ix_stylist_chat_messages_user_id", table_name="stylist_chat_messages")
    op.drop_table("stylist_chat_messages")
