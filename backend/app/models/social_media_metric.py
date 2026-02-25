from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database.connection import Base


class SocialMediaMetric(Base):
    __tablename__ = "social_media_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    platform = Column(String(64), nullable=False, index=True)  # instagram, vk, telegram, etc.
    metric_type = Column(String(64), nullable=False, index=True)  # post, story, followers, engagement, etc.
    post_id = Column(String(255), nullable=True)  # ID поста/контента (если применимо)
    date = Column(DateTime(timezone=True), nullable=False, index=True)  # Дата метрики
    
    # Основные метрики
    value = Column(Float, nullable=False, default=0.0)  # Основное значение метрики
    likes = Column(Integer, nullable=True)  # Лайки
    comments = Column(Integer, nullable=True)  # Комментарии
    shares = Column(Integer, nullable=True)  # Репосты/пересылки
    views = Column(Integer, nullable=True)  # Просмотры
    reach = Column(Integer, nullable=True)  # Охват
    engagement = Column(Float, nullable=True)  # Вовлеченность (%)
    
    # Дополнительные данные
    meta_data = Column(JSON, nullable=True, default=dict)  # Дополнительная информация
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Составные индексы для быстрых запросов
    __table_args__ = (
        Index('ix_social_media_metrics_platform_date', 'platform', 'date'),
        Index('ix_social_media_metrics_platform_type', 'platform', 'metric_type'),
        Index('ix_social_media_metrics_platform_post', 'platform', 'post_id'),
    )
