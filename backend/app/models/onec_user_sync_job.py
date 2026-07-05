from sqlalchemy import Column, String, DateTime, JSON, Integer, Index, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database.connection import Base


class OneCUserSyncJob(Base):
    __tablename__ = "onec_user_sync_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    status = Column(String(32), nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=8)

    next_attempt_at = Column(DateTime(timezone=True), nullable=True)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)

    last_error = Column(String(2000), nullable=True)
    request_payload = Column(JSON, nullable=True)
    response_payload = Column(JSON, nullable=True)

    customer_id_1c = Column(String(64), nullable=True, index=True)
    discount_card_id_1c = Column(String(64), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_onec_user_sync_jobs_status", "status"),
        Index("ix_onec_user_sync_jobs_next_attempt_at", "next_attempt_at"),
        Index("ix_onec_user_sync_jobs_user_id_status", "user_id", "status"),
    )

