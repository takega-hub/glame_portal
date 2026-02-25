from sqlalchemy import Column, String, Integer, Float, JSON, Text, DateTime, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database.connection import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    brand = Column(String(100), nullable=True)
    price = Column(Integer, nullable=False)  # цена в копейках
    category = Column(String(100), nullable=True)
    images = Column(JSON, nullable=True, default=list)  # массив URL изображений
    tags = Column(JSON, nullable=True, default=list)  # массив тегов
    description = Column(Text, nullable=True)

    # Дополнительные поля из 1С (Каталог Номенклатура)
    article = Column(String(100), nullable=True)  # артикул
    vendor_code = Column(String(100), nullable=True)  # код производителя
    barcode = Column(String(100), nullable=True)  # штрихкод
    unit = Column(String(50), nullable=True)  # единица измерения
    weight = Column(Float, nullable=True)
    volume = Column(Float, nullable=True)
    country = Column(String(100), nullable=True)
    warranty = Column(String(100), nullable=True)
    full_description = Column(Text, nullable=True)
    specifications = Column(JSON, nullable=True)  # технические характеристики
    onec_data = Column(JSON, nullable=True)  # полные данные из 1С
    
    # Поля для интеграции с 1С
    external_id = Column(String(255), nullable=True, unique=True)  # ID товара в 1С
    external_code = Column(String(100), nullable=True)  # Код товара в 1С
    is_active = Column(Boolean, default=True, nullable=False)  # Активен ли товар
    sync_status = Column(String(50), nullable=True)  # Статус синхронизации: synced, pending, error
    sync_metadata = Column(JSON, nullable=True)  # Метаданные синхронизации (дата последней синхронизации, источник и т.д.)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Индексы для быстрого поиска
    __table_args__ = (
        Index('ix_products_external_id', 'external_id'),
        Index('ix_products_external_code', 'external_code'),
        Index('ix_products_article', 'article'),  # Индекс для поиска по артикулу
    )
