"""add live stylist conversations

Revision ID: 045_live_stylist_conversations
Revises: 044_home_slide_background_image
Create Date: 2026-05-13 11:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "045_live_stylist_conversations"
down_revision = "044_home_slide_background_image"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "live_stylist_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assigned_stylist_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("scenario", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="requested"),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="normal"),
        sa.Column("initial_working_hours_status", sa.String(length=16), nullable=True),
        sa.Column("unread_for_stylist_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unread_for_customer_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "recommended_product_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("internal_notes", sa.Text(), nullable=True),
        sa.Column("result_purchase_status", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("result_order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("result_notes", sa.Text(), nullable=True),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_response_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_customer_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_stylist_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["customer_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["assigned_stylist_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_live_stylist_conversations_customer_user_id",
        "live_stylist_conversations",
        ["customer_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_live_stylist_conversations_assigned_stylist_user_id",
        "live_stylist_conversations",
        ["assigned_stylist_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_live_stylist_conversations_status",
        "live_stylist_conversations",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_live_stylist_conversations_priority",
        "live_stylist_conversations",
        ["priority"],
        unique=False,
    )
    op.create_index(
        "ix_live_stylist_conversations_result_purchase_status",
        "live_stylist_conversations",
        ["result_purchase_status"],
        unique=False,
    )
    op.create_index(
        "ix_live_stylist_customer_status",
        "live_stylist_conversations",
        ["customer_user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_live_stylist_assigned_status",
        "live_stylist_conversations",
        ["assigned_stylist_user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_live_stylist_last_message",
        "live_stylist_conversations",
        ["last_message_at", "created_at"],
        unique=False,
    )

    op.add_column(
        "stylist_chat_messages",
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "stylist_chat_messages",
        sa.Column("sender_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_stylist_chat_messages_conversation_id",
        "stylist_chat_messages",
        "live_stylist_conversations",
        ["conversation_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_stylist_chat_messages_sender_user_id",
        "stylist_chat_messages",
        "users",
        ["sender_user_id"],
        ["id"],
    )
    op.create_index(
        "ix_stylist_chat_messages_conversation_id",
        "stylist_chat_messages",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylist_chat_messages_sender_user_id",
        "stylist_chat_messages",
        ["sender_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_stylist_chat_conversation_created",
        "stylist_chat_messages",
        ["conversation_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_stylist_chat_conversation_created", table_name="stylist_chat_messages")
    op.drop_index("ix_stylist_chat_messages_sender_user_id", table_name="stylist_chat_messages")
    op.drop_index("ix_stylist_chat_messages_conversation_id", table_name="stylist_chat_messages")
    op.drop_constraint("fk_stylist_chat_messages_sender_user_id", "stylist_chat_messages", type_="foreignkey")
    op.drop_constraint("fk_stylist_chat_messages_conversation_id", "stylist_chat_messages", type_="foreignkey")
    op.drop_column("stylist_chat_messages", "sender_user_id")
    op.drop_column("stylist_chat_messages", "conversation_id")

    op.drop_index("ix_live_stylist_last_message", table_name="live_stylist_conversations")
    op.drop_index("ix_live_stylist_assigned_status", table_name="live_stylist_conversations")
    op.drop_index("ix_live_stylist_customer_status", table_name="live_stylist_conversations")
    op.drop_index("ix_live_stylist_conversations_result_purchase_status", table_name="live_stylist_conversations")
    op.drop_index("ix_live_stylist_conversations_priority", table_name="live_stylist_conversations")
    op.drop_index("ix_live_stylist_conversations_status", table_name="live_stylist_conversations")
    op.drop_index("ix_live_stylist_conversations_assigned_stylist_user_id", table_name="live_stylist_conversations")
    op.drop_index("ix_live_stylist_conversations_customer_user_id", table_name="live_stylist_conversations")
    op.drop_table("live_stylist_conversations")
