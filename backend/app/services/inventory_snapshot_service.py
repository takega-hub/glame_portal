from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_snapshot import InventorySnapshot


class InventorySnapshotService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_fresh_snapshot(
        self,
        snapshot_type: str,
        analysis_period_days: int,
        store_id: Optional[str],
        period_start: Optional[datetime],
        period_end: Optional[datetime],
        max_age_seconds: int,
    ) -> Optional[dict]:
        stmt = select(InventorySnapshot).where(
            InventorySnapshot.snapshot_type == snapshot_type,
            InventorySnapshot.analysis_period_days == analysis_period_days,
            InventorySnapshot.store_id == store_id,
            InventorySnapshot.period_start == period_start,
            InventorySnapshot.period_end == period_end,
        )
        result = await self.db.execute(stmt)
        snap = result.scalar_one_or_none()
        if not snap:
            return None

        computed_at = snap.computed_at
        if computed_at is None:
            return None

        now = datetime.now(timezone.utc)
        if computed_at.tzinfo is None:
            computed_at = computed_at.replace(tzinfo=timezone.utc)
        age = (now - computed_at).total_seconds()
        if age > max_age_seconds:
            return None

        if isinstance(snap.payload, dict):
            return snap.payload
        return None

    async def upsert_snapshot(
        self,
        snapshot_type: str,
        analysis_period_days: int,
        store_id: Optional[str],
        period_start: Optional[datetime],
        period_end: Optional[datetime],
        payload: dict,
    ) -> None:
        stmt = select(InventorySnapshot).where(
            InventorySnapshot.snapshot_type == snapshot_type,
            InventorySnapshot.analysis_period_days == analysis_period_days,
            InventorySnapshot.store_id == store_id,
            InventorySnapshot.period_start == period_start,
            InventorySnapshot.period_end == period_end,
        )
        result = await self.db.execute(stmt)
        snap = result.scalar_one_or_none()

        if snap:
            snap.payload = payload
            snap.computed_at = datetime.now(timezone.utc)
            snap.period_start = period_start
            snap.period_end = period_end
            self.db.add(snap)
        else:
            self.db.add(
                InventorySnapshot(
                    snapshot_type=snapshot_type,
                    store_id=store_id,
                    analysis_period_days=analysis_period_days,
                    period_start=period_start,
                    period_end=period_end,
                    payload=payload,
                    computed_at=datetime.now(timezone.utc),
                )
            )

        await self.db.commit()
