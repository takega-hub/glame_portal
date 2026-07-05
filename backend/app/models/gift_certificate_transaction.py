import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database.connection import Base


class GiftCertificateTransaction(Base):
    __tablename__ = "gift_certificate_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    certificate_id = Column(UUID(as_uuid=True), ForeignKey("gift_certificates.id"), nullable=False, index=True)
    transaction_type = Column(String(32), nullable=False, index=True)
    amount = Column(Integer, nullable=False, default=0)
    balance_after = Column(Integer, nullable=False, default=0)
    reserved_after = Column(Integer, nullable=False, default=0)

    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=True, index=True)
    store_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    source = Column(String(32), nullable=True)
    external_operation_id = Column(String(128), nullable=True)
    onec_document_id = Column(String(128), nullable=True)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_gift_certificate_transactions_cert_date", "certificate_id", "created_at"),
        Index("ix_gift_certificate_transactions_external", "source", "external_operation_id"),
    )

