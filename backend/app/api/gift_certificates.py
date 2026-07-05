from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, normalize_phone
from app.api.dependencies import require_any_role
from app.database.connection import get_db
from app.models.gift_certificate import GiftCertificate
from app.models.order import Order
from app.models.payment import Payment
from app.models.user import User
from app.services.gift_certificate_service import GiftCertificateService
from app.services.onec_order_xml_service import write_orders_xml_snapshot
from app.services.yookassa_service import get_yookassa_service


router = APIRouter()


class GiftCertificatePurchaseRequest(BaseModel):
    nominal_amount: int = Field(gt=0)
    return_url: str
    recipient_name: Optional[str] = None
    recipient_phone: Optional[str] = None
    recipient_email: Optional[EmailStr] = None
    message: Optional[str] = None
    sender_name: Optional[str] = None
    send_at: Optional[str] = None
    design: Optional[int] = None
    accent: Optional[int] = None
    texture_id: Optional[str] = None
    expires_in_days: int = Field(default=365, ge=1, le=3650)
    meta: Optional[dict[str, Any]] = None


class GiftCertificateValidateRequest(BaseModel):
    number: str
    pin: Optional[str] = None


class GiftCertificateRedeemOfflineRequest(BaseModel):
    number: str
    amount: int = Field(gt=0)
    pin: Optional[str] = None
    store_id: Optional[str] = None
    external_operation_id: Optional[str] = None
    onec_document_id: Optional[str] = None
    meta: Optional[dict[str, Any]] = None


def _rub_value(amount_kopeks: int) -> str:
    return f"{amount_kopeks / 100.0:.2f}"


def _parse_uuid(value: Optional[str], field: str) -> Optional[UUID]:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {field}")


async def _refresh_onec_orders_snapshot(db: AsyncSession) -> None:
    try:
        await write_orders_xml_snapshot(db)
    except Exception:
        pass


@router.post("/gift-certificates/purchase")
async def purchase_gift_certificate(
    body: GiftCertificatePurchaseRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = get_yookassa_service()
    if not svc:
        raise HTTPException(status_code=500, detail="YOOKASSA is not configured")

    nominal = int(body.nominal_amount or 0)
    if nominal <= 0:
        raise HTTPException(status_code=400, detail="Invalid nominal amount")
    return_url = str(body.return_url or "").strip()
    if not return_url:
        raise HTTPException(status_code=400, detail="return_url is required")

    recipient_phone = normalize_phone(body.recipient_phone or "") or None
    recipient_user_id: Optional[UUID] = None
    if recipient_phone:
        recipient_user = (
            await db.execute(select(User).where(User.phone == recipient_phone))
        ).scalar_one_or_none()
        if recipient_user:
            recipient_user_id = recipient_user.id

    order_meta = dict(body.meta or {})
    order_meta["order_type"] = "gift_certificate_purchase"
    order_meta["gift_certificate_purchase"] = {
        "nominal_amount": nominal,
        "recipient_name": body.recipient_name,
        "recipient_phone": recipient_phone,
        "recipient_user_id": str(recipient_user_id) if recipient_user_id else None,
        "recipient_email": str(body.recipient_email) if body.recipient_email else None,
        "message": body.message,
        "sender_name": body.sender_name,
        "send_at": body.send_at,
        "design": body.design,
        "accent": body.accent,
        "texture_id": body.texture_id,
        "expires_in_days": int(body.expires_in_days or 365),
    }

    contact = {
        "name": body.recipient_name or current_user.full_name,
        "phone": recipient_phone or current_user.phone,
        "email": str(body.recipient_email) if body.recipient_email else current_user.email,
    }
    order = Order(
        user_id=current_user.id,
        status="pending",
        currency="RUB",
        subtotal_amount=nominal,
        delivery_amount=0,
        discount_amount=0,
        total_amount=nominal,
        delivery=None,
        contact=contact,
        meta=order_meta,
    )
    db.add(order)
    await db.flush()

    cert, pin = await GiftCertificateService(db).create_pending_certificate(
        buyer_user_id=current_user.id,
        recipient_user_id=recipient_user_id,
        nominal_amount=nominal,
        order_id=order.id,
        recipient_name=body.recipient_name,
        recipient_phone=recipient_phone,
        recipient_email=str(body.recipient_email) if body.recipient_email else None,
        message=body.message,
        expires_in_days=int(body.expires_in_days or 365),
        meta={
            "purchase_order_id": str(order.id),
            "sender_name": body.sender_name,
            "send_at": body.send_at,
            "recipient_user_id": str(recipient_user_id) if recipient_user_id else None,
            "design": body.design,
            "accent": body.accent,
            "texture_id": body.texture_id,
        },
    )
    order_meta["gift_certificate_purchase"].update(
        {
            "certificate_id": str(cert.id),
            "certificate_number": cert.number,
        }
    )
    order.meta = order_meta

    payment_data = await svc.create_payment(
        amount_rub=_rub_value(nominal),
        description=f"Подарочный сертификат {cert.number} GLAME.JEWELRY",
        return_url=return_url,
        metadata={
            "order_id": str(order.id),
            "order_type": "gift_certificate_purchase",
            "certificate_id": str(cert.id),
            "certificate_number": cert.number,
        },
    )
    confirmation = payment_data.get("confirmation") or {}
    payment = Payment(
        order_id=order.id,
        provider="yookassa",
        external_id=str(payment_data.get("id")) if payment_data.get("id") else None,
        status=str(payment_data.get("status") or "pending"),
        currency="RUB",
        amount=nominal,
        idempotence_key=str(payment_data.get("_idempotence_key")) if payment_data.get("_idempotence_key") else None,
        confirmation_url=confirmation.get("confirmation_url"),
        raw=payment_data,
    )
    db.add(payment)
    await db.commit()
    await db.refresh(order)
    await db.refresh(payment)
    await db.refresh(cert)
    await _refresh_onec_orders_snapshot(db)

    return {
        "order_id": str(order.id),
        "payment_id": str(payment.id),
        "provider": "yookassa",
        "confirmation_url": payment.confirmation_url,
        "amount": nominal,
        "currency": "RUB",
        "certificate": GiftCertificateService.to_public_dict(cert, include_pin=True),
        "pin": pin,
    }


@router.get("/gift-certificates/my")
async def list_my_gift_certificates(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(GiftCertificate)
            .where(
                or_(
                    GiftCertificate.buyer_user_id == current_user.id,
                    GiftCertificate.recipient_user_id == current_user.id,
                )
            )
            .order_by(desc(GiftCertificate.created_at))
        )
    ).scalars().all()
    return [GiftCertificateService.to_public_dict(row, include_pin=True) for row in rows]


@router.post("/gift-certificates/validate")
async def validate_gift_certificate(
    body: GiftCertificateValidateRequest,
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await GiftCertificateService(db).validate(number=body.number, pin=body.pin)


@router.post("/admin/gift-certificates/redeem-offline")
async def redeem_gift_certificate_offline(
    body: GiftCertificateRedeemOfflineRequest,
    current_user: User = Depends(require_any_role(["admin", "manager", "seller"])),
    db: AsyncSession = Depends(get_db),
):
    cert = await GiftCertificateService(db).redeem_offline(
        number=body.number,
        pin=body.pin,
        amount=int(body.amount or 0),
        store_id=_parse_uuid(body.store_id, "store_id"),
        created_by=current_user.id,
        external_operation_id=body.external_operation_id,
        onec_document_id=body.onec_document_id,
        meta=body.meta,
    )
    await db.commit()
    await db.refresh(cert)
    return GiftCertificateService.to_public_dict(cert, include_private=True, include_pin=True)


@router.get("/admin/gift-certificates")
async def list_gift_certificates_admin(
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    _current_user: User = Depends(require_any_role(["admin", "manager", "seller"])),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(GiftCertificate).order_by(desc(GiftCertificate.created_at)).limit(limit)
    if status:
        stmt = stmt.where(GiftCertificate.status == status)
    rows = (await db.execute(stmt)).scalars().all()
    return [GiftCertificateService.to_public_dict(row, include_private=True, include_pin=True) for row in rows]
