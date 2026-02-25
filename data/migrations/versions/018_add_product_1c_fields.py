"""add product 1c fields

Revision ID: 018_add_product_1c_fields
Revises: 017_make_user_email_nullable
Create Date: 2026-02-03 12:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "018_add_product_1c_fields"
down_revision = "017_make_user_email_nullable"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("products", sa.Column("article", sa.String(length=100), nullable=True))
    op.add_column("products", sa.Column("vendor_code", sa.String(length=100), nullable=True))
    op.add_column("products", sa.Column("barcode", sa.String(length=100), nullable=True))
    op.add_column("products", sa.Column("unit", sa.String(length=50), nullable=True))
    op.add_column("products", sa.Column("weight", sa.Float(), nullable=True))
    op.add_column("products", sa.Column("volume", sa.Float(), nullable=True))
    op.add_column("products", sa.Column("country", sa.String(length=100), nullable=True))
    op.add_column("products", sa.Column("warranty", sa.String(length=100), nullable=True))
    op.add_column("products", sa.Column("full_description", sa.Text(), nullable=True))
    op.add_column("products", sa.Column("specifications", sa.JSON(), nullable=True))
    op.add_column("products", sa.Column("onec_data", sa.JSON(), nullable=True))
    
    # Создаем индекс для быстрого поиска по артикулу
    op.create_index("ix_products_article", "products", ["article"])


def downgrade():
    op.drop_column("products", "onec_data")
    op.drop_column("products", "specifications")
    op.drop_column("products", "full_description")
    op.drop_column("products", "warranty")
    op.drop_column("products", "country")
    op.drop_column("products", "volume")
    op.drop_column("products", "weight")
    op.drop_column("products", "unit")
    op.drop_column("products", "barcode")
    op.drop_column("products", "vendor_code")
    op.drop_column("products", "article")
