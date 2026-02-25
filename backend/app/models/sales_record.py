"""
Модель для детальных записей о продажах из 1С
Хранит каждую продажу отдельно для детального анализа
"""
from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database.connection import Base


class SalesRecord(Base):
    """Детальная запись о продаже из 1С"""
    __tablename__ = "sales_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Дата продажи (из Period в 1С)
    sale_date = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # Идентификаторы из 1С
    external_id = Column(String(255), nullable=True, index=True)  # Recorder или Документ из 1С
    document_id = Column(String(255), nullable=True, index=True)  # ID документа продажи
    
    # Связи
    store_id = Column(String(255), nullable=True, index=True)  # Склад_Key из 1С (может быть GUID строкой)
    customer_id = Column(String(255), nullable=True, index=True)  # Контрагент_Key из 1С
    product_id = Column(String(255), nullable=True, index=True)  # Номенклатура_Key из 1С
    organization_id = Column(String(255), nullable=True)  # Организация_Key из 1С
    
    # Метрики продажи
    revenue = Column(Float, nullable=False, default=0.0)  # Сумма
    quantity = Column(Float, nullable=False, default=0.0)  # Количество
    revenue_without_discount = Column(Float, nullable=True)  # СуммаБезСкидки
    
    # Данные о товаре (для аналитики)
    product_name = Column(String(500), nullable=True)  # Название товара на момент продажи
    product_article = Column(String(100), nullable=True, index=True)  # Артикул товара
    product_category = Column(String(100), nullable=True, index=True)  # Категория товара
    product_brand = Column(String(100), nullable=True, index=True)  # Бренд товара
    product_type = Column(String(100), nullable=True, index=True)  # Тип изделия (кольца, серьги и т.д.)
    cost_price = Column(Float, nullable=True)  # Себестоимость (если доступна)
    margin = Column(Float, nullable=True)  # Маржа
    
    # Канал продажи
    channel = Column(String(64), nullable=True, default="offline", index=True)  # offline, online, etc.
    
    # Метаданные из 1С (все дополнительные поля)
    raw_data = Column(JSON, nullable=True)  # Полные данные из 1С для справки
    
    # Служебные поля
    synced_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)  # Когда синхронизировано
    sync_batch_id = Column(String(255), nullable=True, index=True)  # ID пакета синхронизации
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Индексы для быстрых запросов
    __table_args__ = (
        Index('ix_sales_records_date_store', 'sale_date', 'store_id'),
        Index('ix_sales_records_date_customer', 'sale_date', 'customer_id'),
        Index('ix_sales_records_date_product', 'sale_date', 'product_id'),
        Index('ix_sales_records_sync_batch', 'sync_batch_id'),
        Index('ix_sales_records_external_id', 'external_id', unique=True),  # Уникальный индекс для on_conflict_do_update
    )
