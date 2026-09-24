from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database.connection import Base


class AppPromotion(Base):
    __tablename__ = "app_promotions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    banner_image_url = Column(String(500), nullable=True)
    body = Column(String, nullable=False)
    starts_at = Column(DateTime(timezone=True), nullable=True)
    ends_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="draft")
    discount_kind = Column(String(64), nullable=False, default="none")
    is_cart_discount = Column(Boolean, nullable=False, default=False)
    group_size = Column(Integer, nullable=False, default=3)
    discounted_items_per_group = Column(Integer, nullable=False, default=1)
    discounted_item_price = Column(Integer, nullable=False, default=100)
    discount_config = Column(JSON, nullable=True)
    updated_by_user_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
