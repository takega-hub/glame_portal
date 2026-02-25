from sqlalchemy import Column, String, DateTime, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database.connection import Base


class ContentPlan(Base):
    __tablename__ = "content_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)

    name = Column(String(255), nullable=True)
    status = Column(String(50), nullable=False, default="draft")  # draft, active, archived

    # диапазон планирования (в timezone пользователя)
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)
    timezone = Column(String(64), nullable=False, default="Europe/Moscow")

    # параметры генерации/контекст (каналы, частоты, персоны, цели, кампании и т.п.)
    inputs = Column(JSON, nullable=True, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

