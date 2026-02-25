"""
Связь пользователей с сегментами
"""
from sqlalchemy import Column, String, DateTime, Float, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from app.database.connection import Base


class UserSegment(Base):
    __tablename__ = "user_segments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    segment_id = Column(UUID(as_uuid=True), ForeignKey("customer_segments.id"), nullable=False, index=True)
    
    # Метаданные
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    assigned_by = Column(String(50), nullable=True)  # auto, manual, ai
    confidence_score = Column(Float, nullable=True)  # для AI сегментации (0-1)
    
    # Отношения
    user = relationship("User", backref="user_segments")
    segment = relationship("CustomerSegment", backref="user_segments")
    
    # Индексы
    __table_args__ = (
        Index('ix_user_segments_user_segment', 'user_id', 'segment_id', unique=True),
        Index('ix_user_segments_assigned', 'assigned_at'),
    )
