from sqlalchemy import Column, String, DateTime, Boolean, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database.connection import Base


class AppLookbook(Base):
    __tablename__ = "app_lookbooks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    cover_image_url = Column(String(500), nullable=False)
    description = Column(String(2000), nullable=True)
    items = Column(JSON, nullable=False, default=list)
    is_published = Column(Boolean, nullable=False, default=False)
    updated_by_user_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

