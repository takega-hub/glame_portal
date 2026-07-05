"""add live stylist audit events

Revision ID: 046_live_stylist_audit_events
Revises: 045_live_stylist_conversations
Create Date: 2026-05-13 13:40:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "046_live_stylist_audit_events"
down_revision = "045_live_stylist_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "live_stylist_conversation_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["conversation_id"], ["live_stylist_conversations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_live_stylist_conversation_events_conversation_id",
        "live_stylist_conversation_events",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        "ix_live_stylist_conversation_events_actor_user_id",
        "live_stylist_conversation_events",
        ["actor_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_live_stylist_conversation_events_event_type",
        "live_stylist_conversation_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        "ix_live_stylist_conversation_events_created_at",
        "live_stylist_conversation_events",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_live_stylist_event_conversation_created",
        "live_stylist_conversation_events",
        ["conversation_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_live_stylist_event_conversation_created", table_name="live_stylist_conversation_events")
    op.drop_index("ix_live_stylist_conversation_events_created_at", table_name="live_stylist_conversation_events")
    op.drop_index("ix_live_stylist_conversation_events_event_type", table_name="live_stylist_conversation_events")
    op.drop_index("ix_live_stylist_conversation_events_actor_user_id", table_name="live_stylist_conversation_events")
    op.drop_index("ix_live_stylist_conversation_events_conversation_id", table_name="live_stylist_conversation_events")
    op.drop_table("live_stylist_conversation_events")
