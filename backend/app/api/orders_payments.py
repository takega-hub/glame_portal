from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database.connection import get_db
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.payment import Payment
from app.models.product import Product
from app.models.product_stock import ProductStock
from app.models.user import User
from app.services.gift_certificate_email_service import GiftCertificateEmailService
from app.services.gift_certificate_service import GiftCertificateService
from app.services.yookassa_service import get_yookassa_service


router = APIRouter()


class UpdateOrderDeliveryRequest(BaseModel):
    delivery: Dict[str, Any]


def _parse_uuid(value: str, field: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {field}")


async def _order_to_dict(db: AsyncSession, order: Order) -> Dict[str, Any]:
    items = (
        await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))
    ).scalars().all()
    product_ids = [x.product_id for x in items]
    products: Dict[UUID, Product] = {}
    if product_ids:
        rows = (
            await db.execute(select(Product).where(Product.id.in_(product_ids)))
        ).scalars().all()
        products = {p.id: p for p in rows}

    items_out: List[Dict[str, Any]] = []
    for it in items:
        p = products.get(it.product_id)
        items_out.append(
            {
                "id": str(it.id),
                "product_id": str(it.product_id),
                "quantity": int(it.quantity),
                "unit_price": int(it.unit_price),
                "line_total": int(it.line_total),
                "product": {
                    "id": str(p.id),
                    "name": p.name,
                    "price": p.price,
                    "images": p.images or [],
                }
                if p
                else None,
            }
        )

    payment = (
        await db.execute(
            select(Payment)
            .where(Payment.order_id == order.id)
            .order_by(desc(Payment.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    return {
        "id": str(order.id),
        "status": order.status,
        "currency": order.currency,
        "subtotal_amount": int(order.subtotal_amount),
        "delivery_amount": int(order.delivery_amount),
        "discount_amount": int(order.discount_amount),
        "total_amount": int(order.total_amount),
        "delivery": order.delivery,
        "contact": order.contact,
        "meta": getattr(order, "meta", None),
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
        "items": items_out,
        "payment": (
            {
                "id": str(payment.id),
                "provider": payment.provider,
                "external_id": payment.external_id,
                "status": payment.status,
                "amount": int(payment.amount),
                "currency": payment.currency,
                "confirmation_url": payment.confirmation_url,
                "created_at": payment.created_at.isoformat() if payment.created_at else None,
                "updated_at": payment.updated_at.isoformat() if payment.updated_at else None,
            }
            if payment
            else None
        ),
    }


async def _release_reservation_for_order(db: AsyncSession, order_id: UUID) -> None:
    """
    Best-effort release of reserved stock linked to order items.
    If there was no reservation, quantities remain unchanged.
    """
    items = (
        await db.execute(select(OrderItem).where(OrderItem.order_id == order_id))
    ).scalars().all()
    if not items:
        return

    qty_by_product: Dict[UUID, float] = {}
    for item in items:
        qty_by_product[item.product_id] = qty_by_product.get(item.product_id, 0.0) + float(
            int(item.quantity or 0)
        )

    for product_id, need_release in qty_by_product.items():
        if need_release <= 0:
            continue
        stocks = (
            await db.execute(
                select(ProductStock)
                .where(ProductStock.product_id == product_id)
                .where(ProductStock.reserved_quantity > 0)
                .order_by(desc(ProductStock.reserved_quantity))
            )
        ).scalars().all()
        remaining = float(need_release)
        for stock in stocks:
            if remaining <= 0:
                break
            can_release = min(float(stock.reserved_quantity or 0), remaining)
            if can_release <= 0:
                continue
            stock.reserved_quantity = max(0.0, float(stock.reserved_quantity or 0) - can_release)
            stock.available_quantity = float(stock.available_quantity or 0) + can_release
            remaining -= can_release


async def _sync_payment_with_provider(
    db: AsyncSession,
    order: Order,
    payment: Optional[Payment],
) -> None:
    if not payment or payment.provider != "yookassa" or not payment.external_id:
        return
    if payment.status in {"succeeded", "canceled"}:
        return

    svc = get_yookassa_service()
    if not svc:
        return

    remote = await svc.get_payment(payment.external_id)
    remote_status = str(remote.get("status") or "pending")
    payment.status = remote_status
    payment.raw = remote

    if remote_status == "succeeded" and order.status in {"pending", "payment_pending"}:
        order.status = "paid"
        meta = order.meta if isinstance(order.meta, dict) else {}
        gift_service = GiftCertificateService(db)
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
    if remote_status == "canceled" and order.status in {"pending", "payment_pending"}:
        order.status = "canceled"
        await GiftCertificateService(db).cancel_order_certificates(order.id)


@router.get("/orders")
async def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Order)
        .where(Order.user_id == current_user.id)
        .order_by(desc(Order.created_at))
        .offset(skip)
        .limit(limit)
    )
    orders = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(o.id),
            "status": o.status,
            "currency": o.currency,
            "total_amount": int(o.total_amount),
            "delivery": o.delivery,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }
        for o in orders
    ]


@router.get("/orders/{order_id}")
async def get_order(
    order_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    oid = _parse_uuid(order_id, "order_id")
    order = (
        await db.execute(select(Order).where(Order.id == oid, Order.user_id == current_user.id))
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return await _order_to_dict(db, order)


@router.get("/orders/{order_id}/payment-status")
async def get_order_payment_status(
    order_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    oid = _parse_uuid(order_id, "order_id")
    order = (
        await db.execute(select(Order).where(Order.id == oid, Order.user_id == current_user.id))
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    payment = (
        await db.execute(
            select(Payment)
            .where(Payment.order_id == order.id)
            .order_by(desc(Payment.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    await _sync_payment_with_provider(db, order, payment)
    await db.commit()
    if payment:
        await db.refresh(payment)
    await db.refresh(order)

    return {
        "order_id": str(order.id),
        "order_status": order.status,
        "payment": (
            {
                "payment_id": str(payment.id),
                "provider": payment.provider,
                "status": payment.status,
                "amount": int(payment.amount),
                "currency": payment.currency,
                "confirmation_url": payment.confirmation_url,
                "updated_at": payment.updated_at.isoformat() if payment.updated_at else None,
            }
            if payment
            else None
        ),
    }


@router.get("/payments/{payment_id}")
async def get_payment(
    payment_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pid = _parse_uuid(payment_id, "payment_id")
    payment = (
        await db.execute(select(Payment).where(Payment.id == pid))
    ).scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    order = (
        await db.execute(select(Order).where(Order.id == payment.order_id, Order.user_id == current_user.id))
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Payment not found")

    return {
        "id": str(payment.id),
        "order_id": str(payment.order_id),
        "provider": payment.provider,
        "external_id": payment.external_id,
        "status": payment.status,
        "amount": int(payment.amount),
        "currency": payment.currency,
        "confirmation_url": payment.confirmation_url,
        "raw": payment.raw,
        "created_at": payment.created_at.isoformat() if payment.created_at else None,
        "updated_at": payment.updated_at.isoformat() if payment.updated_at else None,
    }


@router.post("/payments/{payment_id}/refresh")
async def refresh_payment(
    payment_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = get_yookassa_service()
    if not svc:
        raise HTTPException(status_code=500, detail="YOOKASSA is not configured")

    pid = _parse_uuid(payment_id, "payment_id")
    payment = (
        await db.execute(select(Payment).where(Payment.id == pid))
    ).scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    order = (
        await db.execute(select(Order).where(Order.id == payment.order_id, Order.user_id == current_user.id))
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Payment not found")

    if not payment.external_id:
        raise HTTPException(status_code=400, detail="Payment has no external_id")

    await _sync_payment_with_provider(db, order, payment)

    await db.commit()
    await db.refresh(payment)
    await db.refresh(order)

    return {
        "payment_id": str(payment.id),
        "order_id": str(order.id),
        "status": payment.status,
        "order_status": order.status,
    }


@router.get("/payments/last-active")
async def get_last_active_payment(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Payment, Order)
        .join(Order, Payment.order_id == Order.id)
        .where(Order.user_id == current_user.id)
        .where(Payment.status.notin_(["succeeded", "canceled"]))
        .order_by(desc(Payment.created_at))
        .limit(1)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        return None
    payment, order = row
    return {
        "payment_id": str(payment.id),
        "order_id": str(order.id),
        "provider": payment.provider,
        "status": payment.status,
        "amount": int(payment.amount),
        "currency": payment.currency,
        "confirmation_url": payment.confirmation_url,
        "order_status": order.status,
        "created_at": payment.created_at.isoformat() if payment.created_at else None,
        "updated_at": payment.updated_at.isoformat() if payment.updated_at else None,
    }


@router.put("/orders/{order_id}/delivery")
async def update_order_delivery(
    order_id: str,
    body: UpdateOrderDeliveryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    oid = _parse_uuid(order_id, "order_id")
    order = (
        await db.execute(select(Order).where(Order.id == oid, Order.user_id == current_user.id))
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status in {"delivered", "canceled"}:
        raise HTTPException(status_code=400, detail="Order delivery can no longer be changed")

    current_delivery = order.delivery if isinstance(order.delivery, dict) else {}
    next_delivery = {**current_delivery, **(body.delivery or {})}
    order.delivery = next_delivery
    await db.commit()
    await db.refresh(order)
    return {
        "order_id": str(order.id),
        "status": order.status,
        "delivery": order.delivery,
    }


@router.delete("/orders/{order_id}")
async def delete_order(
    order_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    oid = _parse_uuid(order_id, "order_id")
    order = (
        await db.execute(select(Order).where(Order.id == oid, Order.user_id == current_user.id))
    ).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    payment = (
        await db.execute(
            select(Payment).where(Payment.order_id == order.id).order_by(desc(Payment.created_at)).limit(1)
        )
    ).scalar_one_or_none()
    payment_status = (payment.status if payment else None) or "pending"

    # User requirement: allow deleting order if it is not paid or already shipped.
    can_delete = payment_status != "succeeded" or order.status == "shipped"
    if not can_delete:
        raise HTTPException(status_code=400, detail="Only unpaid or shipped orders can be deleted")

    await _release_reservation_for_order(db, order.id)
    await db.execute(delete(Payment).where(Payment.order_id == order.id))
    await db.execute(delete(OrderItem).where(OrderItem.order_id == order.id))
    await db.delete(order)
    await db.commit()

    return {
        "deleted": True,
        "order_id": str(oid),
        "reservation_released": True,
    }
