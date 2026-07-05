import uuid

from sqlalchemy import Column, DateTime, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database.connection import Base


class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    provider = Column(String(32), nullable=False, default="yookassa")
    external_id = Column(String(128), nullable=True, unique=True, index=True)
    status = Column(String(32), nullable=False, default="pending")
    currency = Column(String(8), nullable=False, default="RUB")
    amount = Column(Integer, nullable=False, default=0)
    idempotence_key = Column(String(64), nullable=True)
    confirmation_url = Column(String(1000), nullable=True)
    raw = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

