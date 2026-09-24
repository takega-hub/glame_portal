import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database.connection import Base


class ProductArrivalSubscription(Base):
    __tablename__ = "product_arrival_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    variant_product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    email = Column(String(255), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    source = Column(String(64), nullable=True)
    variant_label = Column(String(255), nullable=True)
    product_snapshot = Column(JSON, nullable=True, default=dict)
    requested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    notified_at = Column(DateTime(timezone=True), nullable=True)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)

    __table_args__ = (
        Index(
            "ix_product_arrival_pending_variant",
            "status",
            "variant_product_id",
        ),
        Index(
            "ix_product_arrival_email_variant_status",
            "email",
            "variant_product_id",
            "status",
        ),
    )
