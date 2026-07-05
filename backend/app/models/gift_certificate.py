import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database.connection import Base


class GiftCertificate(Base):
    __tablename__ = "gift_certificates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    number = Column(String(32), nullable=False, unique=True, index=True)
    pin_hash = Column(String(128), nullable=True)

    status = Column(String(32), nullable=False, default="pending", index=True)
    currency = Column(String(8), nullable=False, default="RUB")
    nominal_amount = Column(Integer, nullable=False, default=0)
    balance_amount = Column(Integer, nullable=False, default=0)
    reserved_amount = Column(Integer, nullable=False, default=0)

    buyer_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    recipient_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    recipient_name = Column(String(255), nullable=True)
    recipient_phone = Column(String(32), nullable=True)
    recipient_email = Column(String(255), nullable=True)
    message = Column(Text, nullable=True)

    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=True, index=True)
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id"), nullable=True, index=True)
    onec_certificate_id = Column(String(128), nullable=True)
    onec_sale_document_id = Column(String(128), nullable=True)
    meta = Column(JSON, nullable=True)

    issued_at = Column(DateTime(timezone=True), nullable=True)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    canceled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    __table_args__ = (
        Index("ix_gift_certificates_buyer_status", "buyer_user_id", "status"),
        Index("ix_gift_certificates_recipient_status", "recipient_user_id", "status"),
        Index("ix_gift_certificates_order_status", "order_id", "status"),
    )
