"""
Модель для рекомендаций по закупкам товаров
Используется для определения оптимального количества товаров для заказа
"""
from sqlalchemy import Column, String, Float, Integer, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database.connection import Base


class PurchaseRecommendation(Base):
    """Рекомендации по закупкам товаров"""
    __tablename__ = "purchase_recommendation"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Связь с товаром
    product_id_1c = Column(String(255), nullable=True, index=True)  # Номенклатура_Key из 1С
    product_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # ID товара из каталога (если есть)
    
    # Данные о товаре (для быстрого доступа)
    product_name = Column(String(500), nullable=True, index=True)
    product_article = Column(String(100), nullable=True, index=True)
    category = Column(String(100), nullable=True, index=True)
    brand = Column(String(100), nullable=True, index=True)
    
    # Текущие остатки
    current_stock = Column(Integer, nullable=False, default=0)  # Текущий остаток
    
    # Рекомендации
    recommended_stock = Column(Integer, nullable=True)  # Рекомендуемый остаток
    reorder_quantity = Column(Integer, nullable=True)  # Количество для заказа
    reorder_point = Column(Integer, nullable=True)  # Точка заказа (когда заказывать)
    
    # Метрики для расчёта
    days_of_stock = Column(Float, nullable=True)  # Дней остатка при текущих продажах
    avg_daily_sales = Column(Float, nullable=True)  # Средние продажи в день
    turnover_rate = Column(Float, nullable=True)  # Коэффициент оборачиваемости
    turnover_days = Column(Float, nullable=True)  # Оборачиваемость в днях
    
    # Уровень срочности
    urgency_level = Column(String(20), nullable=True, index=True)  # critical, high, medium, low
    
    # Распределение по магазинам (JSON)
    store_distribution = Column(String(500), nullable=True)  # JSON строка с распределением по магазинам
    
    # Даты
    recommended_date = Column(DateTime(timezone=True), nullable=True)  # Рекомендуемая дата заказа
    calculated_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Индексы для быстрых запросов
    __table_args__ = (
        Index('ix_purchase_recommendation_product', 'product_id_1c'),
        Index('ix_purchase_recommendation_urgency', 'urgency_level'),
        Index('ix_purchase_recommendation_category', 'category'),
        Index('ix_purchase_recommendation_date', 'recommended_date'),
    )
