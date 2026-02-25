"""
Модель транзакций баллов лояльности
"""
from sqlalchemy import Column, String, DateTime, JSON, Integer, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.database.connection import Base


class LoyaltyTransaction(Base):
    __tablename__ = "loyalty_transactions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    
    # Транзакция
    transaction_type = Column(String(50), nullable=False)  # earn, spend, expire, bonus, manual
    points = Column(Integer, nullable=False)  # количество баллов (+ начисление, - списание)
    balance_after = Column(Integer, nullable=False)  # баланс после транзакции
    
    # Причина
    reason = Column(String(100), nullable=True)  # purchase, birthday, campaign, etc.
    description = Column(Text, nullable=True)  # описание транзакции
    related_purchase_id = Column(UUID(as_uuid=True), ForeignKey("purchase_history.id"), nullable=True)
    
    # Источник
    source = Column(String(50), nullable=True)  # 1c, platform, manual, ai_campaign
    source_id = Column(String(255), nullable=True)  # ID источника (ID кампании, etc.)
    
    # Даты
    expires_at = Column(DateTime(timezone=True), nullable=True)  # срок действия баллов
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)  # кто создал (для manual)
    
    # Отношения
    user = relationship("User", foreign_keys=[user_id], backref="loyalty_transactions")
    related_purchase = relationship("PurchaseHistory", foreign_keys=[related_purchase_id])
    creator = relationship("User", foreign_keys=[created_by])
    
    # Индексы
    __table_args__ = (
        Index('ix_loyalty_transactions_user_date', 'user_id', 'created_at'),
        Index('ix_loyalty_transactions_type', 'transaction_type'),
        Index('ix_loyalty_transactions_expires', 'expires_at'),
    )
