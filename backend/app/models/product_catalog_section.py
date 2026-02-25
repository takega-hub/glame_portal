"""
Промежуточная таблица для связи many-to-many между товарами и разделами каталога.
Один товар может быть в нескольких разделах каталога.
"""
from sqlalchemy import Column, ForeignKey, Index, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database.connection import Base


class ProductCatalogSection(Base):
    __tablename__ = "product_catalog_sections"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Связи
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    catalog_section_id = Column(UUID(as_uuid=True), ForeignKey("catalog_sections.id", ondelete="CASCADE"), nullable=False)
    
    # Временные метки
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Уникальный индекс для предотвращения дубликатов
    __table_args__ = (
        Index('ix_product_catalog_sections_product_section', 'product_id', 'catalog_section_id', unique=True),
        Index('ix_product_catalog_sections_product', 'product_id'),
        Index('ix_product_catalog_sections_section', 'catalog_section_id'),
    )
