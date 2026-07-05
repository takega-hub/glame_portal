"""Create GLAME token daily audit hashes.

Revision ID: 065_glame_token_daily_audit_hashes
Revises: 064_glame_token_ledger
Create Date: 2026-07-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "065_glame_token_daily_audit_hashes"
down_revision = "064_glame_token_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "glame_token_daily_audit_hashes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("audit_date", sa.Date(), nullable=False),
        sa.Column("token_code", sa.String(length=16), nullable=False, server_default="GLM"),
        sa.Column("root_hash", sa.String(length=64), nullable=False),
        sa.Column("previous_root_hash", sa.String(length=64), nullable=True),
        sa.Column("transactions_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accounts_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("balance_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hold_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lifetime_earned_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lifetime_burned_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload", postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("public_status", sa.String(length=32), nullable=False, server_default="internal"),
        sa.Column("public_reference", sa.Text(), nullable=True),
        sa.Column("generated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["generated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("audit_date", name="uq_glame_token_daily_audit_hashes_date"),
    )
    op.create_index("ix_glame_token_daily_audit_hashes_audit_date", "glame_token_daily_audit_hashes", ["audit_date"], unique=True)
    op.create_index("ix_glame_token_daily_audit_hashes_generated_at", "glame_token_daily_audit_hashes", ["generated_at"], unique=False)
    op.create_index("ix_glame_token_daily_audit_hashes_generated_by", "glame_token_daily_audit_hashes", ["generated_by"], unique=False)
    op.create_index("ix_glame_token_daily_audit_hashes_public_status", "glame_token_daily_audit_hashes", ["public_status"], unique=False)
    op.create_index("ix_glame_token_daily_audit_hashes_token_code", "glame_token_daily_audit_hashes", ["token_code"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_glame_token_daily_audit_hashes_token_code", table_name="glame_token_daily_audit_hashes")
    op.drop_index("ix_glame_token_daily_audit_hashes_public_status", table_name="glame_token_daily_audit_hashes")
    op.drop_index("ix_glame_token_daily_audit_hashes_generated_by", table_name="glame_token_daily_audit_hashes")
    op.drop_index("ix_glame_token_daily_audit_hashes_generated_at", table_name="glame_token_daily_audit_hashes")
    op.drop_index("ix_glame_token_daily_audit_hashes_audit_date", table_name="glame_token_daily_audit_hashes")
    op.drop_table("glame_token_daily_audit_hashes")
