from sqlalchemy import Column, String, Float, DateTime, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database.connection import Base


class InventoryTargetCategory(Base):
    __tablename__ = "inventory_target_categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category = Column(String(200), nullable=False)
    target_share = Column(Float, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (Index("ix_inventory_target_categories_category", "category", unique=True),)

