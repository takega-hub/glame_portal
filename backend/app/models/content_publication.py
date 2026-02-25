from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database.connection import Base


class ContentPublication(Base):
    __tablename__ = "content_publications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    item_id = Column(UUID(as_uuid=True), ForeignKey("content_items.id"), nullable=False, index=True)

    provider = Column(String(64), nullable=False, default="glame")  # glame, instagram, telegram, etc.
    status = Column(String(50), nullable=False, default="created")  # created, success, failed

    external_id = Column(String(255), nullable=True)
    request_payload = Column(JSON, nullable=True, default=dict)
    response_payload = Column(JSON, nullable=True, default=dict)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

