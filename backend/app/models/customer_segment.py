"""
Модель сегментов покупателей
"""
from sqlalchemy import Column, String, DateTime, JSON, Integer, Boolean, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database.connection import Base


class CustomerSegment(Base):
    __tablename__ = "customer_segments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True)  # VIP, Active, Sleeping, etc.
    description = Column(Text, nullable=True)
    
    # Правила сегментации (JSON условия)
    rules = Column(JSON, nullable=True)  # {"min_purchases": 5, "min_total": 50000, ...}
    
    # Статистика
    customer_count = Column(Integer, default=0, nullable=False)
    
    # Метаданные
    is_active = Column(Boolean, default=True, nullable=False)
    is_auto_generated = Column(Boolean, default=False, nullable=False)  # создан AI или вручную
    color = Column(String(20), nullable=True)  # цвет для UI
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Индексы
    __table_args__ = (
        Index('ix_customer_segments_active', 'is_active'),
        Index('ix_customer_segments_auto', 'is_auto_generated'),
    )
