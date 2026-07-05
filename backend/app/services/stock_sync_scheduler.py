"""
Ночной планировщик синхронизации остатков по складам из 1С.
Поддерживает OData движения регистра `ЗапасыНаСкладах` и CommerceML XML fallback.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta

from app.database.connection import AsyncSessionLocal
from app.services.onec_stock_service import OneCStockService

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


async def run_nightly_stock_sync() -> None:
    """
    Ночная синхронизация остатков.
    
    Переменные окружения:
    - ONEC_STOCKS_SOURCE=odata|xml|auto (по умолчанию auto)
    - ONEC_XML_OFFERS_URL: URL к offers.xml файлу для XML/fallback режима
    """
    source = (os.getenv("ONEC_STOCKS_SOURCE") or "auto").strip().lower()
    async with AsyncSessionLocal() as session:
        async with OneCStockService(session) as stock_service:
            if source in {"odata", "auto"}:
                try:
                    logger.info("Starting nightly 1C stock sync from OData")
                    result = await stock_service.sync_stocks_from_odata_movements(
                        page_size=int(os.getenv("ONEC_STOCKS_ODATA_PAGE_SIZE", "1000")),
                        replace_all=_env_bool("ONEC_STOCKS_ODATA_REPLACE_ALL", "true"),
                    )
                    logger.info("Nightly 1C OData stock sync finished: %s", result)
                    return
                except Exception as exc:
                    if source == "odata":
                        raise
                    logger.warning("OData stock sync failed, falling back to XML: %s", exc, exc_info=True)

            offers_url = os.getenv("ONEC_XML_OFFERS_URL")
            if not offers_url:
                logger.warning("ONEC_XML_OFFERS_URL is not set. Skipping XML stock sync.")
                return

            logger.info("Starting nightly 1C stock sync from XML: %s", offers_url)
            result = await stock_service.sync_stocks_from_xml(offers_url)
            logger.info("Nightly 1C XML stock sync finished: %s", result)


async def nightly_stock_sync_loop(stop_event: asyncio.Event) -> None:
    hour = int(os.getenv("STOCKS_SYNC_NIGHTLY_HOUR", "2"))
    minute = int(os.getenv("STOCKS_SYNC_NIGHTLY_MINUTE", "0"))

    while not stop_event.is_set():
        try:
            wait_seconds = max(60, _seconds_until(hour, minute))
            await asyncio.wait_for(stop_event.wait(), timeout=wait_seconds)
        except asyncio.TimeoutError:
            try:
                await run_nightly_stock_sync()
            except Exception as exc:
                logger.error("Nightly stock sync failed: %s", exc, exc_info=True)


async def start_nightly_stock_sync_scheduler(app) -> None:
    if not _env_bool("STOCKS_SYNC_NIGHTLY_ENABLED", "true"):
        logger.info("Nightly stock sync scheduler disabled by env.")
        return

    stop_event = asyncio.Event()
    task = asyncio.create_task(nightly_stock_sync_loop(stop_event))

    app.state.nightly_stock_sync_stop_event = stop_event
    app.state.nightly_stock_sync_task = task

    logger.info(
        "Nightly stock sync scheduler started (time=%s:%s).",
        os.getenv("STOCKS_SYNC_NIGHTLY_HOUR", "2"),
        os.getenv("STOCKS_SYNC_NIGHTLY_MINUTE", "0"),
    )


async def stop_nightly_stock_sync_scheduler(app) -> None:
    stop_event = getattr(app.state, "nightly_stock_sync_stop_event", None)
    task = getattr(app.state, "nightly_stock_sync_task", None)
    if stop_event:
        stop_event.set()
    if task:
        await task
