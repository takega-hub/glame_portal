"""Create GLM treasury refill check journal

Revision ID: 017_glm_treasury_refill_checks
Revises: 016_stylist_chat_messages
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "017_glm_treasury_refill_checks"
down_revision = "016_stylist_chat_messages"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "glame_treasury_refill_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(length=32), nullable=False, server_default="balance_check"),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column("network", sa.String(length=32), nullable=True),
        sa.Column("treasury_address", sa.String(length=128), nullable=True),
        sa.Column("hot_wallet_address", sa.String(length=128), nullable=True),
        sa.Column("ton_tx_hash", sa.String(length=128), nullable=True),
        sa.Column("refill_glm_amount", sa.Numeric(20, 9), nullable=True),
        sa.Column("refill_ton_amount", sa.Numeric(20, 9), nullable=True),
        sa.Column("manual_glm_amount", sa.Numeric(20, 9), nullable=True),
        sa.Column("manual_ton_amount", sa.Numeric(20, 9), nullable=True),
        sa.Column("hot_wallet_glm_balance", sa.Numeric(20, 9), nullable=True),
        sa.Column("hot_wallet_ton_balance", sa.Numeric(20, 9), nullable=True),
        sa.Column("treasury_glm_balance", sa.Numeric(20, 9), nullable=True),
        sa.Column("treasury_ton_balance", sa.Numeric(20, 9), nullable=True),
        sa.Column("target_glm", sa.Numeric(20, 9), nullable=True),
        sa.Column("target_ton", sa.Numeric(20, 9), nullable=True),
        sa.Column("threshold_glm", sa.Numeric(20, 9), nullable=True),
        sa.Column("threshold_ton", sa.Numeric(20, 9), nullable=True),
        sa.Column("errors", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
    )
    op.create_index("ix_glame_treasury_refill_checks_event_type", "glame_treasury_refill_checks", ["event_type"])
    op.create_index("ix_glame_treasury_refill_checks_status", "glame_treasury_refill_checks", ["status"])
    op.create_index("ix_glame_treasury_refill_checks_reason", "glame_treasury_refill_checks", ["reason"])
    op.create_index("ix_glame_treasury_refill_checks_network", "glame_treasury_refill_checks", ["network"])
    op.create_index("ix_glame_treasury_refill_checks_treasury_address", "glame_treasury_refill_checks", ["treasury_address"])
    op.create_index("ix_glame_treasury_refill_checks_hot_wallet_address", "glame_treasury_refill_checks", ["hot_wallet_address"])
    op.create_index("ix_glame_treasury_refill_checks_ton_tx_hash", "glame_treasury_refill_checks", ["ton_tx_hash"])
    op.create_index("ix_glame_treasury_refill_checks_created_by", "glame_treasury_refill_checks", ["created_by"])
    op.create_index("ix_glame_treasury_refill_checks_created_at", "glame_treasury_refill_checks", ["created_at"])
    op.create_index("ix_glame_treasury_refill_checks_event_created", "glame_treasury_refill_checks", ["event_type", "created_at"])
    op.create_index("ix_glame_treasury_refill_checks_status_created", "glame_treasury_refill_checks", ["status", "created_at"])
    op.alter_column("glame_treasury_refill_checks", "event_type", server_default=None)


def downgrade():
    op.drop_index("ix_glame_treasury_refill_checks_status_created", table_name="glame_treasury_refill_checks")
    op.drop_index("ix_glame_treasury_refill_checks_event_created", table_name="glame_treasury_refill_checks")
    op.drop_index("ix_glame_treasury_refill_checks_created_at", table_name="glame_treasury_refill_checks")
    op.drop_index("ix_glame_treasury_refill_checks_created_by", table_name="glame_treasury_refill_checks")
    op.drop_index("ix_glame_treasury_refill_checks_ton_tx_hash", table_name="glame_treasury_refill_checks")
    op.drop_index("ix_glame_treasury_refill_checks_hot_wallet_address", table_name="glame_treasury_refill_checks")
    op.drop_index("ix_glame_treasury_refill_checks_treasury_address", table_name="glame_treasury_refill_checks")
    op.drop_index("ix_glame_treasury_refill_checks_network", table_name="glame_treasury_refill_checks")
    op.drop_index("ix_glame_treasury_refill_checks_reason", table_name="glame_treasury_refill_checks")
    op.drop_index("ix_glame_treasury_refill_checks_status", table_name="glame_treasury_refill_checks")
    op.drop_index("ix_glame_treasury_refill_checks_event_type", table_name="glame_treasury_refill_checks")
    op.drop_table("glame_treasury_refill_checks")
