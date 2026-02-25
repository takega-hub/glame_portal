from sqlalchemy import Column, String, DateTime, JSON, Float, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.database.connection import Base


class MarketingCampaign(Base):
    __tablename__ = "marketing_campaigns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    type = Column(String(50), nullable=False)  # email, social, content, paid, etc.
    status = Column(String(50), nullable=False, default="draft")  # draft, active, paused, completed, archived
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=True)
    budget = Column(Float, nullable=True)  # в рублях
    target_audience = Column(JSON, nullable=True)  # {personas: [], demographics: {}, etc.}
    channels = Column(JSON, nullable=True)  # ["instagram", "telegram", etc.]
    content_plan_id = Column(UUID(as_uuid=True), ForeignKey("content_plans.id"), nullable=True, index=True)
    metrics = Column(JSON, nullable=True, default=dict)  # {impressions, clicks, conversions, revenue, etc.}
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
