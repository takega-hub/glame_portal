"""inventory control basics

Revision ID: 023_inventory_control_basics
Revises: 022_merge_heads
Create Date: 2026-03-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "023_inventory_control_basics"
down_revision = "022_merge_heads"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("products", sa.Column("is_core_assortment", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("products", sa.Column("supports_brand_concept", sa.Boolean(), nullable=False, server_default=sa.text("false")))

    op.create_table(
        "inventory_target_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("category", sa.String(length=200), nullable=False),
        sa.Column("target_share", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_inventory_target_categories_category",
        "inventory_target_categories",
        ["category"],
        unique=True,
    )


def downgrade():
    op.drop_index("ix_inventory_target_categories_category", table_name="inventory_target_categories")
    op.drop_table("inventory_target_categories")

    op.drop_column("products", "supports_brand_concept")
    op.drop_column("products", "is_core_assortment")

