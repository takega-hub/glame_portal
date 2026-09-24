from sqlalchemy import Column, String, DateTime, Date, Text, ForeignKey, Integer, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.database.connection import Base


class CrmTask(Base):
    """Операционная CRM-задача продавца по клиенту."""

    __tablename__ = "crm_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    assigned_seller_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    assigned_seller_external_id = Column(String(255), nullable=True, index=True)
    assigned_seller_name = Column(String(255), nullable=True, index=True)

    store_id = Column(String(255), nullable=True)
    store_name = Column(String(255), nullable=True, index=True)

    work_date = Column(Date, nullable=False, index=True)
    due_date = Column(DateTime(timezone=True), nullable=True, index=True)
    priority = Column(Integer, nullable=False, default=3)

    crm_group = Column(String(64), nullable=False, index=True)
    reason = Column(Text, nullable=True)
    seller_action = Column(Text, nullable=True)

    script_key = Column(String(128), nullable=True)
    script_text = Column(Text, nullable=True)

    status = Column(String(32), nullable=False, default="new", index=True)
    seller_outcome = Column(String(64), nullable=True)
    seller_comment = Column(Text, nullable=True)
    next_action_date = Column(Date, nullable=True, index=True)

    campaign_id = Column(String(255), nullable=True, index=True)
    campaign_name = Column(String(255), nullable=True)
    source = Column(String(64), nullable=False, default="manual")
    source_row_id = Column(String(255), nullable=True)
    source_idempotency_key = Column(String(255), nullable=True, unique=True, index=True)
    source_payload = Column(JSONB, nullable=True)

    last_contacted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True, index=True)

    attributed_purchase_count = Column(Integer, nullable=False, default=0)
    attributed_revenue_kopecks = Column(Integer, nullable=False, default=0)
    attributed_purchase_ids = Column(JSONB, nullable=True)
    attributed_at = Column(DateTime(timezone=True), nullable=True)

    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())

    customer = relationship("User", foreign_keys=[customer_id])
    assigned_seller = relationship("User", foreign_keys=[assigned_seller_user_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    events = relationship("CrmTaskEvent", back_populates="task", cascade="all, delete-orphan", order_by="CrmTaskEvent.created_at")

    __table_args__ = (
        Index("ix_crm_tasks_seller_date", "assigned_seller_external_id", "work_date"),
        Index("ix_crm_tasks_seller_user_date", "assigned_seller_user_id", "work_date"),
        Index("ix_crm_tasks_store_date", "store_name", "work_date"),
    )


class CrmTaskEvent(Base):
    """История изменений CRM-задачи."""

    __tablename__ = "crm_task_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("crm_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_name = Column(String(255), nullable=True)
    previous_status = Column(String(32), nullable=True)
    next_status = Column(String(32), nullable=True)
    payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    task = relationship("CrmTask", back_populates="events")
    actor = relationship("User", foreign_keys=[actor_user_id])

    __table_args__ = (
        Index("ix_crm_task_events_task_created", "task_id", "created_at"),
        Index("ix_crm_task_events_type_created", "event_type", "created_at"),
    )
