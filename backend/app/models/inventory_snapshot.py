from sqlalchemy import Column, String, Integer, DateTime, Index, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database.connection import Base


class InventorySnapshot(Base):
    __tablename__ = "inventory_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_type = Column(String(64), nullable=False)
    store_id = Column(String(255), nullable=True)
    analysis_period_days = Column(Integer, nullable=False, default=90)
    period_start = Column(DateTime(timezone=True), nullable=True)
    period_end = Column(DateTime(timezone=True), nullable=True)
    payload = Column(JSON, nullable=False, default=dict)
    computed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index(
            "ix_inventory_snapshots_type_store_period",
            "snapshot_type",
            "store_id",
            "analysis_period_days",
            "period_start",
            "period_end",
            unique=True,
        ),
        Index("ix_inventory_snapshots_computed_at", "computed_at"),
    )
