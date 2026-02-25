from sqlalchemy import Column, String, DateTime, Integer, Float, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database.connection import Base


class StoreVisit(Base):
    __tablename__ = "store_visits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(UUID(as_uuid=True), ForeignKey("stores.id"), nullable=False, index=True)
    date = Column(DateTime(timezone=True), nullable=False, index=True)
    visitor_count = Column(Integer, nullable=False, default=0)
    sales_count = Column(Integer, nullable=False, default=0)
    revenue = Column(Float, nullable=False, default=0.0)  # в рублях
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Составные индексы для быстрых запросов
    __table_args__ = (
        Index('ix_store_visits_store_date', 'store_id', 'date'),
    )
