import uuid

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database.connection import Base


class RewardStoreItem(Base):
    __tablename__ = "reward_store_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sku = Column(String(120), nullable=False, unique=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(64), nullable=False, default="branded_goods", index=True)
    inventory_status = Column(String(64), nullable=False, default="pilot_batch")
    status = Column(String(32), nullable=False, default="available", index=True)
    price_glm = Column(Integer, nullable=True)
    price_points = Column(Integer, nullable=True)
    sort_order = Column(Integer, nullable=False, default=100)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    __table_args__ = (
        Index("ix_reward_store_items_active_sort", "is_active", "sort_order", "created_at"),
    )
