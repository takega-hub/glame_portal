"""
Модель сохраненных образов покупателей
"""
from sqlalchemy import Column, String, DateTime, JSON, Boolean, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.database.connection import Base


class SavedLook(Base):
    __tablename__ = "saved_looks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    look_id = Column(UUID(as_uuid=True), ForeignKey("looks.id"), nullable=False, index=True)
    
    # Тип
    save_type = Column(String(50), nullable=False)  # favorite (из каталога) или generated (AI сгенерированный)
    
    # Персонализация
    notes = Column(Text, nullable=True)  # заметки покупателя
    is_purchased = Column(Boolean, default=False, nullable=False)  # куплен ли образ
    purchased_at = Column(DateTime(timezone=True), nullable=True)
    
    # Метаданные AI
    generation_context = Column(JSON, nullable=True)  # контекст генерации (если generated)
    recommended_occasions = Column(JSON, nullable=True)  # рекомендуемые поводы для образа
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Отношения
    user = relationship("User", backref="saved_looks")
    look = relationship("Look")
    
    # Индексы
    __table_args__ = (
        Index('ix_saved_looks_user_type', 'user_id', 'save_type'),
        Index('ix_saved_looks_user_created', 'user_id', 'created_at'),
    )
