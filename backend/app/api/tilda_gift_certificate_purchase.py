"""Public, cart-independent sale of electronic certificates from Tilda."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.models.gift_certificate import GiftCertificate
from app.models.tilda_gift_certificate_purchase import TildaGiftCertificatePurchase
from app.services.gift_certificate_email_service import GiftCertificateEmailService
from app.services.gift_certificate_service import GiftCertificateService
from app.services.yookassa_service import get_yookassa_service_for_db


router = APIRouter()


def _origins() -> set[str]:
    raw = os.getenv("TILDA_GIFT_CERTIFICATE_ALLOWED_ORIGINS", "")
    return {value.strip().rstrip("/") for value in raw.split(",") if value.strip()}


def _require_tilda_origin(request: Request) -> None:
    origin = str(request.headers.get("origin") or "").strip().rstrip("/")
    if not _origins() or origin not in _origins():
        raise HTTPException(status_code=403, detail="Request origin is not allowed")


class Recipient(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: EmailStr


class Sender(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class Delivery(BaseModel):
    mode: Literal["now", "scheduled"]
    send_at: Optional[datetime] = None


class ReceiptContact(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def exactly_one_contact(self):
        if bool(self.email) == bool(self.phone):
            raise ValueError("Provide exactly one receipt contact")
        return self


class PurchaseRequest(BaseModel):
    design: str = Field(min_length=1, max_length=32)
    nominal_amount: int = Field(gt=0)
    recipient: Recipient
    sender: Sender
    message: Optional[str] = Field(default=None, max_length=500)
    delivery: Delivery
    buyer_receipt_contact: ReceiptContact
    return_url: str = Field(min_length=8, max_length=2000)


def _enabled() -> bool:
    return os.getenv("TILDA_GIFT_CERTIFICATE_PURCHASE_ENABLED", "false").lower() in {"1", "true", "yes"}


def _amounts() -> list[int]:
    raw = os.getenv("TILDA_GIFT_CERTIFICATE_PURCHASE_ALLOWED_AMOUNTS", "500000,1000000,1500000,2000000,3000000,5000000")
    return sorted({int(value.strip()) for value in raw.split(",") if value.strip().isdigit() and int(value.strip()) > 0})


def _token_secret() -> bytes:
    value = os.getenv("TILDA_GIFT_CERTIFICATE_INTERNAL_SECRET") or os.getenv("GIFT_CERTIFICATE_SECRET")
    if not value:
        raise HTTPException(status_code=503, detail="Gift certificate service is temporarily unavailable")
    return value.encode()


def _status_token(purchase_id: UUID) -> str:
    signature = hmac.new(_token_secret(), str(purchase_id).encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(signature).decode().rstrip("=")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _request_hash(body: PurchaseRequest) -> str:
    return _hash(json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))


def _return_url(value: str) -> str:
    parsed = urlsplit(value)
    origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    if parsed.scheme != "https" or origin not in _origins():
        raise HTTPException(status_code=422, detail="Invalid return URL")
    return value


def _receipt(purchase: TildaGiftCertificatePurchase) -> dict:
    vat_code = os.getenv("TILDA_GIFT_CERTIFICATE_RECEIPT_VAT_CODE", "").strip()
    payment_subject = os.getenv("TILDA_GIFT_CERTIFICATE_RECEIPT_PAYMENT_SUBJECT", "").strip()
    payment_mode = os.getenv("TILDA_GIFT_CERTIFICATE_RECEIPT_PAYMENT_MODE", "").strip()
    if not vat_code or not payment_subject or not payment_mode:
        raise HTTPException(status_code=503, detail="Gift certificate receipt configuration is unavailable")
    contact = purchase.buyer_contact if isinstance(purchase.buyer_contact, dict) else {}
    customer = {key: str(contact[key]).strip() for key in ("email", "phone") if contact.get(key)}
    if len(customer) != 1:
        raise HTTPException(status_code=422, detail="A receipt contact is required")
    receipt = {
        "customer": customer,
        "items": [{
            "description": "Электронный подарочный сертификат GLAME",
            "quantity": "1.00",
            "amount": {"value": f"{purchase.nominal_amount / 100:.2f}", "currency": "RUB"},
            "vat_code": int(vat_code),
            "payment_subject": payment_subject,
            "payment_mode": payment_mode,
        }],
    }
    tax_system_code = os.getenv("TILDA_GIFT_CERTIFICATE_RECEIPT_TAX_SYSTEM_CODE", "").strip()
    if tax_system_code:
        receipt["tax_system_code"] = int(tax_system_code)
    return receipt


def _public(purchase: TildaGiftCertificatePurchase) -> dict:
    payload = {"purchase_id": str(purchase.id), "status": purchase.status, "amount": purchase.nominal_amount, "currency": "RUB"}
    if purchase.status in {"issued", "scheduled", "sent"} and purchase.certificate_id:
        payload.update({"delivery_mode": purchase.delivery_mode, "sent_at": purchase.sent_at.isoformat() if purchase.sent_at else None})
    return payload


@router.get("/public/tilda/gift-certificates/purchase-config")
async def purchase_config(request: Request):
    _require_tilda_origin(request)
    return {"enabled": _enabled(), "currency": "RUB", "allowed_amounts": _amounts(), "designs": [{"code": "light", "title": "Светлый"}, {"code": "dark", "title": "Тёмный"}], "validity_months": 6, "delivery_modes": ["now", "scheduled"], "timezone": "Europe/Moscow", "max_schedule_days": 180}


@router.post("/public/tilda/gift-certificates/purchases", status_code=201)
async def create_purchase(body: PurchaseRequest, request: Request, idempotency_key: str = Header(alias="Idempotency-Key"), db: AsyncSession = Depends(get_db)):
    _require_tilda_origin(request)
    if not _enabled():
        raise HTTPException(status_code=503, detail="Gift certificate sales are temporarily unavailable")
    key = str(idempotency_key or "").strip()
    if not key:
        raise HTTPException(status_code=422, detail="Idempotency-Key is required")
    digest = _request_hash(body)
    existing = (await db.execute(select(TildaGiftCertificatePurchase).where(TildaGiftCertificatePurchase.idempotency_key == key))).scalar_one_or_none()
    if existing:
        if existing.request_hash != digest:
            raise HTTPException(status_code=409, detail="IDEMPOTENCY_CONFLICT")
        return {**_public(existing), "payment": {"provider": "yookassa", "payment_id": existing.payment_id, "confirmation_url": existing.confirmation_url}, "status_token": _status_token(existing.id), "created_at": existing.created_at.isoformat()}
    if body.design not in {"light", "dark"} or body.nominal_amount not in _amounts():
        raise HTTPException(status_code=422, detail="Unsupported certificate option")
    send_at = body.delivery.send_at
    now = datetime.now(timezone.utc)
    if body.delivery.mode == "scheduled" and (not send_at or send_at <= now or send_at > now + timedelta(days=180)):
        raise HTTPException(status_code=422, detail="Invalid scheduled delivery time")
    if body.delivery.mode == "now" and send_at:
        raise HTTPException(status_code=422, detail="send_at is only valid for scheduled delivery")
    purchase = TildaGiftCertificatePurchase(idempotency_key=key, request_hash=digest, status_token_hash="pending", nominal_amount=body.nominal_amount, design=body.design, recipient_name=body.recipient.name.strip(), recipient_email=str(body.recipient.email).lower(), sender_name=body.sender.name.strip(), message=(body.message or "").strip() or None, delivery_mode=body.delivery.mode, send_at=send_at, buyer_contact=body.buyer_receipt_contact.model_dump(mode="json", exclude_none=True), return_url=_return_url(body.return_url))
    db.add(purchase)
    await db.flush()
    purchase.status_token_hash = _hash(_status_token(purchase.id))
    svc = await get_yookassa_service_for_db(db)
    if not svc:
        raise HTTPException(status_code=503, detail="Online payment is temporarily unavailable")
    payment = await svc.create_payment(
        amount_rub=f"{purchase.nominal_amount / 100:.2f}",
        description="Электронный подарочный сертификат GLAME",
        return_url=purchase.return_url,
        metadata={"source": "tilda_gift_certificate_purchase", "purchase_id": str(purchase.id)},
        receipt=_receipt(purchase),
        idempotence_key=f"tilda-gift-purchase:{purchase.id}",
    )
    purchase.payment_id = str(payment.get("id") or "") or None
    purchase.confirmation_url = str((payment.get("confirmation") or {}).get("confirmation_url") or "") or None
    if not purchase.payment_id or not purchase.confirmation_url:
        raise HTTPException(status_code=502, detail="Online payment is temporarily unavailable")
    await db.commit()
    await db.refresh(purchase)
    return {**_public(purchase), "payment": {"provider": "yookassa", "payment_id": purchase.payment_id, "confirmation_url": purchase.confirmation_url}, "status_token": _status_token(purchase.id), "created_at": purchase.created_at.isoformat()}


@router.get("/public/tilda/gift-certificates/purchases/{purchase_id}")
async def get_purchase(purchase_id: UUID, request: Request, token: str = Header(alias="X-Purchase-Token"), db: AsyncSession = Depends(get_db)):
    _require_tilda_origin(request)
    purchase = await db.get(TildaGiftCertificatePurchase, purchase_id)
    if not purchase or not hmac.compare_digest(purchase.status_token_hash, _hash(str(token or ""))):
        raise HTTPException(status_code=404, detail="Purchase not found")
    return _public(purchase)


async def process_purchase_payment(db: AsyncSession, *, payment_id: str, yookassa_service) -> bool:
    """Issue exactly one Tilda certificate after YooKassa confirms payment."""
    purchase = (
        await db.execute(
            select(TildaGiftCertificatePurchase)
            .where(TildaGiftCertificatePurchase.payment_id == payment_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not purchase:
        return False
    remote = await yookassa_service.get_payment(payment_id)
    metadata = remote.get("metadata") if isinstance(remote.get("metadata"), dict) else {}
    amount = remote.get("amount") if isinstance(remote.get("amount"), dict) else {}
    if str(metadata.get("purchase_id") or "") != str(purchase.id) or str(amount.get("currency") or "") != "RUB":
        purchase.status = "failed"
        purchase.error = "Payment metadata verification failed"
        await db.commit()
        return True
    if str(remote.get("status") or "").lower() == "canceled":
        purchase.status = "canceled"
        await db.commit()
        return True
    if str(remote.get("status") or "").lower() != "succeeded" or not bool(remote.get("paid")) or amount.get("value") != f"{purchase.nominal_amount / 100:.2f}":
        return True
    purchase.status = "paid_pending_issue"
    try:
        certificates = GiftCertificateService(db)
        cert = await db.get(GiftCertificate, purchase.certificate_id) if purchase.certificate_id else None
        if not cert:
            cert, _pin = await certificates.create_pending_certificate(
                buyer_user_id=None,
                nominal_amount=purchase.nominal_amount,
                order_id=None,
                recipient_name=purchase.recipient_name,
                recipient_email=purchase.recipient_email,
                message=purchase.message,
                expires_in_months=6,
                pin_required=False,
                meta={"source": "tilda_purchase", "purchase_id": str(purchase.id), "sender_name": purchase.sender_name, "design": purchase.design, "send_at": purchase.send_at.isoformat() if purchase.send_at else None},
            )
            purchase.certificate_id = cert.id
            # Persist the 1C series reference before posting the starting
            # balance. A retry then resumes this certificate rather than
            # creating another series after a transient 1C failure.
            await db.commit()
            await db.refresh(purchase)
            await db.refresh(cert)
        if cert.status == "active":
            return True
        await certificates.ensure_onec_certificate_balance(cert, source="tilda_purchase")
        cert.status = "active"
        cert.balance_amount = cert.nominal_amount
        cert.issued_at = datetime.now(timezone.utc)
        cert.activated_at = cert.issued_at
        certificates._add_tx(cert, "activation", cert.nominal_amount, source="tilda_purchase")
        if purchase.delivery_mode == "scheduled":
            purchase.status = "scheduled"
        else:
            try:
                sent = await GiftCertificateEmailService(db).send_gift_certificate(cert)
            except Exception as exc:
                purchase.status = "failed"
                purchase.error = f"Certificate email was not sent: {exc}"
                await db.commit()
                return True
            if not sent:
                purchase.status = "failed"
                purchase.error = "Certificate email was not sent"
            else:
                purchase.status = "sent"
                purchase.error = None
                purchase.sent_at = datetime.now(timezone.utc)
        await db.commit()
    except Exception:
        purchase.status = "paid_pending_issue"
        purchase.error = "Certificate issue is pending"
        await db.commit()
    return True
