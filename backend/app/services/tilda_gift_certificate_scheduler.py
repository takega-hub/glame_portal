from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

from fastapi import FastAPI
from sqlalchemy import select

from app.database.connection import AsyncSessionLocal
from app.models.tilda_gift_certificate_operation import TildaGiftCertificateOperation
from app.models.tilda_gift_certificate_purchase import TildaGiftCertificatePurchase
from app.models.gift_certificate import GiftCertificate
from app.services.gift_certificate_email_service import GiftCertificateEmailService
from app.services.tilda_gift_certificate_service import TildaGiftCertificateService
from app.services.yookassa_service import get_yookassa_service_for_db
from app.api.tilda_gift_certificate_purchase import process_purchase_payment


logger = logging.getLogger(__name__)
_TASK_NAME = "tilda_gift_certificate_maintenance_task"


async def _reconcile_expired_hosted_payments(db) -> int:
    """Keep a certificate reserved until its hosted YooKassa payment is final."""
    payment_service = await get_yookassa_service_for_db(db)
    if not payment_service:
        return 0
    now = datetime.now(timezone.utc)
    operations = (
        await db.execute(
            select(TildaGiftCertificateOperation)
            .where(TildaGiftCertificateOperation.operation_type == "reserve")
            .where(TildaGiftCertificateOperation.status == "reserved")
            .where(TildaGiftCertificateOperation.payment_id.is_not(None))
            .where(TildaGiftCertificateOperation.reservation_expires_at < now)
            .with_for_update(skip_locked=True)
        )
    ).scalars().all()
    certificates = TildaGiftCertificateService(db)
    reconciled = 0
    for operation in operations:
        try:
            payment = await payment_service.get_payment(str(operation.payment_id))
            status = str(payment.get("status") or "pending").lower()
            if status == "succeeded":
                meta = operation.meta if isinstance(operation.meta, dict) else {}
                await certificates.confirm(
                    operation_id=operation.id,
                    tilda_order_id=str(operation.tilda_order_id or ""),
                    payment_status="succeeded",
                    payment_id=str(operation.payment_id),
                    order_amount=int(operation.cart_total or 0),
                    payment_amount=max(0, int(operation.cart_total or 0) - int(operation.amount or 0)),
                    items=meta.get("items") if isinstance(meta.get("items"), list) else [],
                    idempotency_key=f"yookassa:{operation.payment_id}:succeeded",
                )
            elif status == "canceled":
                await certificates.release(
                    operation_id=operation.id,
                    tilda_order_id=str(operation.tilda_order_id or ""),
                    reason="payment_canceled",
                    idempotency_key=f"yookassa:{operation.payment_id}:canceled",
                )
            else:
                operation.reservation_expires_at = now + certificates.reservation_ttl()
                operation.meta = {**(operation.meta or {}), "yookassa_status": status}
            reconciled += 1
        except Exception:
            logger.exception("Tilda hosted payment reconciliation failed: payment=%s", operation.payment_id)
    return reconciled


async def _deliver_scheduled_purchases(db) -> int:
    now = datetime.now(timezone.utc)
    purchases = (
        await db.execute(
            select(TildaGiftCertificatePurchase)
            .where(TildaGiftCertificatePurchase.status == "scheduled")
            .where(TildaGiftCertificatePurchase.send_at <= now)
            .with_for_update(skip_locked=True)
        )
    ).scalars().all()
    delivered = 0
    mailer = GiftCertificateEmailService(db)
    for purchase in purchases:
        certificate = await db.get(GiftCertificate, purchase.certificate_id)
        if not certificate:
            purchase.status = "failed"
            purchase.error = "Issued certificate is missing"
            continue
        await mailer.send_for_certificates([certificate])
        purchase.status = "sent"
        purchase.sent_at = now
        delivered += 1
    return delivered


async def _retry_paid_purchase_issues(db) -> int:
    payment_service = await get_yookassa_service_for_db(db)
    if not payment_service:
        return 0
    purchases = (
        await db.execute(
            select(TildaGiftCertificatePurchase)
            .where(TildaGiftCertificatePurchase.status == "paid_pending_issue")
            .where(TildaGiftCertificatePurchase.payment_id.is_not(None))
            .with_for_update(skip_locked=True)
        )
    ).scalars().all()
    retried = 0
    for purchase in purchases:
        if await process_purchase_payment(db, payment_id=str(purchase.payment_id), yookassa_service=payment_service):
            retried += 1
    return retried


async def _run_maintenance() -> None:
    interval = max(30, int(os.getenv("TILDA_GIFT_CERTIFICATE_MAINTENANCE_INTERVAL_SECONDS", "60")))
    while True:
        try:
            async with AsyncSessionLocal() as db:
                service = TildaGiftCertificateService(db)
                await _reconcile_expired_hosted_payments(db)
                await _retry_paid_purchase_issues(db)
                await _deliver_scheduled_purchases(db)
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
