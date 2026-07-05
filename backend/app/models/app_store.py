from sqlalchemy import JSON, Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database.connection import Base


class AppStore(Base):
    __tablename__ = "app_stores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    city = Column(String(120), nullable=False)
    title = Column(String(255), nullable=False)
    address = Column(String(500), nullable=False)
    working_hours = Column(String(255), nullable=True)
    phone = Column(String(80), nullable=True)
    comment = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=True)
    image_urls = Column(JSON, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    updated_by_user_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
