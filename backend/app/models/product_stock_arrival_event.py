from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid

from app.database.connection import Base


class ProductStockArrivalEvent(Base):
    """Detected stock increase / arrival event for CRM clienteling."""

    __tablename__ = "product_stock_arrival_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    store_id = Column(String(255), nullable=False, index=True)

    previous_available_quantity = Column(Float, nullable=False, default=0.0)
    available_quantity = Column(Float, nullable=False, default=0.0)
    delta_quantity = Column(Float, nullable=False, default=0.0)

    event_type = Column(String(64), nullable=False, default="RESTOCK", index=True)
    source = Column(String(64), nullable=False, default="onec_stock_sync", index=True)
    source_sync_id = Column(String(128), nullable=False, index=True)
    source_idempotency_key = Column(String(255), nullable=False, unique=True, index=True)
    source_payload = Column(JSONB, nullable=True)

    received_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    processed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        UniqueConstraint("source_idempotency_key", name="uq_product_stock_arrival_events_idempotency"),
        Index("ix_stock_arrival_events_store_received", "store_id", "received_at"),
        Index("ix_stock_arrival_events_processed_received", "processed_at", "received_at"),
    )
