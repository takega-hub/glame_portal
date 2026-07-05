"""Create GLAME token bridge operations.

Revision ID: 066_glame_token_bridge_operations
Revises: 065_glame_token_daily_audit_hashes
Create Date: 2026-07-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "066_glame_token_bridge_operations"
down_revision = "065_glame_token_daily_audit_hashes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.create_table(
        "glame_token_bridge_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("referral_member_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("token_code", sa.String(length=16), nullable=False, server_default="GLM"),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("points_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("glm_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rate_basis", sa.String(length=64), nullable=True),
        sa.Column("ton_network", sa.String(length=32), nullable=True),
        sa.Column("ton_sender_address", sa.String(length=128), nullable=True),
        sa.Column("ton_recipient_address", sa.String(length=128), nullable=True),
        sa.Column("ton_treasury_address", sa.String(length=128), nullable=True),
        sa.Column("ton_tx_hash", sa.String(length=128), nullable=True),
        sa.Column("ton_status", sa.String(length=64), nullable=True),
        sa.Column("onec_document_id", sa.String(length=128), nullable=True),
        sa.Column("onec_status", sa.String(length=64), nullable=True),
        sa.Column("onec_error", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("source_id", sa.String(length=255), nullable=True),
        sa.Column("meta", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["glame_token_accounts.id"]),
        sa.ForeignKeyConstraint(["referral_member_id"], ["referral_program_members.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["glame_token_transactions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transaction_id", name="uq_glame_token_bridge_operations_transaction"),
        sa.UniqueConstraint("idempotency_key", name="uq_glame_token_bridge_operations_idempotency"),
    )
    op.create_index("ix_glame_token_bridge_operations_account_id", "glame_token_bridge_operations", ["account_id"], unique=False)
    op.create_index("ix_glame_token_bridge_operations_created_at", "glame_token_bridge_operations", ["created_at"], unique=False)
    op.create_index("ix_glame_token_bridge_operations_direction", "glame_token_bridge_operations", ["direction"], unique=False)
    op.create_index("ix_glame_token_bridge_operations_direction_status", "glame_token_bridge_operations", ["direction", "status"], unique=False)
    op.create_index("ix_glame_token_bridge_operations_idempotency_key", "glame_token_bridge_operations", ["idempotency_key"], unique=True)
    op.create_index("ix_glame_token_bridge_operations_member_direction", "glame_token_bridge_operations", ["referral_member_id", "direction"], unique=False)
    op.create_index("ix_glame_token_bridge_operations_onec", "glame_token_bridge_operations", ["onec_status", "onec_document_id"], unique=False)
    op.create_index("ix_glame_token_bridge_operations_onec_document_id", "glame_token_bridge_operations", ["onec_document_id"], unique=False)
    op.create_index("ix_glame_token_bridge_operations_onec_status", "glame_token_bridge_operations", ["onec_status"], unique=False)
    op.create_index("ix_glame_token_bridge_operations_processed_at", "glame_token_bridge_operations", ["processed_at"], unique=False)
    op.create_index("ix_glame_token_bridge_operations_referral_member_id", "glame_token_bridge_operations", ["referral_member_id"], unique=False)
    op.create_index("ix_glame_token_bridge_operations_requested_at", "glame_token_bridge_operations", ["requested_at"], unique=False)
    op.create_index("ix_glame_token_bridge_operations_source", "glame_token_bridge_operations", ["source"], unique=False)
    op.create_index("ix_glame_token_bridge_operations_source_id", "glame_token_bridge_operations", ["source_id"], unique=False)
    op.create_index("ix_glame_token_bridge_operations_status", "glame_token_bridge_operations", ["status"], unique=False)
    op.create_index("ix_glame_token_bridge_operations_token_code", "glame_token_bridge_operations", ["token_code"], unique=False)
    op.create_index("ix_glame_token_bridge_operations_ton", "glame_token_bridge_operations", ["ton_status", "ton_tx_hash"], unique=False)
    op.create_index("ix_glame_token_bridge_operations_ton_network", "glame_token_bridge_operations", ["ton_network"], unique=False)
    op.create_index("ix_glame_token_bridge_operations_ton_recipient_address", "glame_token_bridge_operations", ["ton_recipient_address"], unique=False)
    op.create_index("ix_glame_token_bridge_operations_ton_sender_address", "glame_token_bridge_operations", ["ton_sender_address"], unique=False)
    op.create_index("ix_glame_token_bridge_operations_ton_status", "glame_token_bridge_operations", ["ton_status"], unique=False)
    op.create_index("ix_glame_token_bridge_operations_ton_treasury_address", "glame_token_bridge_operations", ["ton_treasury_address"], unique=False)
    op.create_index("ix_glame_token_bridge_operations_ton_tx_hash", "glame_token_bridge_operations", ["ton_tx_hash"], unique=False)
    op.create_index("ix_glame_token_bridge_operations_transaction_id", "glame_token_bridge_operations", ["transaction_id"], unique=True)
    op.create_index("ix_glame_token_bridge_operations_user_id", "glame_token_bridge_operations", ["user_id"], unique=False)

    op.execute(
        """
        INSERT INTO glame_token_bridge_operations (
            id,
            transaction_id,
            account_id,
            user_id,
            referral_member_id,
            token_code,
            direction,
            status,
            idempotency_key,
            points_amount,
            glm_amount,
            rate_basis,
            ton_network,
            ton_sender_address,
            ton_recipient_address,
            ton_treasury_address,
            ton_tx_hash,
            ton_status,
            onec_document_id,
            onec_status,
            onec_error,
            source,
            source_id,
            meta,
            requested_at,
            processed_at,
            created_at,
            updated_at
        )
        SELECT
            gen_random_uuid(),
            t.id,
            t.account_id,
            t.user_id,
            t.referral_member_id,
            t.token_code,
            CASE
                WHEN t.reason IN ('glm_to_points_bridge', 'buy_loyalty_points') THEN 'glm_to_points'
                ELSE 'points_to_glm'
            END,
            t.status,
            COALESCE(t.source_id, t.id::text),
            COALESCE(NULLIF(t.meta->>'target_points', '')::integer, NULLIF(t.meta->>'points_converted', '')::integer, ABS(t.amount), 0),
            ABS(t.amount),
            COALESCE(t.meta->>'rate', '1 GLM = 1 point'),
            COALESCE(NULLIF(t.meta->>'ton_network', ''), current_setting('app.ton_network', true)),
            NULLIF(COALESCE(t.meta->>'expected_ton_sender_address', t.meta->>'ton_sender_address'), ''),
            NULLIF(COALESCE(t.meta->>'wallet_address', t.meta->>'ton_recipient_address'), ''),
            NULLIF(t.meta->>'treasury_address', ''),
            NULLIF(COALESCE(t.meta->>'deposit_tx_hash', t.meta->>'tx_hash'), ''),
            NULLIF(COALESCE(t.meta->>'ton_deposit_status', t.meta->'ton_auto_transfer'->>'status'), ''),
            NULLIF(COALESCE(t.meta->>'onec_document_id', t.meta->>'onec_spend_document_id'), ''),
            NULLIF(COALESCE(t.meta->>'onec_sync_status', t.meta->>'onec_spend_sync_status'), ''),
            NULLIF(COALESCE(t.meta->>'onec_sync_error', t.meta->>'onec_spend_sync_error'), ''),
            t.source,
            t.source_id,
            json_build_object(
                'backfilled', true,
                'transaction_type', t.transaction_type,
                'reason', t.reason,
                'legacy_meta', t.meta
            ),
            COALESCE(NULLIF(t.meta->>'requested_at', '')::timestamptz, t.created_at),
            NULLIF(t.meta->>'processed_at', '')::timestamptz,
            t.created_at,
            now()
        FROM glame_token_transactions t
        WHERE t.token_code = 'GLM'
          AND (
              (t.transaction_type = 'bridge' AND t.reason IN ('glm_to_points_bridge', 'buy_loyalty_points'))
              OR (t.transaction_type IN ('claim', 'conversion') AND t.reason IN ('points_to_ton_bridge', 'points_to_glm_bridge'))
          )
        ON CONFLICT (transaction_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_glame_token_bridge_operations_user_id", table_name="glame_token_bridge_operations")
    op.drop_index("ix_glame_token_bridge_operations_transaction_id", table_name="glame_token_bridge_operations")
    op.drop_index("ix_glame_token_bridge_operations_ton_tx_hash", table_name="glame_token_bridge_operations")
    op.drop_index("ix_glame_token_bridge_operations_ton_treasury_address", table_name="glame_token_bridge_operations")
    op.drop_index("ix_glame_token_bridge_operations_ton_status", table_name="glame_token_bridge_operations")
    op.drop_index("ix_glame_token_bridge_operations_ton_sender_address", table_name="glame_token_bridge_operations")
    op.drop_index("ix_glame_token_bridge_operations_ton_recipient_address", table_name="glame_token_bridge_operations")
    op.drop_index("ix_glame_token_bridge_operations_ton_network", table_name="glame_token_bridge_operations")
    op.drop_index("ix_glame_token_bridge_operations_ton", table_name="glame_token_bridge_operations")
    op.drop_index("ix_glame_token_bridge_operations_token_code", table_name="glame_token_bridge_operations")
    op.drop_index("ix_glame_token_bridge_operations_status", table_name="glame_token_bridge_operations")
    op.drop_index("ix_glame_token_bridge_operations_source_id", table_name="glame_token_bridge_operations")
    op.drop_index("ix_glame_token_bridge_operations_source", table_name="glame_token_bridge_operations")
    op.drop_index("ix_glame_token_bridge_operations_requested_at", table_name="glame_token_bridge_operations")
    op.drop_index("ix_glame_token_bridge_operations_referral_member_id", table_name="glame_token_bridge_operations")
    op.drop_index("ix_glame_token_bridge_operations_processed_at", table_name="glame_token_bridge_operations")
    op.drop_index("ix_glame_token_bridge_operations_onec_status", table_name="glame_token_bridge_operations")
    op.drop_index("ix_glame_token_bridge_operations_onec_document_id", table_name="glame_token_bridge_operations")
    op.drop_index("ix_glame_token_bridge_operations_onec", table_name="glame_token_bridge_operations")
    op.drop_index("ix_glame_token_bridge_operations_member_direction", table_name="glame_token_bridge_operations")
    op.drop_index("ix_glame_token_bridge_operations_idempotency_key", table_name="glame_token_bridge_operations")
    op.drop_index("ix_glame_token_bridge_operations_direction_status", table_name="glame_token_bridge_operations")
    op.drop_index("ix_glame_token_bridge_operations_direction", table_name="glame_token_bridge_operations")
    op.drop_index("ix_glame_token_bridge_operations_created_at", table_name="glame_token_bridge_operations")
    op.drop_index("ix_glame_token_bridge_operations_account_id", table_name="glame_token_bridge_operations")
    op.drop_table("glame_token_bridge_operations")
