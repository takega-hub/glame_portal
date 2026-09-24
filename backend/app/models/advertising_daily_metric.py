import uuid

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database.connection import Base


class AdvertisingDailyMetric(Base):
    """Read-only daily facts imported from an advertising platform."""

    __tablename__ = "advertising_daily_metrics"
    __table_args__ = (
        UniqueConstraint(
            "advertising_connection_id",
            "external_campaign_id",
            "metric_date",
            name="uq_advertising_daily_metrics_connection_campaign_date",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    advertising_connection_id = Column(UUID(as_uuid=True), ForeignKey("advertising_connections.id"), nullable=False, index=True)
    marketing_campaign_id = Column(UUID(as_uuid=True), ForeignKey("marketing_campaigns.id"), nullable=True, index=True)
    external_campaign_id = Column(String(128), nullable=False, index=True)
    metric_date = Column(Date, nullable=False, index=True)
    impressions = Column(Integer, nullable=False, default=0)
    clicks = Column(Integer, nullable=False, default=0)
    cost = Column(Float, nullable=False, default=0.0)
    conversions = Column(Float, nullable=False, default=0.0)
    raw_metrics = Column(JSON, nullable=False, default=dict)
    imported_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
