import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.database.connection import Base


class CustomerRequest(Base):
    """An operational promise to a customer: waiting list, order, repair or service case."""

    __tablename__ = "customer_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    request_type = Column(String(48), nullable=False, index=True)
    physical_store = Column(String(64), nullable=True, index=True)
    crm_store = Column(String(64), nullable=True, index=True)
    assigned_consultant_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(String(48), nullable=False, index=True)
    priority = Column(String(16), nullable=False, default="normal", index=True)
    product_name = Column(String(255), nullable=True)
    sku = Column(String(128), nullable=True, index=True)
    size = Column(String(32), nullable=True)
    brand = Column(String(128), nullable=True)
    original_comment = Column(Text, nullable=True)
    photo_urls = Column(JSONB, nullable=False, default=list)
    structured_context = Column(JSONB, nullable=False, default=dict)
    next_action = Column(Text, nullable=True)
    next_action_at = Column(DateTime(timezone=True), nullable=True, index=True)
    closed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())

    __table_args__ = (Index("ix_customer_requests_open", "status", "next_action_at"),)


class CustomerRequestAudit(Base):
    __tablename__ = "customer_request_audit"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(UUID(as_uuid=True), ForeignKey("customer_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(64), nullable=False)
    old_status = Column(String(48), nullable=True)
    new_status = Column(String(48), nullable=True)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
