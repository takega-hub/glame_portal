"""consultant training mentor messages

Revision ID: 053_consultant_training_mentor_messages
Revises: 052_consultant_training_attestations
Create Date: 2026-06-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "053_consultant_training_mentor_messages"
down_revision = "052_consultant_training_attestations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consultant_training_mentor_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("seller_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultant_training_programs.id", ondelete="CASCADE"), nullable=True),
        sa.Column("step_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("consultant_training_steps.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sender_role", sa.String(length=20), nullable=False, server_default="mentor"),
        sa.Column("question_text", sa.Text(), nullable=True),
        sa.Column("response_text", sa.Text(), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("risk_flags", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_consultant_training_mentor_messages_seller_created", "consultant_training_mentor_messages", ["seller_user_id", "created_at"])
    op.create_index("ix_consultant_training_mentor_messages_program_id", "consultant_training_mentor_messages", ["program_id"])
    op.create_index("ix_consultant_training_mentor_messages_step_id", "consultant_training_mentor_messages", ["step_id"])


def downgrade() -> None:
    op.drop_index("ix_consultant_training_mentor_messages_step_id", table_name="consultant_training_mentor_messages")
    op.drop_index("ix_consultant_training_mentor_messages_program_id", table_name="consultant_training_mentor_messages")
    op.drop_index("ix_consultant_training_mentor_messages_seller_created", table_name="consultant_training_mentor_messages")
    op.drop_table("consultant_training_mentor_messages")
