"""add product stocks

Revision ID: 019_add_product_stocks
Revises: 018_add_product_1c_fields
Create Date: 2026-02-03 12:10:30.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "019_add_product_stocks"
down_revision = "018_add_product_1c_fields"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "product_stocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("store_id", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reserved_quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("available_quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_product_stocks_product_id", "product_stocks", ["product_id"])
    op.create_index("ix_product_stocks_store_id", "product_stocks", ["store_id"])
    op.create_index(
        "ix_product_stocks_product_store",
        "product_stocks",
        ["product_id", "store_id"],
        unique=True,
    )
    op.create_foreign_key(
        "fk_product_stocks_product_id",
        "product_stocks",
        "products",
        ["product_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint("fk_product_stocks_product_id", "product_stocks", type_="foreignkey")
    op.drop_index("ix_product_stocks_product_store", table_name="product_stocks")
    op.drop_index("ix_product_stocks_store_id", table_name="product_stocks")
    op.drop_index("ix_product_stocks_product_id", table_name="product_stocks")
    op.drop_table("product_stocks")
