from sqlalchemy import Column, String, JSON, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database.connection import Base


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    event_type = Column(String(50), nullable=False, index=True)  # chat_message, product_click, look_view, etc.
    event_data = Column(JSON, nullable=True, default=dict)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Связи с сущностями
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True, index=True)
    look_id = Column(UUID(as_uuid=True), ForeignKey("looks.id"), nullable=True, index=True)
    content_item_id = Column(UUID(as_uuid=True), ForeignKey("content_items.id"), nullable=True, index=True)
    
    # Канал и UTM параметры
    channel = Column(String(64), nullable=True, index=True)  # instagram, website, email, etc.
    utm_source = Column(String(255), nullable=True)
    utm_medium = Column(String(255), nullable=True)
    utm_campaign = Column(String(255), nullable=True)
    
    # Составные индексы для быстрых запросов
    __table_args__ = (
        Index('ix_analytics_events_user_timestamp', 'user_id', 'timestamp'),
        Index('ix_analytics_events_type_timestamp', 'event_type', 'timestamp'),
        Index('ix_analytics_events_channel_timestamp', 'channel', 'timestamp'),
    )
