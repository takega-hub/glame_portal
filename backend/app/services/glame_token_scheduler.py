"""Scheduler for GLM ledger maintenance jobs."""
from __future__ import annotations

import asyncio
import logging
import os
from uuid import UUID

from sqlalchemy import desc, select

from app.database.connection import AsyncSessionLocal
from app.models.glame_token import GlameTokenTransaction
from app.services.glm_telegram_alert_service import GlmTelegramAlertService
from app.services.glame_token_service import GLAME_GLM_TO_POINTS_BRIDGE_REASONS, GlameTokenService
from app.services.ton_glm_auto_transfer_service import TonGlmAutoTransferService
from app.services.ton_glm_settlement_service import TonGlmSettlementService

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: str = "false") -> bool:
    value = os.getenv(name, default).strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def glm_token_scheduler_status(app) -> dict:
    def task_status(task) -> str:
        if task is None:
            return "not_started"
        if task.cancelled():
            return "cancelled"
        if task.done():
            return "stopped"
        return "running"

    hold_task = getattr(app.state, "glm_hold_release_task", None)
    settlement_task = getattr(app.state, "glm_ton_settlement_task", None)
    auto_transfer_task = getattr(app.state, "glm_ton_auto_transfer_task", None)
    onec_retry_task = getattr(app.state, "glm_onec_bridge_retry_task", None)
    telegram_alert_task = getattr(app.state, "glm_telegram_alert_task", None)
    return {
        "hold_release": {
            "enabled": _env_bool("GLM_HOLD_RELEASE_SCHEDULER_ENABLED", "true"),
            "status": task_status(hold_task),
            "interval_minutes": int(os.getenv("GLM_HOLD_RELEASE_INTERVAL_MINUTES", "60") or 60),
            "batch_limit": int(os.getenv("GLM_HOLD_RELEASE_BATCH_LIMIT", "500") or 500),
        },
        "ton_settlement": {
            "enabled": _env_bool("TON_GLM_SETTLEMENT_WATCHER_ENABLED", "false"),
            "status": task_status(settlement_task),
            "interval_minutes": int(os.getenv("TON_GLM_SETTLEMENT_INTERVAL_MINUTES", "15") or 15),
            "batch_limit": int(os.getenv("TON_GLM_SETTLEMENT_BATCH_LIMIT", "50") or 50),
        },
        "ton_auto_transfer": {
            "enabled": _env_bool("TON_GLM_AUTO_TRANSFER_ENABLED", "false"),
            "status": task_status(auto_transfer_task),
            "interval_minutes": int(os.getenv("TON_GLM_AUTO_TRANSFER_INTERVAL_MINUTES", "5") or 5),
            "batch_limit": int(os.getenv("TON_GLM_AUTO_TRANSFER_BATCH_LIMIT", "20") or 20),
        },
        "onec_bridge_retry": {
            "enabled": _env_bool("GLM_BRIDGE_ONEC_RETRY_SCHEDULER_ENABLED", "false"),
            "status": task_status(onec_retry_task),
            "interval_minutes": int(os.getenv("GLM_BRIDGE_ONEC_RETRY_INTERVAL_MINUTES", "10") or 10),
            "batch_limit": int(os.getenv("GLM_BRIDGE_ONEC_RETRY_BATCH_LIMIT", "50") or 50),
        },
        "telegram_alerts": {
            "enabled": _env_bool("GLM_TELEGRAM_ALERTS_ENABLED", "true"),
            "status": task_status(telegram_alert_task),
            "interval_minutes": int(os.getenv("GLM_TELEGRAM_ALERTS_INTERVAL_MINUTES", "15") or 15),
            "cooldown_minutes": int(os.getenv("GLM_TELEGRAM_ALERTS_COOLDOWN_MINUTES", "60") or 60),
        },
    }


async def run_glm_due_hold_release(limit: int | None = None) -> dict:
    batch_limit = limit if limit is not None else int(os.getenv("GLM_HOLD_RELEASE_BATCH_LIMIT", "500"))
    async with AsyncSessionLocal() as db:
        result = await GlameTokenService(db).release_due_holds(limit=max(batch_limit, 1), admin_user_id=None)
        await db.commit()
        logger.info("GLM due hold release finished: %s", result)
        return result


async def run_glm_ton_settlement(limit: int | None = None) -> dict:
    admin_user_id = (os.getenv("TON_GLM_SETTLEMENT_ADMIN_USER_ID") or "").strip()
    if not admin_user_id:
        return {
            "status": "skipped",
            "reason": "TON_GLM_SETTLEMENT_ADMIN_USER_ID is not set",
        }
    batch_limit = limit if limit is not None else int(os.getenv("TON_GLM_SETTLEMENT_BATCH_LIMIT", "50"))
    async with AsyncSessionLocal() as db:
        result = await TonGlmSettlementService(db).settle_pending_claims(
            admin_user_id=UUID(admin_user_id),
            limit=max(batch_limit, 1),
            require_verified=True,
        )
        await db.commit()
        logger.info("GLM TON settlement finished: %s", result)
        return result


async def run_glm_ton_auto_transfer(limit: int | None = None) -> dict:
    batch_limit = limit if limit is not None else int(os.getenv("TON_GLM_AUTO_TRANSFER_BATCH_LIMIT", "20"))
    async with AsyncSessionLocal() as db:
        result = await TonGlmAutoTransferService(db).process_pending_claims(limit=max(batch_limit, 1))
        await db.commit()
        logger.info("GLM TON auto-transfer finished: %s", result)
        return result


async def run_glm_onec_bridge_retry(limit: int | None = None) -> dict:
    admin_user_id = (
        os.getenv("GLM_BRIDGE_ONEC_RETRY_ADMIN_USER_ID")
        or os.getenv("TON_GLM_SETTLEMENT_ADMIN_USER_ID")
        or os.getenv("TON_GLM_AUTO_TRANSFER_ADMIN_USER_ID")
        or ""
    ).strip()
    if not admin_user_id:
        return {
            "status": "skipped",
            "reason": "GLM_BRIDGE_ONEC_RETRY_ADMIN_USER_ID is not set",
        }

    batch_limit = max(limit if limit is not None else int(os.getenv("GLM_BRIDGE_ONEC_RETRY_BATCH_LIMIT", "50")), 1)
    retryable_statuses = {"failed", "ready_for_1c", "created_without_ref_key", "posted_without_balance_change"}
    candidate_limit = max(batch_limit * 5, batch_limit)

    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(GlameTokenTransaction)
                .where(
                    GlameTokenTransaction.transaction_type == "bridge",
                    GlameTokenTransaction.status == "processed",
                    GlameTokenTransaction.reason.in_(GLAME_GLM_TO_POINTS_BRIDGE_REASONS),
                )
                .order_by(desc(GlameTokenTransaction.created_at))
                .limit(candidate_limit)
            )
        ).scalars().all()

        service = GlameTokenService(db)
        processed: list[dict] = []
        blocked: list[dict] = []
        skipped = 0

        for bridge in rows:
            if len(processed) >= batch_limit:
                break
            meta = bridge.meta if isinstance(bridge.meta, dict) else {}
            sync_status = str(meta.get("onec_sync_status") or "").strip()
            if sync_status not in retryable_statuses:
                skipped += 1
                continue
            if meta.get("repair_status") == "reviewed":
                skipped += 1
                continue

            try:
                repaired = await service.repair_glm_bridge_onec_sync(
                    bridge=bridge,
                    action="retry_onec",
                    admin_user_id=UUID(admin_user_id),
                    comment="Automatic retry for GLM -> points 1C sync.",
                )
                repaired_meta = repaired.meta if isinstance(repaired.meta, dict) else {}
                processed.append(
                    {
                        "transaction_id": str(repaired.id),
                        "onec_sync_status": repaired_meta.get("onec_sync_status"),
                        "onec_document_id": repaired_meta.get("onec_document_id"),
                    }
                )
            except Exception as exc:
                blocked.append({"transaction_id": str(bridge.id), "error": str(exc)})

        await db.commit()
        result = {
            "status": "processed",
            "checked": len(rows),
            "processed": processed,
            "blocked": blocked,
            "skipped": skipped,
        }
        logger.info("GLM 1C bridge retry finished: %s", result)
        return result


async def run_glm_telegram_alerts(*, force: bool = False) -> dict:
    async with AsyncSessionLocal() as db:
        result = await GlmTelegramAlertService(db).run_once(force=force)
        logger.info("GLM Telegram alerts finished: %s", result)
        return result


async def glm_hold_release_loop(stop_event: asyncio.Event) -> None:
    interval_minutes = int(os.getenv("GLM_HOLD_RELEASE_INTERVAL_MINUTES", "60"))
    initial_delay = int(os.getenv("GLM_HOLD_RELEASE_INITIAL_DELAY_SECONDS", "120"))

    try:
        await asyncio.wait_for(stop_event.wait(), timeout=max(initial_delay, 0))
        return
    except asyncio.TimeoutError:
        pass

    while not stop_event.is_set():
        try:
            await run_glm_due_hold_release()
        except Exception:
            logger.error("GLM due hold release failed", exc_info=True)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=max(interval_minutes, 5) * 60)
            break
        except asyncio.TimeoutError:
            pass


async def glm_ton_settlement_loop(stop_event: asyncio.Event) -> None:
    interval_minutes = int(os.getenv("TON_GLM_SETTLEMENT_INTERVAL_MINUTES", "15"))
    initial_delay = int(os.getenv("TON_GLM_SETTLEMENT_INITIAL_DELAY_SECONDS", "180"))

    try:
        await asyncio.wait_for(stop_event.wait(), timeout=max(initial_delay, 0))
        return
    except asyncio.TimeoutError:
        pass

    while not stop_event.is_set():
        try:
            await run_glm_ton_settlement()
        except Exception:
            logger.error("GLM TON settlement failed", exc_info=True)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=max(interval_minutes, 1) * 60)
            break
        except asyncio.TimeoutError:
            pass


async def glm_ton_auto_transfer_loop(stop_event: asyncio.Event) -> None:
    interval_minutes = int(os.getenv("TON_GLM_AUTO_TRANSFER_INTERVAL_MINUTES", "5"))
    initial_delay = int(os.getenv("TON_GLM_AUTO_TRANSFER_INITIAL_DELAY_SECONDS", "60"))

    try:
        await asyncio.wait_for(stop_event.wait(), timeout=max(initial_delay, 0))
        return
    except asyncio.TimeoutError:
        pass

    while not stop_event.is_set():
        try:
            await run_glm_ton_auto_transfer()
        except Exception:
            logger.error("GLM TON auto-transfer failed", exc_info=True)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=max(interval_minutes, 1) * 60)
            break
        except asyncio.TimeoutError:
            pass


async def glm_onec_bridge_retry_loop(stop_event: asyncio.Event) -> None:
    interval_minutes = int(os.getenv("GLM_BRIDGE_ONEC_RETRY_INTERVAL_MINUTES", "10"))
    initial_delay = int(os.getenv("GLM_BRIDGE_ONEC_RETRY_INITIAL_DELAY_SECONDS", "240"))

    try:
        await asyncio.wait_for(stop_event.wait(), timeout=max(initial_delay, 0))
        return
    except asyncio.TimeoutError:
        pass

    while not stop_event.is_set():
        try:
            await run_glm_onec_bridge_retry()
        except Exception:
            logger.error("GLM 1C bridge retry failed", exc_info=True)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=max(interval_minutes, 1) * 60)
            break
        except asyncio.TimeoutError:
            pass


async def glm_telegram_alert_loop(stop_event: asyncio.Event) -> None:
    interval_minutes = int(os.getenv("GLM_TELEGRAM_ALERTS_INTERVAL_MINUTES", "15"))
    initial_delay = int(os.getenv("GLM_TELEGRAM_ALERTS_INITIAL_DELAY_SECONDS", "300"))

    try:
        await asyncio.wait_for(stop_event.wait(), timeout=max(initial_delay, 0))
        return
    except asyncio.TimeoutError:
        pass

    while not stop_event.is_set():
        try:
            await run_glm_telegram_alerts()
        except Exception:
            logger.error("GLM Telegram alerts failed", exc_info=True)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=max(interval_minutes, 1) * 60)
            break
        except asyncio.TimeoutError:
            pass


async def start_glm_hold_release_scheduler(app) -> None:
    if not _env_bool("GLM_HOLD_RELEASE_SCHEDULER_ENABLED", "true"):
        logger.info("GLM hold release scheduler disabled by env.")
        return

    stop_event = asyncio.Event()
    task = asyncio.create_task(glm_hold_release_loop(stop_event))
    app.state.glm_hold_release_stop_event = stop_event
    app.state.glm_hold_release_task = task
    logger.info(
        "GLM hold release scheduler started (interval=%s minutes, batch_limit=%s).",
        os.getenv("GLM_HOLD_RELEASE_INTERVAL_MINUTES", "60"),
        os.getenv("GLM_HOLD_RELEASE_BATCH_LIMIT", "500"),
    )


async def start_glm_ton_settlement_scheduler(app) -> None:
    if not _env_bool("TON_GLM_SETTLEMENT_WATCHER_ENABLED", "false"):
        logger.info("GLM TON settlement scheduler disabled by env.")
        return

    stop_event = asyncio.Event()
    task = asyncio.create_task(glm_ton_settlement_loop(stop_event))
    app.state.glm_ton_settlement_stop_event = stop_event
    app.state.glm_ton_settlement_task = task
    logger.info(
        "GLM TON settlement scheduler started (interval=%s minutes, batch_limit=%s).",
        os.getenv("TON_GLM_SETTLEMENT_INTERVAL_MINUTES", "15"),
        os.getenv("TON_GLM_SETTLEMENT_BATCH_LIMIT", "50"),
    )


async def start_glm_ton_auto_transfer_scheduler(app) -> None:
    if not _env_bool("TON_GLM_AUTO_TRANSFER_ENABLED", "false"):
        logger.info("GLM TON auto-transfer scheduler disabled by env.")
        return

    stop_event = asyncio.Event()
    task = asyncio.create_task(glm_ton_auto_transfer_loop(stop_event))
    app.state.glm_ton_auto_transfer_stop_event = stop_event
    app.state.glm_ton_auto_transfer_task = task
    logger.info(
        "GLM TON auto-transfer scheduler started (interval=%s minutes, batch_limit=%s).",
        os.getenv("TON_GLM_AUTO_TRANSFER_INTERVAL_MINUTES", "5"),
        os.getenv("TON_GLM_AUTO_TRANSFER_BATCH_LIMIT", "20"),
    )


async def start_glm_onec_bridge_retry_scheduler(app) -> None:
    if not _env_bool("GLM_BRIDGE_ONEC_RETRY_SCHEDULER_ENABLED", "false"):
        logger.info("GLM 1C bridge retry scheduler disabled by env.")
        return

    stop_event = asyncio.Event()
    task = asyncio.create_task(glm_onec_bridge_retry_loop(stop_event))
    app.state.glm_onec_bridge_retry_stop_event = stop_event
    app.state.glm_onec_bridge_retry_task = task
    logger.info(
        "GLM 1C bridge retry scheduler started (interval=%s minutes, batch_limit=%s).",
        os.getenv("GLM_BRIDGE_ONEC_RETRY_INTERVAL_MINUTES", "10"),
        os.getenv("GLM_BRIDGE_ONEC_RETRY_BATCH_LIMIT", "50"),
    )


async def start_glm_telegram_alert_scheduler(app) -> None:
    if not _env_bool("GLM_TELEGRAM_ALERTS_ENABLED", "true"):
        logger.info("GLM Telegram alert scheduler disabled by env.")
        return

    stop_event = asyncio.Event()
    task = asyncio.create_task(glm_telegram_alert_loop(stop_event))
    app.state.glm_telegram_alert_stop_event = stop_event
    app.state.glm_telegram_alert_task = task
    logger.info(
        "GLM Telegram alert scheduler started (interval=%s minutes, cooldown=%s minutes).",
        os.getenv("GLM_TELEGRAM_ALERTS_INTERVAL_MINUTES", "15"),
        os.getenv("GLM_TELEGRAM_ALERTS_COOLDOWN_MINUTES", "60"),
    )


async def stop_glm_hold_release_scheduler(app) -> None:
    stop_event = getattr(app.state, "glm_hold_release_stop_event", None)
    task = getattr(app.state, "glm_hold_release_task", None)

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

    logger.info("GLM hold release scheduler stopped")


async def stop_glm_ton_settlement_scheduler(app) -> None:
    stop_event = getattr(app.state, "glm_ton_settlement_stop_event", None)
    task = getattr(app.state, "glm_ton_settlement_task", None)

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

    logger.info("GLM TON settlement scheduler stopped")


async def stop_glm_ton_auto_transfer_scheduler(app) -> None:
    stop_event = getattr(app.state, "glm_ton_auto_transfer_stop_event", None)
    task = getattr(app.state, "glm_ton_auto_transfer_task", None)

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

    logger.info("GLM TON auto-transfer scheduler stopped")


async def stop_glm_onec_bridge_retry_scheduler(app) -> None:
    stop_event = getattr(app.state, "glm_onec_bridge_retry_stop_event", None)
    task = getattr(app.state, "glm_onec_bridge_retry_task", None)

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

    logger.info("GLM 1C bridge retry scheduler stopped")


async def stop_glm_telegram_alert_scheduler(app) -> None:
    stop_event = getattr(app.state, "glm_telegram_alert_stop_event", None)
    task = getattr(app.state, "glm_telegram_alert_task", None)

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

    logger.info("GLM Telegram alert scheduler stopped")
