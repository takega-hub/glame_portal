"""Scheduler for recurring post-purchase CRM touchpoint generation."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date

from app.database.connection import AsyncSessionLocal
from app.services.birthday_crm_service import BirthdayCrmService, DEFAULT_BIRTHDAY_DAYS_AHEAD
from app.services.crm_new_arrival_service import CrmNewArrivalService
from app.services.crm_task_service import CrmTaskService
from app.services.crm_touchpoint_service import CrmTouchpointService, DEFAULT_WARRANTY_DAYS
from app.services.onec_purchase_receipt_arrival_service import OneCPurchaseReceiptArrivalService
from app.api.customer_requests import run_due_control

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: str = "true") -> bool:
    value = os.getenv(name, default).strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


async def run_crm_touchpoint_generation(work_date: date | None = None) -> dict:
    target_date = work_date or date.today()
    warranty_days = int(os.getenv("CRM_DEFAULT_WARRANTY_DAYS", str(DEFAULT_WARRANTY_DAYS)))
    limit_documents = int(os.getenv("CRM_TOUCHPOINT_LIMIT_DOCUMENTS_PER_RULE", "2000"))
    async with AsyncSessionLocal() as db:
        result = await CrmTouchpointService(db).generate_for_work_date(
            target_date,
            warranty_days=warranty_days,
            limit_documents_per_rule=limit_documents,
        )
        logger.info("CRM touchpoint generation finished: %s", result)
        return result


async def run_birthday_crm_generation(work_date: date | None = None) -> dict:
    target_date = work_date or date.today()
    days_ahead = int(os.getenv("CRM_BIRTHDAY_DAYS_AHEAD", str(DEFAULT_BIRTHDAY_DAYS_AHEAD)))
    limit = int(os.getenv("CRM_BIRTHDAY_LIMIT", "500"))
    async with AsyncSessionLocal() as db:
        result = await BirthdayCrmService(db).generate_tasks(
            target_date,
            days_ahead=days_ahead,
            limit=limit,
        )
        logger.info("Birthday CRM generation finished: %s", result)
        return result


async def run_new_arrival_crm_generation(work_date: date | None = None) -> dict:
    if os.getenv("CRM_NEW_ARRIVAL_LIVE_GENERATION_ENABLED", "false").strip().lower() not in {"1", "true", "yes", "on"}:
        return {
            "skipped": True,
            "reason": "live_generation_requires_anatoliy_technical_approval",
            "auto_send": False,
        }
    target_date = work_date or date.today()
    lookback_hours = int(os.getenv("CRM_NEW_ARRIVAL_LOOKBACK_HOURS", "24"))
    limit_arrivals = int(os.getenv("CRM_NEW_ARRIVAL_LIMIT_ARRIVALS", "10"))
    limit_clients = int(os.getenv("CRM_NEW_ARRIVAL_LIMIT_CLIENTS_PER_ARRIVAL", "25"))
    receipt_max_documents = int(os.getenv("CRM_NEW_ARRIVAL_RECEIPT_MAX_DOCUMENTS", "500"))
    async with AsyncSessionLocal() as db:
        async with OneCPurchaseReceiptArrivalService(db) as receipt_service:
            receipt_sync = await receipt_service.sync_recent_receipts(
                lookback_hours=lookback_hours,
                max_documents=receipt_max_documents,
            )
        result = await CrmNewArrivalService(db).generate_tasks(
            target_date,
            lookback_hours=lookback_hours,
            limit_arrivals=limit_arrivals,
            limit_clients_per_arrival=limit_clients,
            use_polling_fallback=False,
            dry_run=False,
        )
        result["receipt_sync"] = receipt_sync
        result["transfer_sync"] = {
            "enabled": False,
            "ignored_as_new_arrival_source": True,
            "source_rule": "scheduler_primary_receipt_only",
        }
        logger.info("New arrival CRM generation finished: %s", result)
        return result


async def run_customer_request_control() -> dict:
    async with AsyncSessionLocal() as db:
        result = await run_due_control(db)
        logger.info("Customer request control finished: %s", result)
        return result


async def run_crm_overdue_control(work_date: date | None = None) -> dict:
    target_date = work_date or date.today()
    async with AsyncSessionLocal() as db:
        marked = await CrmTaskService(db).mark_overdue_tasks(today=target_date)
        result = {"work_date": target_date.isoformat(), "marked_overdue": marked}
        logger.info("CRM overdue control finished: %s", result)
        return result


async def crm_touchpoint_generation_loop(stop_event: asyncio.Event) -> None:
    interval_minutes = int(os.getenv("CRM_TOUCHPOINT_INTERVAL_MINUTES", "180"))
    initial_delay = int(os.getenv("CRM_TOUCHPOINT_INITIAL_DELAY_SECONDS", "180"))

    try:
        await asyncio.wait_for(stop_event.wait(), timeout=max(initial_delay, 0))
        return
    except asyncio.TimeoutError:
        pass

    while not stop_event.is_set():
        try:
            touchpoints = await run_crm_touchpoint_generation()
            birthdays = await run_birthday_crm_generation()
            new_arrivals = await run_new_arrival_crm_generation()
            overdue = await run_crm_overdue_control()
            requests = await run_customer_request_control()
            logger.info(
                "CRM recurring generation finished: touchpoints=%s birthdays=%s new_arrivals=%s overdue=%s customer_requests=%s",
                touchpoints,
                birthdays,
                new_arrivals,
                overdue,
                requests,
            )
        except Exception:
            logger.error("CRM touchpoint generation failed", exc_info=True)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=max(interval_minutes, 5) * 60)
            break
        except asyncio.TimeoutError:
            pass


async def start_crm_touchpoint_scheduler(app) -> None:
    if not _env_bool("CRM_TOUCHPOINT_SCHEDULER_ENABLED", "true"):
        logger.info("CRM touchpoint scheduler disabled by env.")
        return

    stop_event = asyncio.Event()
    task = asyncio.create_task(crm_touchpoint_generation_loop(stop_event))
    app.state.crm_touchpoint_stop_event = stop_event
    app.state.crm_touchpoint_task = task
    logger.info(
        "CRM touchpoint scheduler started (interval=%s minutes, initial_delay=%s seconds).",
        os.getenv("CRM_TOUCHPOINT_INTERVAL_MINUTES", "180"),
        os.getenv("CRM_TOUCHPOINT_INITIAL_DELAY_SECONDS", "180"),
    )


async def stop_crm_touchpoint_scheduler(app) -> None:
    stop_event = getattr(app.state, "crm_touchpoint_stop_event", None)
    task = getattr(app.state, "crm_touchpoint_task", None)

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

    logger.info("CRM touchpoint scheduler stopped")
