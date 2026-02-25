"""
Планировщик синхронизации покупателей из 1С.
"""
import asyncio
import logging
import os
from typing import Optional
from datetime import datetime, timedelta

from app.database.connection import AsyncSessionLocal
from app.services.customer_sync_service import CustomerSyncService

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: str = "true") -> bool:
    value = os.getenv(name, default).strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


async def run_customer_sync_once() -> None:
    """Однократная синхронизация покупателей и покупок."""
    api_url = os.getenv("ONEC_API_URL")
    if not api_url:
        logger.warning("ONEC_API_URL is not set. Skipping customer sync.")
        return

    limit = int(os.getenv("CUSTOMER_SYNC_CARDS_LIMIT", "1000"))
    days = int(os.getenv("CUSTOMER_SYNC_PURCHASE_DAYS", "365"))

    async with AsyncSessionLocal() as session:
        sync_service = CustomerSyncService(session)

        logger.info("Starting 1C customer sync (cards, limit=%s)", limit)
        await sync_service.sync_discount_cards(limit=limit)

        logger.info("Starting 1C purchase sync (days=%s)", days)
        await sync_service.sync_purchase_history(days=days)

        if _env_bool("ONEC_LOYALTY_ENABLED", "true"):
            logger.info("Starting 1C loyalty sync")
            await sync_service.sync_loyalty_points()

        logger.info("1C customer sync finished")


async def run_nightly_customer_sync() -> None:
    """Ночная синхронизация: новые покупатели, покупки и бонусы."""
    api_url = os.getenv("ONEC_API_URL")
    if not api_url:
        logger.warning("ONEC_API_URL is not set. Skipping nightly customer sync.")
        return

    nightly_days = int(os.getenv("CUSTOMER_SYNC_NIGHTLY_PURCHASE_DAYS", "30"))
    nightly_limit = int(os.getenv("CUSTOMER_SYNC_NIGHTLY_CARDS_LIMIT", "10000"))

    async with AsyncSessionLocal() as session:
        sync_service = CustomerSyncService(session)

        logger.info("Starting nightly 1C customer sync")
        await sync_service.sync_discount_cards(limit=nightly_limit)
        await sync_service.sync_purchase_history(days=nightly_days)

        if _env_bool("ONEC_LOYALTY_ENABLED", "true"):
            await sync_service.sync_loyalty_points()

        logger.info("Nightly 1C customer sync finished")


async def customer_sync_loop(stop_event: asyncio.Event) -> None:
    """Цикл синхронизации с интервалом."""
    interval_hours = int(os.getenv("CUSTOMER_SYNC_INTERVAL_HOURS", "4"))
    interval_seconds = max(300, interval_hours * 3600)  # минимум 5 минут
    # По умолчанию НЕ запускаем синхронизацию при старте (только по расписанию и вручную)
    run_on_start = _env_bool("CUSTOMER_SYNC_RUN_ON_START", "false")

    if run_on_start:
        try:
            await run_customer_sync_once()
        except Exception as exc:
            logger.error("Initial 1C customer sync failed: %s", exc, exc_info=True)

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            try:
                await run_customer_sync_once()
            except Exception as exc:
                logger.error("Scheduled 1C customer sync failed: %s", exc, exc_info=True)


async def start_customer_sync_scheduler(app) -> None:
    """Запуск планировщика."""
    if not _env_bool("CUSTOMER_SYNC_ENABLED", "true"):
        logger.info("Customer sync scheduler disabled by env.")
        return

    stop_event = asyncio.Event()
    task = asyncio.create_task(customer_sync_loop(stop_event))

    app.state.customer_sync_stop_event = stop_event
    app.state.customer_sync_task = task

    logger.info("Customer sync scheduler started (interval=%s hours).", os.getenv("CUSTOMER_SYNC_INTERVAL_HOURS", "4"))


def _seconds_until(hour: int, minute: int) -> float:
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def nightly_customer_sync_loop(stop_event: asyncio.Event) -> None:
    """Цикл ночной синхронизации."""
    hour = int(os.getenv("CUSTOMER_SYNC_NIGHTLY_HOUR", "3"))
    minute = int(os.getenv("CUSTOMER_SYNC_NIGHTLY_MINUTE", "0"))

    while not stop_event.is_set():
        try:
            wait_seconds = max(60, _seconds_until(hour, minute))
            await asyncio.wait_for(stop_event.wait(), timeout=wait_seconds)
        except asyncio.TimeoutError:
            try:
                await run_nightly_customer_sync()
            except Exception as exc:
                logger.error("Nightly 1C customer sync failed: %s", exc, exc_info=True)


async def start_nightly_customer_sync_scheduler(app) -> None:
    """Запуск ночного планировщика."""
    if not _env_bool("CUSTOMER_SYNC_NIGHTLY_ENABLED", "true"):
        logger.info("Nightly customer sync scheduler disabled by env.")
        return

    stop_event = asyncio.Event()
    task = asyncio.create_task(nightly_customer_sync_loop(stop_event))

    app.state.nightly_customer_sync_stop_event = stop_event
    app.state.nightly_customer_sync_task = task

    logger.info(
        "Nightly customer sync scheduler started (time=%s:%s).",
        os.getenv("CUSTOMER_SYNC_NIGHTLY_HOUR", "3"),
        os.getenv("CUSTOMER_SYNC_NIGHTLY_MINUTE", "0"),
    )


async def stop_nightly_customer_sync_scheduler(app) -> None:
    """Остановка ночного планировщика."""
    stop_event: Optional[asyncio.Event] = getattr(app.state, "nightly_customer_sync_stop_event", None)
    task: Optional[asyncio.Task] = getattr(app.state, "nightly_customer_sync_task", None)

    if stop_event:
        stop_event.set()

    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def stop_customer_sync_scheduler(app) -> None:
    """Остановка планировщика."""
    stop_event: Optional[asyncio.Event] = getattr(app.state, "customer_sync_stop_event", None)
    task: Optional[asyncio.Task] = getattr(app.state, "customer_sync_task", None)

    if stop_event:
        stop_event.set()

    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
