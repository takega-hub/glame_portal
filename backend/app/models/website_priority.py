"""
Модель для приоритизации товаров для выкладки на сайт
Используется для определения, какие товары должны быть приоритетными на сайте
"""
from sqlalchemy import Column, String, Float, Integer, DateTime, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database.connection import Base


class WebsitePriority(Base):
    """Приоритет товаров для выкладки на сайт"""
    __tablename__ = "website_priority"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Связь с товаром
    product_id_1c = Column(String(255), nullable=True, index=True)  # Номенклатура_Key из 1С
    product_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # ID товара из каталога (если есть)
    
    # Данные о товаре (для быстрого доступа)
    product_name = Column(String(500), nullable=True, index=True)
    product_article = Column(String(100), nullable=True, index=True)
    category = Column(String(100), nullable=True, index=True)
    brand = Column(String(100), nullable=True, index=True)
    
    # Общий приоритет
    priority_score = Column(Float, nullable=False, default=0.0, index=True)  # Общий балл приоритета (0-100)
    priority_class = Column(String(20), nullable=True, index=True)  # high, medium, low
    
    # Компоненты приоритета (0-1 нормализованные значения)
    turnover_score = Column(Float, nullable=True)  # Оценка оборачиваемости (30% веса)
    revenue_score = Column(Float, nullable=True)  # Оценка выручки (25% веса)
    margin_score = Column(Float, nullable=True)  # Оценка маржинальности (25% веса)
    stock_score = Column(Float, nullable=True)  # Оценка наличия остатков (15% веса)
    trend_score = Column(Float, nullable=True)  # Оценка тренда продаж (20% веса)
    seasonality_score = Column(Float, nullable=True)  # Оценка сезонности (10% веса)
    
    # Рекомендации
    is_recommended = Column(Boolean, default=False, index=True)  # Рекомендуется ли для выкладки
    recommendation_reason = Column(String(500), nullable=True)  # Причина рекомендации
    
    # Служебные поля
    calculated_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Индексы для быстрых запросов
    __table_args__ = (
        Index('ix_website_priority_score', 'priority_score'),
        Index('ix_website_priority_class', 'priority_class'),
        Index('ix_website_priority_recommended', 'is_recommended'),
        Index('ix_website_priority_product', 'product_id_1c'),
        Index('ix_website_priority_category', 'category'),
    )
