"""Планировщик свежей синхронизации продаж 1С по чекам."""
import asyncio
import logging
import os
from datetime import datetime, timedelta

from app.database.connection import AsyncSessionLocal
from app.services.onec_sales_sync_service import OneCSalesSyncService

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: str = "false") -> bool:
    value = os.getenv(name, default).strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


async def run_recent_onec_sales_sync(days_back: int | None = None) -> None:
    days = days_back if days_back is not None else int(os.getenv("ONEC_SALES_SYNC_DAYS_BACK", "3"))
    end_date = datetime.now()
    start_date = (end_date - timedelta(days=max(days, 1))).replace(hour=0, minute=0, second=0, microsecond=0)

    async with AsyncSessionLocal() as db:
        async with OneCSalesSyncService(db) as sync_service:
            result = await sync_service.sync_period(start_date=start_date, end_date=end_date, incremental=True)
            logger.info("Recent 1C sales sync finished: %s", result)


async def onec_sales_sync_loop(stop_event: asyncio.Event) -> None:
    interval_minutes = int(os.getenv("ONEC_SALES_SYNC_INTERVAL_MINUTES", "60"))
    initial_delay = int(os.getenv("ONEC_SALES_SYNC_INITIAL_DELAY_SECONDS", "60"))

    try:
        await asyncio.wait_for(stop_event.wait(), timeout=max(initial_delay, 0))
        return
    except asyncio.TimeoutError:
        pass

    while not stop_event.is_set():
        try:
            await run_recent_onec_sales_sync()
        except Exception:
            logger.error("Recent 1C sales sync failed", exc_info=True)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=max(interval_minutes, 5) * 60)
            break
        except asyncio.TimeoutError:
            pass


async def start_onec_sales_sync_scheduler(app) -> None:
    if not _env_bool("ONEC_SALES_SYNC_ENABLED", "true"):
        logger.info("Recent 1C sales sync scheduler disabled by env.")
        return

    stop_event = asyncio.Event()
    task = asyncio.create_task(onec_sales_sync_loop(stop_event))
    app.state.onec_sales_sync_stop_event = stop_event
    app.state.onec_sales_sync_task = task
    logger.info(
        "Recent 1C sales sync scheduler started (interval=%s minutes, days_back=%s).",
        os.getenv("ONEC_SALES_SYNC_INTERVAL_MINUTES", "60"),
        os.getenv("ONEC_SALES_SYNC_DAYS_BACK", "3"),
    )


async def stop_onec_sales_sync_scheduler(app) -> None:
    stop_event = getattr(app.state, "onec_sales_sync_stop_event", None)
    task = getattr(app.state, "onec_sales_sync_task", None)

    if stop_event:
        stop_event.set()
    if task:
        try:
            await asyncio.wait_for(task, timeout=5.0)
        except asyncio.TimeoutError:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    logger.info("Recent 1C sales sync scheduler stopped")
