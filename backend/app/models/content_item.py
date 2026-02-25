from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database.connection import Base


class ContentItem(Base):
    __tablename__ = "content_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    plan_id = Column(UUID(as_uuid=True), ForeignKey("content_plans.id"), nullable=False, index=True)

    # слот в календаре
    scheduled_at = Column(DateTime(timezone=True), nullable=False, index=True)
    timezone = Column(String(64), nullable=False, default="Europe/Moscow")

    channel = Column(String(64), nullable=False)  # instagram, website_main, email, etc.
    content_type = Column(String(64), nullable=False, default="post")  # post, story, reel, email, blog, etc.

    topic = Column(String(500), nullable=True)
    hook = Column(String(500), nullable=True)
    cta = Column(String(500), nullable=True)

    persona = Column(String(500), nullable=True)
    cjm_stage = Column(String(64), nullable=True)
    goal = Column(String(500), nullable=True)

    # параметры/ограничения для генерации (тон, длина, hashtag, UTM и т.д.)
    spec = Column(JSON, nullable=True, default=dict)

    # результат генерации (текст, заголовок, списки, хэштеги, альтернативы и т.п.)
    generated = Column(JSON, nullable=True, default=dict)
    generated_text = Column(Text, nullable=True)

    status = Column(
        String(50),
        nullable=False,
        default="planned",
    )  # planned, draft, ready, approved, scheduled, published, failed, cancelled

    published_at = Column(DateTime(timezone=True), nullable=True)
    publication_metadata = Column(JSON, nullable=True, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

