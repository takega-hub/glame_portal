from sqlalchemy import Column, String, DateTime, Integer, Float, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database.connection import Base


class WebsiteVisit(Base):
    __tablename__ = "website_visits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    page_url = Column(String(500), nullable=False, index=True)
    referrer = Column(String(500), nullable=True)
    device_type = Column(String(50), nullable=True)  # desktop, mobile, tablet
    browser = Column(String(100), nullable=True)
    duration = Column(Float, nullable=True)  # в секундах
    is_bounce = Column(String(10), nullable=True, default='unknown')  # yes, no, unknown
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Составные индексы для быстрых запросов
    __table_args__ = (
        Index('ix_website_visits_user_created', 'user_id', 'created_at'),
        Index('ix_website_visits_session_created', 'session_id', 'created_at'),
    )
