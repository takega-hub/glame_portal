"""Add stores and store_visits tables

Revision ID: 011_add_stores
Revises: 010_add_website_visits
Create Date: 2026-01-28 15:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "011_add_stores"
down_revision = "010_add_website_visits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Создаем таблицу stores
    op.create_table(
        "stores",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default='true'),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    
    # Создаем таблицу store_visits
    op.create_table(
        "store_visits",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("store_id", UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("visitor_count", sa.Integer(), nullable=False, server_default='0'),
        sa.Column("sales_count", sa.Integer(), nullable=False, server_default='0'),
        sa.Column("revenue", sa.Float(), nullable=False, server_default='0.0'),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    
    # Внешний ключ
    op.create_foreign_key(
        "fk_store_visits_store_id",
        "store_visits", "stores",
        ["store_id"], ["id"],
        ondelete="CASCADE"
    )
    
    # Индексы
    op.create_index("ix_store_visits_store_id", "store_visits", ["store_id"])
    op.create_index("ix_store_visits_date", "store_visits", ["date"])
    op.create_index("ix_store_visits_store_date", "store_visits", ["store_id", "date"])


def downgrade() -> None:
    op.drop_index("ix_store_visits_store_date", "store_visits")
    op.drop_index("ix_store_visits_date", "store_visits")
    op.drop_index("ix_store_visits_store_id", "store_visits")
    op.drop_constraint("fk_store_visits_store_id", "store_visits", type_="foreignkey")
    op.drop_table("store_visits")
    op.drop_table("stores")
