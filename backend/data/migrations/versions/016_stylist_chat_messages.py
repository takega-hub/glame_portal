"""Create stylist chat messages table

Revision ID: 016_stylist_chat_messages
Revises: 015_soft_delete_agent_tasks
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "016_stylist_chat_messages"
down_revision = "015_soft_delete_agent_tasks"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "stylist_chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=24), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("attachments", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_stylist_chat_messages_user_id", "stylist_chat_messages", ["user_id"])
    op.create_index("ix_stylist_chat_messages_role", "stylist_chat_messages", ["role"])
    op.create_index("ix_stylist_chat_messages_created_at", "stylist_chat_messages", ["created_at"])
    op.create_index("ix_stylist_chat_user_created", "stylist_chat_messages", ["user_id", "created_at"])


def downgrade():
    op.drop_index("ix_stylist_chat_user_created", table_name="stylist_chat_messages")
    op.drop_index("ix_stylist_chat_messages_created_at", table_name="stylist_chat_messages")
    op.drop_index("ix_stylist_chat_messages_role", table_name="stylist_chat_messages")
    op.drop_index("ix_stylist_chat_messages_user_id", table_name="stylist_chat_messages")
    op.drop_table("stylist_chat_messages")
