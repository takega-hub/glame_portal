"""Hosted checkout bridge for a Tilda cart paid with a GLAME certificate.

Tilda keeps its standard YooKassa integration for ordinary orders.  This
router is used only by the certificate UI injected into the existing cart:
it creates a reservation first and charges YooKassa only for the remaining
amount.  Certificate numbers and PINs never reach YooKassa or Tilda.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.tilda_gift_certificates import (
    CartItem,
    _origins,
    _require_one_c_operations_bridge,
    _require_tilda_origin,
)
from app.database.connection import get_db
from app.models.tilda_gift_certificate_operation import TildaGiftCertificateOperation
from app.services.tilda_gift_certificate_service import TildaGiftCertificateService
from app.services.yookassa_service import get_yookassa_service_for_db


router = APIRouter()


class CheckoutRequest(BaseModel):
    """Cart snapshot supplied by the GLAME certificate widget in Tilda."""

    validation_token: str = Field(min_length=32, max_length=2048)
    amount: int = Field(gt=0)
    checkout_id: str = Field(min_length=16, max_length=128)
    cart_total: int = Field(gt=0)
    cart_fingerprint: str = Field(min_length=8, max_length=128)
    return_url: str = Field(min_length=8, max_length=2000)
    items: Optional[list[CartItem]] = None


def _rub(amount_kopeks: int) -> str:
    return f"{max(0, int(amount_kopeks or 0)) / 100:.2f}"


def _validate_return_url(value: str) -> str:
    """Never turn the payment flow into an open redirect."""
    url = str(value or "").strip()
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise HTTPException(status_code=422, detail="Invalid return URL")
    origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    if origin not in _origins():
        raise HTTPException(status_code=422, detail="Invalid return URL")
    return url


async def _operation_for_checkout(
    db: AsyncSession, checkout_id: str, *, lock: bool = False
) -> TildaGiftCertificateOperation:
    stmt = (
        select(TildaGiftCertificateOperation)
        .where(TildaGiftCertificateOperation.operation_type == "reserve")
        .where(TildaGiftCertificateOperation.tilda_order_id == checkout_id)
    )
    if lock:
        stmt = stmt.with_for_update()
    operation = (await db.execute(stmt)).scalar_one_or_none()
    if not operation:
        raise HTTPException(status_code=404, detail="Checkout not found")
    return operation


@router.post("/public/tilda/gift-certificates/checkout")
async def create_certificate_checkout(
    body: CheckoutRequest,
    request: Request,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
):
    """Reserve the certificate and create a YooKassa payment for the balance.

    The browser receives only a YooKassa confirmation URL and opaque operation
    identifiers.  It never receives a 1C reference, payment secret or PIN.
    """
    _require_tilda_origin(request)
    _require_one_c_operations_bridge()
    if not str(idempotency_key or "").strip():
        raise HTTPException(status_code=422, detail="Idempotency-Key is required")

    return_url = _validate_return_url(body.return_url)
    items = [item.model_dump() for item in body.items] if body.items else []
    certificates = TildaGiftCertificateService(db)
    reserved = await certificates.reserve(
        validation_token=body.validation_token,
        amount=int(body.amount),
        tilda_order_id=body.checkout_id,
        cart_total=int(body.cart_total),
        cart_fingerprint=body.cart_fingerprint,
        idempotency_key=str(idempotency_key),
    )
    operation = await _operation_for_checkout(db, body.checkout_id, lock=True)
    due = max(0, int(operation.cart_total or 0) - int(operation.amount or 0))
    operation.meta = {
        **(operation.meta or {}),
        "checkout": "tilda_hosted",
        "return_url": return_url,
        "items": items,
    }
    # Persist the reservation before calling an external payment API.  A network
    # timeout can then only leave a recoverable reservation, never a double debit.
    await db.commit()

    if due == 0:
        result = await certificates.confirm(
            operation_id=operation.id,
            tilda_order_id=body.checkout_id,
            payment_status="succeeded",
            payment_id=f"zero:{body.checkout_id}",
            order_amount=int(operation.cart_total or 0),
            payment_amount=0,
            items=items,
            idempotency_key=f"{idempotency_key}:zero",
        )
        await db.commit()
        return {
            "status": "paid",
            "payment_required": False,
            "operation": result,
        }

    # An idempotent retry after a created payment must reuse the same link.
    if operation.payment_id:
        return {
            "status": "pending_payment",
            "payment_required": True,
            "operation": reserved,
            "payment_id": operation.payment_id,
            "confirmation_url": (operation.meta or {}).get("confirmation_url"),
        }

    yookassa = await get_yookassa_service_for_db(db)
    if not yookassa:
        raise HTTPException(status_code=503, detail="Online payment is temporarily unavailable")
    try:
        payment = await yookassa.create_payment(
            amount_rub=_rub(due),
            description=f"Заказ GLAME.JEWELRY {body.checkout_id}",
            return_url=return_url,
            metadata={
                "source": "tilda_gift_certificate_checkout",
                "certificate_operation_id": str(operation.id),
                "checkout_id": body.checkout_id,
                "order_amount": str(operation.cart_total or 0),
                "certificate_amount": str(operation.amount or 0),
            },
            idempotence_key=body.checkout_id,
        )
        confirmation = payment.get("confirmation") or {}
        confirmation_url = str(confirmation.get("confirmation_url") or "")
        payment_id = str(payment.get("id") or "")
        if not payment_id or not confirmation_url:
            raise RuntimeError("YooKassa did not return a payment confirmation URL")
    except Exception as exc:
        # A certificate is reserved before the outbound request by design.  If
        # the payment provider is unavailable, return it immediately instead
        # of making the buyer wait for the 30-minute expiry task.
        await certificates.release(
            operation_id=operation.id,
            tilda_order_id=body.checkout_id,
            reason="payment_failed",
            idempotency_key=f"{idempotency_key}:payment-failed",
        )
        await db.commit()
        raise HTTPException(status_code=503, detail="Online payment is temporarily unavailable") from exc

    # The YooKassa webhook locates this reservation using payment_id and only
    # then confirms the certificate and posts the debit to 1C.
    operation = await _operation_for_checkout(db, body.checkout_id, lock=True)
    operation.payment_id = payment_id
    operation.meta = {
        **(operation.meta or {}),
        "confirmation_url": confirmation_url,
        "yookassa_status": str(payment.get("status") or "pending"),
    }
    await db.commit()
    return {
        "status": "pending_payment",
        "payment_required": True,
        "operation": TildaGiftCertificateService.serialize(operation),
        "payment_id": payment_id,
        "confirmation_url": confirmation_url,
    }


@router.get("/public/tilda/gift-certificates/checkout/{checkout_id}")
async def get_certificate_checkout(
    checkout_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Status endpoint used by the cart when the buyer returns from YooKassa."""
    _require_tilda_origin(request)
    operation = await _operation_for_checkout(db, checkout_id)
    return TildaGiftCertificateService.serialize(operation)
