from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database.connection import Base


class AppNews(Base):
    __tablename__ = "app_news"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    preview_image_url = Column(String(500), nullable=True)
    body = Column(String, nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="draft")
    updated_by_user_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

