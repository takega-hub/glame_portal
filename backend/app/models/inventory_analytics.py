"""
Модель для комплексной аналитики остатков товаров
Используется для анализа запасов, прогнозирования дефицита и оптимизации остатков
"""
from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, Date, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database.connection import Base


class InventoryAnalytics(Base):
    """Комплексная аналитика остатков товаров"""
    __tablename__ = "inventory_analytics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Связь с товаром
    product_id_1c = Column(String(255), nullable=True, index=True)  # Номенклатура_Key из 1С
    product_id = Column(UUID(as_uuid=True), nullable=True, index=True)  # ID товара из каталога (если есть)
    
    # Данные о товаре (для быстрого доступа без JOIN)
    product_name = Column(String(500), nullable=True, index=True)
    product_article = Column(String(100), nullable=True, index=True)
    category = Column(String(100), nullable=True, index=True)
    brand = Column(String(100), nullable=True, index=True)
    
    # Магазин/склад
    store_id = Column(String(255), nullable=True, index=True)  # Склад_Key из 1С
    
    # Дата анализа
    analysis_date = Column(Date, nullable=False, index=True)  # Дата анализа
    
    # Текущие остатки
    current_stock = Column(Float, nullable=False, default=0.0)  # Текущий остаток
    avg_stock_30d = Column(Float, nullable=True)  # Средний остаток за 30 дней
    avg_stock_90d = Column(Float, nullable=True)  # Средний остаток за 90 дней
    
    # Скорость продаж
    sales_velocity = Column(Float, nullable=True)  # Скорость продаж (единиц в день)
    avg_daily_sales = Column(Float, nullable=True)  # Средние продажи в день
    
    # Оборачиваемость
    turnover_days = Column(Float, nullable=True)  # Оборачиваемость в днях
    turnover_rate = Column(Float, nullable=True)  # Коэффициент оборачиваемости
    
    # Риски
    stockout_risk = Column(Float, nullable=True)  # Риск дефицита (0-1)
    overstock_risk = Column(Float, nullable=True)  # Риск излишков (0-1)
    
    # Классификация
    abc_class = Column(String(1), nullable=True, index=True)  # A, B, C
    xyz_class = Column(String(1), nullable=True, index=True)  # X, Y, Z
    
    # Уровень сервиса
    service_level = Column(Float, nullable=True)  # Уровень сервиса (0-1)
    
    # Снимки остатков по дням (для анализа трендов)
    daily_snapshots = Column(JSON, nullable=True)  # Массив снимков остатков по дням
    
    # Служебные поля
    calculated_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Индексы для быстрых запросов
    __table_args__ = (
        Index('ix_inventory_analytics_product_date', 'product_id_1c', 'analysis_date'),
        Index('ix_inventory_analytics_store_date', 'store_id', 'analysis_date'),
        Index('ix_inventory_analytics_abc_xyz', 'abc_class', 'xyz_class'),
        Index('ix_inventory_analytics_category', 'category', 'analysis_date'),
        Index('ix_inventory_analytics_risk', 'stockout_risk', 'overstock_risk'),
    )
