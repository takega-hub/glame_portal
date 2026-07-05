import uuid

from sqlalchemy import Column, DateTime, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database.connection import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    status = Column(String(32), nullable=False, default="pending")
    currency = Column(String(8), nullable=False, default="RUB")
    subtotal_amount = Column(Integer, nullable=False, default=0)
    delivery_amount = Column(Integer, nullable=False, default=0)
    discount_amount = Column(Integer, nullable=False, default=0)
    total_amount = Column(Integer, nullable=False, default=0)

    delivery = Column(JSON, nullable=True)
    contact = Column(JSON, nullable=True)
    meta = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
