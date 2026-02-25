"""Expand analytics_events table with additional fields

Revision ID: 008_expand_analytics_events
Revises: 007_add_look_multiple_images
Create Date: 2026-01-28 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "008_expand_analytics_events"
down_revision = "007_add_look_multiple_images"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Добавляем новые колонки
    op.add_column("analytics_events", sa.Column("user_id", UUID(as_uuid=True), nullable=True))
    op.add_column("analytics_events", sa.Column("product_id", UUID(as_uuid=True), nullable=True))
    op.add_column("analytics_events", sa.Column("look_id", UUID(as_uuid=True), nullable=True))
    op.add_column("analytics_events", sa.Column("content_item_id", UUID(as_uuid=True), nullable=True))
    op.add_column("analytics_events", sa.Column("channel", sa.String(length=64), nullable=True))
    op.add_column("analytics_events", sa.Column("utm_source", sa.String(length=255), nullable=True))
    op.add_column("analytics_events", sa.Column("utm_medium", sa.String(length=255), nullable=True))
    op.add_column("analytics_events", sa.Column("utm_campaign", sa.String(length=255), nullable=True))
    
    # Добавляем внешние ключи
    op.create_foreign_key(
        "fk_analytics_events_user_id",
        "analytics_events", "users",
        ["user_id"], ["id"],
        ondelete="SET NULL"
    )
    op.create_foreign_key(
        "fk_analytics_events_product_id",
        "analytics_events", "products",
        ["product_id"], ["id"],
        ondelete="SET NULL"
    )
    op.create_foreign_key(
        "fk_analytics_events_look_id",
        "analytics_events", "looks",
        ["look_id"], ["id"],
        ondelete="SET NULL"
    )
    op.create_foreign_key(
        "fk_analytics_events_content_item_id",
        "analytics_events", "content_items",
        ["content_item_id"], ["id"],
        ondelete="SET NULL"
    )
    
    # Добавляем индексы
    op.create_index("ix_analytics_events_user_id", "analytics_events", ["user_id"])
    op.create_index("ix_analytics_events_product_id", "analytics_events", ["product_id"])
    op.create_index("ix_analytics_events_look_id", "analytics_events", ["look_id"])
    op.create_index("ix_analytics_events_content_item_id", "analytics_events", ["content_item_id"])
    op.create_index("ix_analytics_events_channel", "analytics_events", ["channel"])
    op.create_index("ix_analytics_events_timestamp", "analytics_events", ["timestamp"])
    op.create_index("ix_analytics_events_event_type", "analytics_events", ["event_type"])
    
    # Составные индексы для быстрых запросов
    op.create_index("ix_analytics_events_user_timestamp", "analytics_events", ["user_id", "timestamp"])
    op.create_index("ix_analytics_events_type_timestamp", "analytics_events", ["event_type", "timestamp"])
    op.create_index("ix_analytics_events_channel_timestamp", "analytics_events", ["channel", "timestamp"])


def downgrade() -> None:
    # Удаляем индексы
    op.drop_index("ix_analytics_events_channel_timestamp", "analytics_events")
    op.drop_index("ix_analytics_events_type_timestamp", "analytics_events")
    op.drop_index("ix_analytics_events_user_timestamp", "analytics_events")
    op.drop_index("ix_analytics_events_event_type", "analytics_events")
    op.drop_index("ix_analytics_events_timestamp", "analytics_events")
    op.drop_index("ix_analytics_events_channel", "analytics_events")
    op.drop_index("ix_analytics_events_content_item_id", "analytics_events")
    op.drop_index("ix_analytics_events_look_id", "analytics_events")
    op.drop_index("ix_analytics_events_product_id", "analytics_events")
    op.drop_index("ix_analytics_events_user_id", "analytics_events")
    
    # Удаляем внешние ключи
    op.drop_constraint("fk_analytics_events_content_item_id", "analytics_events", type_="foreignkey")
    op.drop_constraint("fk_analytics_events_look_id", "analytics_events", type_="foreignkey")
    op.drop_constraint("fk_analytics_events_product_id", "analytics_events", type_="foreignkey")
    op.drop_constraint("fk_analytics_events_user_id", "analytics_events", type_="foreignkey")
    
    # Удаляем колонки
    op.drop_column("analytics_events", "utm_campaign")
    op.drop_column("analytics_events", "utm_medium")
    op.drop_column("analytics_events", "utm_source")
    op.drop_column("analytics_events", "channel")
    op.drop_column("analytics_events", "content_item_id")
    op.drop_column("analytics_events", "look_id")
    op.drop_column("analytics_events", "product_id")
    op.drop_column("analytics_events", "user_id")
