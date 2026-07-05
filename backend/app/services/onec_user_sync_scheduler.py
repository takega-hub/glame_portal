import asyncio
import logging
import os
from datetime import datetime, timezone

from sqlalchemy import select

from app.database.connection import AsyncSessionLocal
from app.models.onec_user_sync_job import OneCUserSyncJob
from app.services.onec_user_sync_service import OneCUserSyncService, _env_bool


logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def onec_user_sync_loop(stop_event: asyncio.Event) -> None:
    poll_seconds = int(os.getenv("ONEC_OUTBOUND_POLL_SECONDS", "10"))
    batch_limit = int(os.getenv("ONEC_OUTBOUND_BATCH_LIMIT", "10"))

    while not stop_event.is_set():
        try:
            now = _utcnow()
            async with AsyncSessionLocal() as db:
                stmt = (
                    select(OneCUserSyncJob.id)
                    .where(OneCUserSyncJob.status == "pending")
                    .where(OneCUserSyncJob.next_attempt_at.isnot(None))
                    .where(OneCUserSyncJob.next_attempt_at <= now)
                    .order_by(OneCUserSyncJob.next_attempt_at.asc())
                    .limit(batch_limit)
                )
                result = await db.execute(stmt)
                job_ids = [row[0] for row in result.all()]

            for job_id in job_ids:
                async with AsyncSessionLocal() as db:
                    svc = OneCUserSyncService(db)
                    await svc.process_job(job_id)
        except Exception as exc:
            logger.error("Outbound 1C user sync loop failed: %s", exc, exc_info=True)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
        except asyncio.TimeoutError:
            continue


async def start_onec_user_sync_scheduler(app) -> None:
    if not _env_bool("ONEC_OUTBOUND_SYNC_ENABLED", "false"):
        logger.info("Outbound 1C user sync scheduler disabled by env.")
        return

    stop_event = asyncio.Event()
    task = asyncio.create_task(onec_user_sync_loop(stop_event))

    app.state.onec_user_sync_stop_event = stop_event
    app.state.onec_user_sync_task = task

    logger.info("Outbound 1C user sync scheduler started.")


async def stop_onec_user_sync_scheduler(app) -> None:
    stop_event = getattr(app.state, "onec_user_sync_stop_event", None)
    task = getattr(app.state, "onec_user_sync_task", None)
    if stop_event:
        stop_event.set()
    if task:
        await task

