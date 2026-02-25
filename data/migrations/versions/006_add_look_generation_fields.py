"""Add look generation fields for AI-generated looks

Revision ID: 006_add_look_generation_fields
Revises: 005_add_app_settings
Create Date: 2026-01-28 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "006_add_look_generation_fields"
down_revision = "005_add_app_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавляем новые поля для генерации образов
    op.add_column("looks", sa.Column("status", sa.String(length=50), nullable=True))
    op.add_column("looks", sa.Column("generation_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("looks", sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("looks", sa.Column("approval_status", sa.String(length=50), nullable=True))
    op.add_column("looks", sa.Column("try_on_image_url", sa.String(length=500), nullable=True))
    op.add_column("looks", sa.Column("fashion_trends", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("looks", sa.Column("client_requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    
    # Создаем внешний ключ для user_id
    op.create_foreign_key(
        "fk_looks_user_id",
        "looks",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL"
    )
    
    # Создаем индекс для быстрого поиска по статусу и approval_status
    op.create_index("ix_looks_status", "looks", ["status"])
    op.create_index("ix_looks_approval_status", "looks", ["approval_status"])
    op.create_index("ix_looks_user_id", "looks", ["user_id"])


def downgrade() -> None:
    # Удаляем индексы
    op.drop_index("ix_looks_user_id", table_name="looks")
    op.drop_index("ix_looks_approval_status", table_name="looks")
    op.drop_index("ix_looks_status", table_name="looks")
    
    # Удаляем внешний ключ
    op.drop_constraint("fk_looks_user_id", "looks", type_="foreignkey")
    
    # Удаляем колонки
    op.drop_column("looks", "client_requirements")
    op.drop_column("looks", "fashion_trends")
    op.drop_column("looks", "try_on_image_url")
    op.drop_column("looks", "approval_status")
    op.drop_column("looks", "user_id")
    op.drop_column("looks", "generation_metadata")
    op.drop_column("looks", "status")
