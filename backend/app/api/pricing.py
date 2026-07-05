from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database.connection import get_db
from app.api.inventory import get_pricing_report


router = APIRouter()


@router.get("/report")
async def pricing_report(
    analysis_period_days: int = Query(90, ge=1, le=365),
    period: Optional[str] = Query(None, description="week|month|quarter|year|custom"),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD (для custom)"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD (для custom)"),
    store_id: Optional[str] = Query(None),
    limit: int = Query(2000, ge=1, le=20000),
    use_cache: bool = Query(True),
    force_refresh: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    return await get_pricing_report(
        analysis_period_days=analysis_period_days,
        period=period,
        start_date=start_date,
        end_date=end_date,
        store_id=store_id,
        limit=limit,
        use_cache=use_cache,
        force_refresh=force_refresh,
        db=db,
    )
