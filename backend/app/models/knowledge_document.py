from sqlalchemy import Column, String, Integer, JSON, Text, DateTime, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database.connection import Base


class KnowledgeDocument(Base):
    """Модель для хранения истории загрузки документов в базу знаний"""
    __tablename__ = "knowledge_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False)  # Имя загруженного файла
    file_type = Column(String(50), nullable=False)  # pdf, json
    file_size = Column(Integer, nullable=True)  # Размер файла в байтах
    source = Column(String(255), nullable=True)  # Источник документа
    collection_name = Column(String(100), nullable=False, default="brand_philosophy")  # Целевая коллекция Qdrant
    
    # Статистика загрузки
    total_items = Column(Integer, default=0, nullable=False)  # Всего элементов в документе
    uploaded_items = Column(Integer, default=0, nullable=False)  # Успешно загружено
    failed_items = Column(Integer, default=0, nullable=False)  # Ошибок при загрузке
    
    # Связь с векторной БД
    vector_document_ids = Column(JSON, nullable=True, default=list)  # ID документов в Qdrant
    
    # Метаданные
    document_metadata = Column(JSON, nullable=True, default=dict)  # Дополнительные метаданные
    
    # Статус
    status = Column(String(50), default="completed", nullable=False)  # completed, processing, failed
    error_message = Column(Text, nullable=True)  # Сообщение об ошибке, если есть
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Индексы
    __table_args__ = (
        Index('ix_knowledge_documents_filename', 'filename'),
        Index('ix_knowledge_documents_status', 'status'),
        Index('ix_knowledge_documents_created_at', 'created_at'),
        Index('ix_knowledge_documents_collection_name', 'collection_name'),
    )
