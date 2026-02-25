"""
Модель разделов каталога из 1С.
Разделы каталога (группы) синхронизируются из Catalog_Номенклатура где IsFolder=True.
"""
from sqlalchemy import Column, String, DateTime, Boolean, Index, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database.connection import Base


class CatalogSection(Base):
    __tablename__ = "catalog_sections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Данные из 1С
    external_id = Column(String(255), nullable=False, unique=True)  # Ref_Key из 1С
    external_code = Column(String(100), nullable=True)  # Code из 1С
    name = Column(String(255), nullable=False)  # Description из 1С
    parent_external_id = Column(String(255), nullable=True)  # Parent_Key из 1С (для иерархии)
    
    # Дополнительные данные
    description = Column(Text, nullable=True)
    onec_metadata = Column(JSON, nullable=True)  # Полные данные из 1С
    
    # Статус
    is_active = Column(Boolean, default=True, nullable=False)
    sync_status = Column(String(50), nullable=True)  # synced, pending, error
    sync_metadata = Column(JSON, nullable=True)  # Метаданные синхронизации
    
    # Временные метки
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Индексы
    __table_args__ = (
        Index('ix_catalog_sections_external_id', 'external_id'),
        Index('ix_catalog_sections_external_code', 'external_code'),
        Index('ix_catalog_sections_parent_external_id', 'parent_external_id'),
        Index('ix_catalog_sections_is_active', 'is_active'),
    )
