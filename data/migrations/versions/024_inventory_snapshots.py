"""inventory snapshots

Revision ID: 024_inventory_snapshots
Revises: 023_inventory_control_basics
Create Date: 2026-03-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "024_inventory_snapshots"
down_revision = "023_inventory_control_basics"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inventory_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_type", sa.String(length=64), nullable=False),
        sa.Column("store_id", sa.String(length=255), nullable=True),
        sa.Column("analysis_period_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_inventory_snapshots_type_store_period",
        "inventory_snapshots",
        ["snapshot_type", "store_id", "analysis_period_days"],
        unique=True,
    )
    op.create_index(
        "ix_inventory_snapshots_computed_at",
        "inventory_snapshots",
        ["computed_at"],
    )


def downgrade():
    op.drop_index("ix_inventory_snapshots_computed_at", table_name="inventory_snapshots")
    op.drop_index("ix_inventory_snapshots_type_store_period", table_name="inventory_snapshots")
    op.drop_table("inventory_snapshots")

