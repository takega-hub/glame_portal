from __future__ import annotations

import asyncio
import logging
import os

from fastapi import FastAPI

from app.database.connection import AsyncSessionLocal
from app.services.tilda_gift_certificate_service import TildaGiftCertificateService


logger = logging.getLogger(__name__)
_TASK_NAME = "tilda_gift_certificate_maintenance_task"


async def _run_maintenance() -> None:
    interval = max(30, int(os.getenv("TILDA_GIFT_CERTIFICATE_MAINTENANCE_INTERVAL_SECONDS", "60")))
    while True:
        try:
            async with AsyncSessionLocal() as db:
                service = TildaGiftCertificateService(db)
                await service.release_expired_reservations()
                await service.retry_pending_sync()
                await db.commit()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Tilda gift certificate maintenance failed")
        await asyncio.sleep(interval)


async def start_tilda_gift_certificate_scheduler(app: FastAPI) -> None:
    if os.getenv("TILDA_GIFT_CERTIFICATE_SCHEDULER_ENABLED", "true").lower() in {"0", "false", "no"}:
        return
    if getattr(app.state, _TASK_NAME, None):
        return
    setattr(app.state, _TASK_NAME, asyncio.create_task(_run_maintenance(), name=_TASK_NAME))


async def stop_tilda_gift_certificate_scheduler(app: FastAPI) -> None:
    task = getattr(app.state, _TASK_NAME, None)
    if not task:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    setattr(app.state, _TASK_NAME, None)
