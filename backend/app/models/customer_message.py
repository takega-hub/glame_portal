"""
Модель сгенерированных сообщений для покупателей.
Хранит историю сообщений для управления общением и контекстом диалога.
"""
from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.database.connection import Base


class CustomerMessage(Base):
    """Сгенерированное сообщение для покупателя (персональная рассылка)."""
    __tablename__ = "customer_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    # Текст сообщения
    message = Column(Text, nullable=False)
    cta = Column(Text, nullable=True)

    # Контекст генерации
    segment = Column(String(20), nullable=True)
    event_type = Column(String(100), nullable=True)   # brand_arrival, loyalty_level_up, ...
    event_brand = Column(String(255), nullable=True)
    event_store = Column(String(255), nullable=True)
    payload = Column(JSONB, nullable=True)  # полный ответ генерации (segment, reason, brand, store и т.д.)

    # Статус: new — новое, sent — отправлено
    status = Column(String(20), nullable=False, default="new", index=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="customer_messages")

    __table_args__ = (
        Index("ix_customer_messages_user_created", "user_id", "created_at"),
    )
