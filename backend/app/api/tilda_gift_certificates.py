from __future__ import annotations

import hmac
import os
import time
from collections import defaultdict, deque
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.services.tilda_gift_certificate_service import TildaGiftCertificateService


router = APIRouter()

# Short per-process protection. Production also needs an equivalent proxy/WAF rule.
_attempts: dict[str, deque[float]] = defaultdict(deque)


class CartItem(BaseModel):
    sku: Optional[str] = None
    quantity: int = Field(default=1, ge=1, le=100)
    unit_price: int = Field(default=0, ge=0)
    is_gift_certificate: bool = False


class ValidateRequest(BaseModel):
    number: str = Field(min_length=3, max_length=64)
    pin: Optional[str] = Field(default=None, max_length=32)
    cart_total: int = Field(gt=0)
    cart_fingerprint: str = Field(min_length=8, max_length=128)
    items: Optional[list[CartItem]] = None


class ReserveRequest(BaseModel):
    validation_token: str = Field(min_length=32, max_length=2048)
    amount: int = Field(gt=0)
    tilda_order_id: str = Field(min_length=1, max_length=128)
    cart_total: int = Field(gt=0)
    cart_fingerprint: str = Field(min_length=8, max_length=128)


class ConfirmRequest(BaseModel):
    operation_id: UUID
    tilda_order_id: str = Field(min_length=1, max_length=128)
    payment_status: str = Field(min_length=1, max_length=32)
    payment_id: Optional[str] = Field(default=None, max_length=128)
    order_amount: int = Field(ge=0)
    payment_amount: int = Field(ge=0)
    items: Optional[list[CartItem]] = None


class ReleaseRequest(BaseModel):
    operation_id: UUID
    tilda_order_id: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=64)


class RefundRequest(BaseModel):
    original_operation_id: UUID
    tilda_order_id: str = Field(min_length=1, max_length=128)
    refund_id: str = Field(min_length=1, max_length=128)
    amount: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=128)


def _origins() -> set[str]:
    configured = os.getenv("TILDA_GIFT_CERTIFICATE_ALLOWED_ORIGINS", "")
    return {value.strip().rstrip("/") for value in configured.split(",") if value.strip()}


def _require_tilda_origin(request: Request) -> None:
    allowed = _origins()
    if not allowed:
        raise HTTPException(status_code=503, detail="Gift certificate service is temporarily unavailable")
    origin = (request.headers.get("origin") or "").strip().rstrip("/")
    if origin not in allowed:
        raise HTTPException(status_code=403, detail="Request origin is not allowed")


def _rate_limit(request: Request, number: str) -> None:
    host = request.client.host if request.client else "unknown"
    key = f"{host}:{str(number).strip().upper()}"
    now = time.monotonic()
    attempts = _attempts[key]
    while attempts and now - attempts[0] > 600:
        attempts.popleft()
    if len(attempts) >= 8:
        raise HTTPException(status_code=429, detail="Too many certificate validation attempts")
    attempts.append(now)


def _require_internal_secret(authorization: Optional[str]) -> None:
    expected = (os.getenv("TILDA_GIFT_CERTIFICATE_INTERNAL_SECRET") or "").strip()
    received = str(authorization or "")
    prefix = "Bearer "
    if not expected:
        raise HTTPException(status_code=503, detail="Gift certificate service is temporarily unavailable")
    if not received.startswith(prefix) or not hmac.compare_digest(received[len(prefix) :], expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/public/tilda/gift-certificates/validate")
async def validate_certificate(body: ValidateRequest, request: Request, db: AsyncSession = Depends(get_db)):
    _require_tilda_origin(request)
    _rate_limit(request, body.number)
    result = await TildaGiftCertificateService(db).validate(
        number=body.number,
        pin=body.pin,
        cart_total=body.cart_total,
        cart_fingerprint=body.cart_fingerprint,
        items=[item.model_dump() for item in body.items] if body.items else None,
    )
    await db.commit()
    return result


@router.post("/public/tilda/gift-certificates/reserve")
async def reserve_certificate(
    body: ReserveRequest,
    request: Request,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
):
    _require_tilda_origin(request)
    result = await TildaGiftCertificateService(db).reserve(
        validation_token=body.validation_token,
        amount=body.amount,
        tilda_order_id=body.tilda_order_id,
        cart_total=body.cart_total,
        cart_fingerprint=body.cart_fingerprint,
        idempotency_key=str(idempotency_key or ""),
    )
    await db.commit()
    return result


@router.post("/internal/tilda/gift-certificates/confirm")
async def confirm_certificate(
    body: ConfirmRequest,
    authorization: Optional[str] = Header(default=None),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
):
    _require_internal_secret(authorization)
    result = await TildaGiftCertificateService(db).confirm(
        operation_id=body.operation_id,
        tilda_order_id=body.tilda_order_id,
        payment_status=body.payment_status,
        payment_id=body.payment_id,
        order_amount=body.order_amount,
        payment_amount=body.payment_amount,
        items=[item.model_dump() for item in body.items] if body.items else None,
        idempotency_key=str(idempotency_key or ""),
    )
    await db.commit()
    return result


@router.post("/internal/tilda/gift-certificates/release")
async def release_certificate(
    body: ReleaseRequest,
    authorization: Optional[str] = Header(default=None),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
):
    _require_internal_secret(authorization)
    allowed = {"checkout_abandoned", "payment_canceled", "payment_failed", "order_canceled", "reservation_expired"}
    if body.reason not in allowed:
        raise HTTPException(status_code=422, detail="Unsupported release reason")
    result = await TildaGiftCertificateService(db).release(
        operation_id=body.operation_id,
        tilda_order_id=body.tilda_order_id,
        reason=body.reason,
        idempotency_key=str(idempotency_key or ""),
    )
    await db.commit()
    return result


@router.post("/internal/tilda/gift-certificates/refund")
async def refund_certificate(
    body: RefundRequest,
    authorization: Optional[str] = Header(default=None),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
):
    _require_internal_secret(authorization)
    result = await TildaGiftCertificateService(db).refund(
        original_operation_id=body.original_operation_id,
        tilda_order_id=body.tilda_order_id,
        refund_id=body.refund_id,
        amount=body.amount,
        reason=body.reason,
        idempotency_key=str(idempotency_key or ""),
    )
    await db.commit()
    return result


@router.get("/internal/tilda/gift-certificates/operations/{operation_id}")
async def get_certificate_operation(
    operation_id: UUID,
    authorization: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    _require_internal_secret(authorization)
    return await TildaGiftCertificateService(db).get_operation(operation_id)
