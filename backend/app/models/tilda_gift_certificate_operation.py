import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database.connection import Base


class TildaGiftCertificateOperation(Base):
    """Idempotent journal for the public Tilda gift-certificate contour.

    The certificate balance is kept on ``gift_certificates``.  This table keeps
    the checkout context and every state transition, so a payment webhook can
    always be retried without debiting a certificate twice.
    """

    __tablename__ = "tilda_gift_certificate_operations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    certificate_id = Column(UUID(as_uuid=True), ForeignKey("gift_certificates.id"), nullable=False, index=True)

    operation_type = Column(String(32), nullable=False, index=True)
    status = Column(String(32), nullable=False, index=True)
    sync_status = Column(String(32), nullable=False, default="synced", index=True)
    idempotency_key = Column(String(255), nullable=True, unique=True, index=True)
    request_hash = Column(String(64), nullable=True)
    validation_token_hash = Column(String(64), nullable=True, unique=True, index=True)

    tilda_order_id = Column(String(128), nullable=True, index=True)
    payment_id = Column(String(128), nullable=True, index=True)
    refund_id = Column(String(128), nullable=True, index=True)
    original_operation_id = Column(UUID(as_uuid=True), ForeignKey("tilda_gift_certificate_operations.id"), nullable=True)
    amount = Column(Integer, nullable=False, default=0)
    cart_total = Column(Integer, nullable=True)
    cart_fingerprint = Column(String(128), nullable=True)
    reservation_expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_sync_attempt_at = Column(DateTime(timezone=True), nullable=True)
    onec_document_id = Column(String(128), nullable=True)
    error = Column(Text, nullable=True)
    meta = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tilda_order_id", "operation_type", name="uq_tilda_gift_operation_order_type"),
        Index("ix_tilda_gift_operations_sync_created", "sync_status", "created_at"),
        Index("ix_tilda_gift_operations_certificate_type", "certificate_id", "operation_type"),
    )
