from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.models.order import Order
from app.models.payment import Payment
from app.models.tilda_gift_certificate_operation import TildaGiftCertificateOperation
from app.services.gift_certificate_email_service import GiftCertificateEmailService
from app.services.gift_certificate_service import GiftCertificateService
from app.services.onec_order_xml_service import write_orders_xml_snapshot
from app.services.tilda_gift_certificate_service import TildaGiftCertificateService
from app.services.yookassa_service import get_yookassa_service_for_db


router = APIRouter()


def _extract_payment_id(payload: Dict[str, Any]) -> Optional[str]:
    obj = payload.get("object")
    if isinstance(obj, dict) and obj.get("id"):
        return str(obj.get("id"))
    return None


async def _refresh_onec_orders_snapshot(db: AsyncSession) -> None:
    try:
        await write_orders_xml_snapshot(db)
    except Exception:
        pass


async def _process_tilda_certificate_payment(
    db: AsyncSession, *, payment_id: str, yookassa_service
) -> bool:
    """Finalize a hosted certificate checkout after a verified YooKassa event.

    The payment id is persisted on the reservation before the buyer is sent to
    YooKassa.  This makes callback retries safe and avoids trusting the event
    payload itself: the current payment state is fetched from YooKassa first.
    """
    operation = (
        await db.execute(
            select(TildaGiftCertificateOperation)
            .where(TildaGiftCertificateOperation.operation_type == "reserve")
            .where(TildaGiftCertificateOperation.payment_id == payment_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not operation:
        return False

    remote = await yookassa_service.get_payment(payment_id)
    status = str(remote.get("status") or "pending").lower()
    meta = operation.meta if isinstance(operation.meta, dict) else {}
    items = meta.get("items") if isinstance(meta.get("items"), list) else []
    certificates = TildaGiftCertificateService(db)

    if status == "succeeded":
        await certificates.confirm(
            operation_id=operation.id,
            tilda_order_id=str(operation.tilda_order_id or ""),
            payment_status="succeeded",
            payment_id=payment_id,
            order_amount=int(operation.cart_total or 0),
            payment_amount=max(0, int(operation.cart_total or 0) - int(operation.amount or 0)),
            items=items,
            idempotency_key=f"yookassa:{payment_id}:succeeded",
        )
    elif status == "canceled" and operation.status == "reserved":
        await certificates.release(
            operation_id=operation.id,
            tilda_order_id=str(operation.tilda_order_id or ""),
            reason="payment_canceled",
            idempotency_key=f"yookassa:{payment_id}:canceled",
        )

    operation.meta = {**meta, "yookassa_status": status}
    await db.commit()
    return True


@router.post("/webhooks/yookassa")
@router.post("/yookassa/webhook")
@router.post("/payments/webhook")
async def yookassa_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    svc = await get_yookassa_service_for_db(db)
    if not svc:
        raise HTTPException(status_code=500, detail="YOOKASSA is not configured")

    payload = await request.json()
    payment_external_id = _extract_payment_id(payload)
    if not payment_external_id:
        return {"ok": True}

    if await _process_tilda_certificate_payment(
        db, payment_id=payment_external_id, yookassa_service=svc
    ):
        return {"ok": True}

    payment = (
        await db.execute(select(Payment).where(Payment.external_id == payment_external_id))
    ).scalar_one_or_none()
    if not payment:
        return {"ok": True}

    remote = await svc.get_payment(payment_external_id)
    remote_status = str(remote.get("status") or "pending")
    payment.status = remote_status
    payment.raw = remote

    if remote_status == "succeeded":
        order = (
            await db.execute(select(Order).where(Order.id == payment.order_id))
        ).scalar_one_or_none()
        if order and order.status in {"pending", "payment_pending", "paid"}:
            order.status = "paid"
            gift_service = GiftCertificateService(db)
            meta = order.meta if isinstance(order.meta, dict) else {}
            if meta.get("order_type") == "gift_certificate_purchase":
                activated = await gift_service.activate_order_certificates(order.id, payment.id)
                await GiftCertificateEmailService(db).send_for_certificates(activated)
            if isinstance(meta.get("gift_certificate_payment"), dict):
                await gift_service.redeem_reserved_for_order(order.id)
                next_meta = dict(meta)
                gift_meta = dict(next_meta.get("gift_certificate_payment") or {})
                gift_meta["status"] = "redeemed"
                next_meta["gift_certificate_payment"] = gift_meta
                order.meta = next_meta

    if remote_status in {"canceled"}:
        order = (
            await db.execute(select(Order).where(Order.id == payment.order_id))
        ).scalar_one_or_none()
        if order and order.status in {"pending", "payment_pending"}:
            order.status = "canceled"
            gift_service = GiftCertificateService(db)
            await gift_service.release_reserved_for_order(order.id)
            await gift_service.cancel_order_certificates(order.id)

    await db.commit()
    await _refresh_onec_orders_snapshot(db)
    return {"ok": True}
