from sqlalchemy import Column, String, JSON, DateTime, Numeric, Index
from sqlalchemy.sql import func
import uuid
from app.database.connection import Base


class AnalyticsMetric(Base):
    __tablename__ = "analytics_metrics"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    metric_type = Column(String(50), nullable=False, index=True)  # conversion, aov, engagement, etc.
    period = Column(String(20), nullable=False, index=True)  # daily, weekly, monthly
    period_start = Column(DateTime(timezone=True), nullable=False, index=True)
    period_end = Column(DateTime(timezone=True), nullable=False)
    value = Column(Numeric(15, 2), nullable=False)
    dimensions = Column(JSON, nullable=True, default=dict)  # дополнительные параметры (channel, cjm_stage, etc.)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Составные индексы для быстрых запросов
    __table_args__ = (
        Index('ix_analytics_metrics_type_period', 'metric_type', 'period', 'period_start'),
    )
