"""Create GLAME token ledger.

Revision ID: 064_glame_token_ledger
Revises: 063_gift_certificate_recipient_user
Create Date: 2026-06-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "064_glame_token_ledger"
down_revision = "063_gift_certificate_recipient_user"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "glame_token_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("referral_member_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("token_code", sa.String(length=16), nullable=False, server_default="GLM"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("balance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hold_balance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lifetime_earned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lifetime_burned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("meta", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["referral_member_id"], ["referral_program_members.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("referral_member_id", "token_code", name="uq_glame_token_accounts_referral_member_token"),
    )
    op.create_index("ix_glame_token_accounts_created_at", "glame_token_accounts", ["created_at"], unique=False)
    op.create_index("ix_glame_token_accounts_referral_member_id", "glame_token_accounts", ["referral_member_id"], unique=False)
    op.create_index("ix_glame_token_accounts_status", "glame_token_accounts", ["status"], unique=False)
    op.create_index("ix_glame_token_accounts_token_code", "glame_token_accounts", ["token_code"], unique=False)
    op.create_index("ix_glame_token_accounts_user_id", "glame_token_accounts", ["user_id"], unique=False)
    op.create_index("ix_glame_token_accounts_user_token", "glame_token_accounts", ["user_id", "token_code"], unique=False)

    op.create_table(
        "glame_token_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("referral_member_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("referral_commission_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("token_code", sa.String(length=16), nullable=False, server_default="GLM"),
        sa.Column("transaction_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="hold"),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hold_balance_after", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reason", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("source_id", sa.String(length=255), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["glame_token_accounts.id"]),
        sa.ForeignKeyConstraint(["referral_commission_id"], ["referral_commissions.id"]),
        sa.ForeignKeyConstraint(["referral_member_id"], ["referral_program_members.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_glame_token_transactions_account_date", "glame_token_transactions", ["account_id", "created_at"], unique=False)
    op.create_index("ix_glame_token_transactions_account_id", "glame_token_transactions", ["account_id"], unique=False)
    op.create_index("ix_glame_token_transactions_available_at", "glame_token_transactions", ["available_at"], unique=False)
    op.create_index("ix_glame_token_transactions_commission", "glame_token_transactions", ["referral_commission_id", "transaction_type"], unique=False)
    op.create_index("ix_glame_token_transactions_created_at", "glame_token_transactions", ["created_at"], unique=False)
    op.create_index("ix_glame_token_transactions_expires_at", "glame_token_transactions", ["expires_at"], unique=False)
    op.create_index("ix_glame_token_transactions_member_status", "glame_token_transactions", ["referral_member_id", "status"], unique=False)
    op.create_index("ix_glame_token_transactions_reason", "glame_token_transactions", ["reason"], unique=False)
    op.create_index("ix_glame_token_transactions_referral_commission_id", "glame_token_transactions", ["referral_commission_id"], unique=False)
    op.create_index("ix_glame_token_transactions_referral_member_id", "glame_token_transactions", ["referral_member_id"], unique=False)
    op.create_index("ix_glame_token_transactions_source", "glame_token_transactions", ["source"], unique=False)
    op.create_index("ix_glame_token_transactions_source_id", "glame_token_transactions", ["source_id"], unique=True)
    op.create_index("ix_glame_token_transactions_status", "glame_token_transactions", ["status"], unique=False)
    op.create_index("ix_glame_token_transactions_token_code", "glame_token_transactions", ["token_code"], unique=False)
    op.create_index("ix_glame_token_transactions_transaction_type", "glame_token_transactions", ["transaction_type"], unique=False)
    op.create_index("ix_glame_token_transactions_user_id", "glame_token_transactions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_glame_token_transactions_user_id", table_name="glame_token_transactions")
    op.drop_index("ix_glame_token_transactions_transaction_type", table_name="glame_token_transactions")
    op.drop_index("ix_glame_token_transactions_token_code", table_name="glame_token_transactions")
    op.drop_index("ix_glame_token_transactions_status", table_name="glame_token_transactions")
    op.drop_index("ix_glame_token_transactions_source_id", table_name="glame_token_transactions")
    op.drop_index("ix_glame_token_transactions_source", table_name="glame_token_transactions")
    op.drop_index("ix_glame_token_transactions_referral_member_id", table_name="glame_token_transactions")
    op.drop_index("ix_glame_token_transactions_referral_commission_id", table_name="glame_token_transactions")
    op.drop_index("ix_glame_token_transactions_reason", table_name="glame_token_transactions")
    op.drop_index("ix_glame_token_transactions_member_status", table_name="glame_token_transactions")
    op.drop_index("ix_glame_token_transactions_expires_at", table_name="glame_token_transactions")
    op.drop_index("ix_glame_token_transactions_created_at", table_name="glame_token_transactions")
    op.drop_index("ix_glame_token_transactions_commission", table_name="glame_token_transactions")
    op.drop_index("ix_glame_token_transactions_available_at", table_name="glame_token_transactions")
    op.drop_index("ix_glame_token_transactions_account_id", table_name="glame_token_transactions")
    op.drop_index("ix_glame_token_transactions_account_date", table_name="glame_token_transactions")
    op.drop_table("glame_token_transactions")

    op.drop_index("ix_glame_token_accounts_user_token", table_name="glame_token_accounts")
    op.drop_index("ix_glame_token_accounts_user_id", table_name="glame_token_accounts")
    op.drop_index("ix_glame_token_accounts_token_code", table_name="glame_token_accounts")
    op.drop_index("ix_glame_token_accounts_status", table_name="glame_token_accounts")
    op.drop_index("ix_glame_token_accounts_referral_member_id", table_name="glame_token_accounts")
    op.drop_index("ix_glame_token_accounts_created_at", table_name="glame_token_accounts")
    op.drop_table("glame_token_accounts")
