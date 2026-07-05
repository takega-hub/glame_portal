import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from app.database.connection import AsyncSessionLocal
from app.services.inventory_snapshot_service import InventorySnapshotService

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: str = "false") -> bool:
    value = os.getenv(name, default).strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def _seconds_until(hour: int, minute: int) -> float:
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def run_inventory_recalc() -> None:
    from app.api.inventory import (
        get_inventory_dashboard,
        get_inventory_report,
        get_inventory_order,
        get_inventory_clearance,
        get_inventory_assortment,
        get_inventory_marketing_link,
        get_pricing_report,
    )

    analysis_period_days = int(os.getenv("INVENTORY_ANALYSIS_PERIOD_DAYS", "90"))
    store_id = os.getenv("INVENTORY_RECALC_STORE_ID")
    store_id = store_id.strip() if store_id else None

    async with AsyncSessionLocal() as db:
        await get_inventory_dashboard(
            analysis_period_days=analysis_period_days,
            period=None,
            start_date=None,
            end_date=None,
            store_id=store_id,
            use_cache=False,
            force_refresh=True,
            db=db,
        )
        await get_inventory_report(
            analysis_period_days=analysis_period_days,
            period=None,
            start_date=None,
            end_date=None,
            store_id=store_id,
            category=None,
            color=None,
            brand=None,
            collection=None,
            limit=5000,
            use_cache=False,
            force_refresh=True,
            db=db,
        )
        await get_inventory_order(
            analysis_period_days=analysis_period_days,
            period=None,
            start_date=None,
            end_date=None,
            store_id=store_id,
            category=None,
            color=None,
            brand=None,
            collection=None,
            limit=5000,
            use_cache=False,
            force_refresh=True,
            db=db,
        )
        await get_inventory_clearance(
            analysis_period_days=analysis_period_days,
            period=None,
            start_date=None,
            end_date=None,
            store_id=store_id,
            limit=5000,
            use_cache=False,
            force_refresh=True,
            db=db,
        )
        await get_inventory_assortment(
            analysis_period_days=analysis_period_days,
            period=None,
            start_date=None,
            end_date=None,
            store_id=store_id,
            use_cache=False,
            force_refresh=True,
            db=db,
        )
        await get_inventory_marketing_link(
            analysis_period_days=analysis_period_days,
            period=None,
            start_date=None,
            end_date=None,
            store_id=store_id,
            limit=5000,
            use_cache=False,
            force_refresh=True,
            db=db,
        )

        snap = InventorySnapshotService(db)
        today = datetime.now(timezone.utc).date()
        start_d = today - timedelta(days=analysis_period_days - 1)
        period_start = datetime.combine(start_d, datetime.min.time(), tzinfo=timezone.utc)
        period_end = datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
        fresh_pricing = await snap.get_fresh_snapshot(
            snapshot_type="pricing_report",
            analysis_period_days=analysis_period_days,
            store_id=store_id,
            period_start=period_start,
            period_end=period_end,
            max_age_seconds=604800,
        )
        if not fresh_pricing:
            await get_pricing_report(
                analysis_period_days=analysis_period_days,
                period=None,
                start_date=None,
                end_date=None,
                store_id=store_id,
                limit=5000,
                use_cache=False,
                force_refresh=True,
                db=db,
            )


async def inventory_recalc_loop(stop_event: asyncio.Event) -> None:
    hour = int(os.getenv("INVENTORY_RECALC_HOUR", "3"))
    minute = int(os.getenv("INVENTORY_RECALC_MINUTE", "0"))

    while not stop_event.is_set():
        try:
            wait_seconds = max(60, _seconds_until(hour, minute))
            await asyncio.wait_for(stop_event.wait(), timeout=wait_seconds)
        except asyncio.TimeoutError:
            try:
                logger.info("Starting scheduled inventory recalc.")
                await run_inventory_recalc()
                logger.info("Scheduled inventory recalc finished.")
            except Exception as exc:
                logger.error("Scheduled inventory recalc failed: %s", exc, exc_info=True)


async def start_inventory_recalc_scheduler(app) -> None:
    if not _env_bool("INVENTORY_RECALC_ENABLED", "true"):
        logger.info("Inventory recalc scheduler disabled by env.")
        return

    stop_event = asyncio.Event()
    task = asyncio.create_task(inventory_recalc_loop(stop_event))

    app.state.inventory_recalc_stop_event = stop_event
    app.state.inventory_recalc_task = task

    logger.info(
        "Inventory recalc scheduler started (time=%s:%s).",
        os.getenv("INVENTORY_RECALC_HOUR", "3"),
        os.getenv("INVENTORY_RECALC_MINUTE", "0"),
    )


async def stop_inventory_recalc_scheduler(app) -> None:
    stop_event = getattr(app.state, "inventory_recalc_stop_event", None)
    task = getattr(app.state, "inventory_recalc_task", None)
    if stop_event:
        stop_event.set()
    if task:
        await task
