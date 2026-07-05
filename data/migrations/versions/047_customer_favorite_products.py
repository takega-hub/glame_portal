"""add customer favorite products

Revision ID: 047_customer_favorite_products
Revises: 046_live_stylist_audit_events
Create Date: 2026-05-26 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "047_customer_favorite_products"
down_revision = "046_live_stylist_audit_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_favorite_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "product_id", name="uq_customer_favorite_products_user_product"),
    )
    op.create_index("ix_customer_favorite_products_user_id", "customer_favorite_products", ["user_id"], unique=False)
    op.create_index("ix_customer_favorite_products_product_id", "customer_favorite_products", ["product_id"], unique=False)
    op.create_index(
        "ix_customer_favorite_products_user_created",
        "customer_favorite_products",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_customer_favorite_products_user_created", table_name="customer_favorite_products")
    op.drop_index("ix_customer_favorite_products_product_id", table_name="customer_favorite_products")
    op.drop_index("ix_customer_favorite_products_user_id", table_name="customer_favorite_products")
    op.drop_table("customer_favorite_products")
