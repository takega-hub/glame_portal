"""
Модель истории покупок покупателей
Синхронизируется из 1С УНФ ФРЕШ
"""
from sqlalchemy import Column, String, DateTime, JSON, Integer, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.database.connection import Base


class PurchaseHistory(Base):
    __tablename__ = "purchase_history"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    
    # Данные из 1С
    purchase_date = Column(DateTime(timezone=True), nullable=False, index=True)
    document_id_1c = Column(String(255), nullable=True, index=True)  # ID документа продажи в 1С
    store_id_1c = Column(String(255), nullable=True)  # ID магазина/склада в 1С
    
    # Товары и суммы
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True, index=True)  # связь с товаром в GLAME
    product_id_1c = Column(String(255), nullable=True)  # ID номенклатуры в 1С
    product_article = Column(String(100), nullable=True, index=True)  # артикул товара для привязки к каталогу
    product_name = Column(String(500), nullable=True)  # название на момент покупки
    quantity = Column(Integer, default=1, nullable=False)
    price = Column(Integer, nullable=True)  # цена за единицу в копейках
    total_amount = Column(Integer, nullable=False)  # общая сумма в копейках
    
    # Метаданные
    category = Column(String(100), nullable=True)  # категория товара
    brand = Column(String(100), nullable=True)  # бренд товара
    sync_metadata = Column(JSON, nullable=True)  # дополнительные данные из 1С
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Отношения
    user = relationship("User", backref="purchases")
    product = relationship("Product", foreign_keys=[product_id])
    
    # Индексы
    __table_args__ = (
        Index('ix_purchase_history_user_date', 'user_id', 'purchase_date'),
        Index('ix_purchase_history_document_1c', 'document_id_1c'),
        Index('ix_purchase_history_product_1c', 'product_id_1c'),
    )
