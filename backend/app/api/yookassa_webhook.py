from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.models.order import Order
from app.models.payment import Payment
from app.services.gift_certificate_email_service import GiftCertificateEmailService
from app.services.gift_certificate_service import GiftCertificateService
from app.services.onec_order_xml_service import write_orders_xml_snapshot
from app.services.yookassa_service import get_yookassa_service


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


@router.post("/webhooks/yookassa")
@router.post("/yookassa/webhook")
@router.post("/payments/webhook")
async def yookassa_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    svc = get_yookassa_service()
    if not svc:
        raise HTTPException(status_code=500, detail="YOOKASSA is not configured")

    payload = await request.json()
    payment_external_id = _extract_payment_id(payload)
    if not payment_external_id:
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
        if order and order.status in {"pending", "payment_pending"}:
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
