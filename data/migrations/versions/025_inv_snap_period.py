"""inventory snapshots period range

Revision ID: 025_inv_snap_period
Revises: 024_inventory_snapshots
Create Date: 2026-03-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "025_inv_snap_period"
down_revision = "024_inventory_snapshots"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("inventory_snapshots", sa.Column("period_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("inventory_snapshots", sa.Column("period_end", sa.DateTime(timezone=True), nullable=True))

    op.drop_index("ix_inventory_snapshots_type_store_period", table_name="inventory_snapshots")
    op.create_index(
        "ix_inventory_snapshots_type_store_period",
        "inventory_snapshots",
        ["snapshot_type", "store_id", "analysis_period_days", "period_start", "period_end"],
        unique=True,
    )


def downgrade():
    op.drop_index("ix_inventory_snapshots_type_store_period", table_name="inventory_snapshots")
    op.create_index(
        "ix_inventory_snapshots_type_store_period",
        "inventory_snapshots",
        ["snapshot_type", "store_id", "analysis_period_days"],
        unique=True,
    )

    op.drop_column("inventory_snapshots", "period_end")
    op.drop_column("inventory_snapshots", "period_start")

