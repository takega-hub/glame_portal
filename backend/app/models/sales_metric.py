from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database.connection import Base


class SalesMetric(Base):
    __tablename__ = "sales_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    date = Column(DateTime(timezone=True), nullable=False, index=True)
    order_id = Column(String(255), nullable=True)  # ID заказа из 1С (если применимо)
    store_id = Column(UUID(as_uuid=True), ForeignKey("stores.id"), nullable=True, index=True)
    channel = Column(String(64), nullable=True, index=True)  # online, offline, instagram, vk, etc.
    
    # Основные метрики продаж
    revenue = Column(Float, nullable=False, default=0.0)  # Выручка
    order_count = Column(Integer, nullable=False, default=0)  # Количество заказов
    items_sold = Column(Integer, nullable=False, default=0)  # Количество проданных товаров
    average_order_value = Column(Float, nullable=False, default=0.0)  # Средний чек
    
    # Возвраты
    returns_count = Column(Integer, nullable=True, default=0)  # Количество возвратов
    returns_amount = Column(Float, nullable=True, default=0.0)  # Сумма возвратов
    
    # Дополнительные данные
    meta_data = Column(JSON, nullable=True, default=dict)  # Детали по товарам, клиентам и т.д.
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Составные индексы для быстрых запросов
    __table_args__ = (
        Index('ix_sales_metrics_date_channel', 'date', 'channel'),
        Index('ix_sales_metrics_date_store', 'date', 'store_id'),
        Index('ix_sales_metrics_channel_date', 'channel', 'date'),
    )
