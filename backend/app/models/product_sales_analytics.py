"""
Модель для агрегированных данных о продажах товаров
Используется для быстрого анализа без запросов к детальным записям SalesRecord
"""
from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, Date, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database.connection import Base


class ProductSalesAnalytics(Base):
    """Агрегированные метрики продаж по товарам"""
    __tablename__ = "product_sales_analytics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Связь с товаром
    product_id_1c = Column(String(255), nullable=True, index=True)  # Номенклатура_Key из 1С
    product_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # ID товара из каталога (если есть)
    
    # Данные о товаре (для быстрого доступа без JOIN)
    product_name = Column(String(500), nullable=True, index=True)
    product_article = Column(String(100), nullable=True, index=True)
    category = Column(String(100), nullable=True, index=True)
    subcategory = Column(String(100), nullable=True, index=True)
    brand = Column(String(100), nullable=True, index=True)
    product_type = Column(String(100), nullable=True, index=True)  # Тип изделия (кольца, серьги и т.д.)
    
    # Период агрегации
    period_date = Column(Date, nullable=False, index=True)  # Дата начала периода
    period_type = Column(String(20), nullable=False, index=True)  # 'day', 'week', 'month', 'quarter', 'year'
    
    # Агрегированные метрики
    total_revenue = Column(Float, nullable=False, default=0.0)  # Общая выручка за период
    total_quantity = Column(Float, nullable=False, default=0.0)  # Общее количество проданных единиц
    orders_count = Column(Integer, nullable=False, default=0)  # Количество заказов/продаж
    avg_price = Column(Float, nullable=True)  # Средняя цена продажи
    avg_quantity_per_order = Column(Float, nullable=True)  # Среднее количество в заказе
    
    # Финансовые метрики
    total_cost = Column(Float, nullable=True)  # Общая себестоимость (если доступна)
    total_margin = Column(Float, nullable=True)  # Общая маржа
    margin_percent = Column(Float, nullable=True)  # Процент маржи
    
    # Канал продаж и магазин
    channel = Column(String(64), nullable=True, index=True)  # offline, online, etc.
    store_id = Column(String(255), nullable=True, index=True)  # Склад_Key из 1С
    
    # Дополнительные метрики
    revenue_without_discount = Column(Float, nullable=True)  # Выручка без скидок
    discount_amount = Column(Float, nullable=True)  # Сумма скидок
    
    # Дополнительные данные в JSON
    raw_metrics = Column(JSON, nullable=True)  # Дополнительные метрики и детали
    
    # Служебные поля
    calculated_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Индексы для быстрых запросов
    __table_args__ = (
        Index('ix_product_sales_analytics_product_period', 'product_id_1c', 'period_date', 'period_type'),
        Index('ix_product_sales_analytics_category_period', 'category', 'period_date', 'period_type'),
        Index('ix_product_sales_analytics_brand_period', 'brand', 'period_date', 'period_type'),
        Index('ix_product_sales_analytics_type_period', 'product_type', 'period_date', 'period_type'),
        Index('ix_product_sales_analytics_store_period', 'store_id', 'period_date', 'period_type'),
        Index('ix_product_sales_analytics_channel_period', 'channel', 'period_date', 'period_type'),
        Index('ix_product_sales_analytics_article', 'product_article'),
        Index('ix_product_sales_analytics_period', 'period_date', 'period_type'),
    )
