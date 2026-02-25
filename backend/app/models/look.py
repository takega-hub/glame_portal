from sqlalchemy import Column, String, JSON, Text, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.database.connection import Base


class Look(Base):
    __tablename__ = "looks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    product_ids = Column(JSON, nullable=False, default=list)  # массив UUID товаров
    style = Column(String(100), nullable=True)  # романтичный, деловой, etc.
    mood = Column(String(100), nullable=True)  # нежный вечер, уверенный день, etc.
    description = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=True)  # Основное изображение (для обратной совместимости)
    image_urls = Column(JSON, nullable=True, default=list)  # Массив всех сгенерированных изображений
    current_image_index = Column(Integer, nullable=True, default=0)  # Индекс текущего основного изображения в image_urls
    
    # Новые поля для генерации образов
    status = Column(String(50), nullable=True, default="draft")  # draft, approved, rejected, auto_generated
    generation_metadata = Column(JSON, nullable=True, default=dict)  # метаданные генерации (правила, тренды, persona)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)  # ID пользователя, для которого создан образ
    approval_status = Column(String(50), nullable=True, default="pending")  # pending, approved, rejected
    try_on_image_url = Column(String(500), nullable=True)  # URL изображения с примеркой на фото пользователя
    fashion_trends = Column(JSON, nullable=True, default=list)  # использованные тренды при генерации
    client_requirements = Column(JSON, nullable=True, default=dict)  # требования клиента, учтенные при генерации
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", backref="looks")
