import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.database.connection import Base


class LiveStylistConversation(Base):
    __tablename__ = "live_stylist_conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    assigned_stylist_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)

    source = Column(String(100), nullable=True)
    scenario = Column(String(100), nullable=True)
    status = Column(String(32), nullable=False, default="requested", index=True)
    priority = Column(String(16), nullable=False, default="normal", index=True)
    initial_working_hours_status = Column(String(16), nullable=True)

    unread_for_stylist_count = Column(Integer, nullable=False, default=0)
    unread_for_customer_count = Column(Integer, nullable=False, default=0)

    recommended_product_ids = Column(JSONB, nullable=False, default=list)
    internal_notes = Column(Text, nullable=True)
    result_purchase_status = Column(String(32), nullable=False, default="unknown", index=True)
    result_order_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    result_notes = Column(Text, nullable=True)
    meta = Column(JSONB, nullable=False, default=dict)

    assigned_at = Column(DateTime(timezone=True), nullable=True)
    first_response_at = Column(DateTime(timezone=True), nullable=True)
    last_message_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_customer_message_at = Column(DateTime(timezone=True), nullable=True)
    last_stylist_message_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True)

    __table_args__ = (
        Index("ix_live_stylist_customer_status", "customer_user_id", "status"),
        Index("ix_live_stylist_assigned_status", "assigned_stylist_user_id", "status"),
        Index("ix_live_stylist_last_message", "last_message_at", "created_at"),
    )
