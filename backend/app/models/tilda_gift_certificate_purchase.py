import uuid

from sqlalchemy import Column, DateTime, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database.connection import Base


class TildaGiftCertificatePurchase(Base):
    __tablename__ = "tilda_gift_certificate_purchases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(String(32), nullable=False, default="pending_payment", index=True)
    idempotency_key = Column(String(128), nullable=False, unique=True, index=True)
    request_hash = Column(String(64), nullable=False)
    status_token_hash = Column(String(64), nullable=False, unique=True, index=True)
    nominal_amount = Column(Integer, nullable=False)
    design = Column(String(32), nullable=False)
    recipient_name = Column(String(80), nullable=False)
    recipient_email = Column(String(255), nullable=False)
    sender_name = Column(String(80), nullable=False)
    message = Column(Text, nullable=True)
    delivery_mode = Column(String(16), nullable=False)
    send_at = Column(DateTime(timezone=True), nullable=True, index=True)
    buyer_contact = Column(JSON, nullable=False)
    return_url = Column(String(2000), nullable=False)
    payment_id = Column(String(128), nullable=True, unique=True, index=True)
    confirmation_url = Column(String(2000), nullable=True)
    certificate_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    error = Column(Text, nullable=True)
    meta = Column(JSON, nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
