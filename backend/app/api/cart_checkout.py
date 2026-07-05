import os
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, normalize_phone
from app.database.connection import get_db
from app.models.cart import Cart
from app.models.cart_item import CartItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.payment import Payment
from app.models.product import Product
from app.models.glame_token import GlameTokenAccount
from app.models.referral import ReferralAttribution, ReferralCommission, ReferralProgramMember
from app.models.user import User
from app.services.gift_certificate_service import GiftCertificateService
from app.services.loyalty_service import LoyaltyService
from app.services.onec_user_registration_payload import OneCUserRegistrationPayload
from app.services.onec_user_sync_service import OneCUserSyncService
from app.services.onec_order_xml_service import write_orders_xml_snapshot
from app.services.referral_service import ReferralService
from app.services.glame_token_service import GlameTokenService
from app.services.yookassa_service import get_yookassa_service


router = APIRouter()
logger = logging.getLogger(__name__)
APP_CLIENT_CUSTOMER_GROUP_KEY = os.getenv(
    "ONEC_APP_CLIENT_CUSTOMER_GROUP_KEY",
    "68442a44-7397-11f1-876b-fa163e4cc04e",
)


class CartItemIn(BaseModel):
    product_id: str
    quantity: int = Field(ge=1, le=99)

class CartItemQtyIn(BaseModel):
    quantity: int = Field(ge=0, le=99)


class CheckoutRequest(BaseModel):
    return_url: str
    payment_method: Literal["card", "cod"] = "card"
    delivery: Optional[Dict[str, Any]] = None
    contact: Optional[Dict[str, Any]] = None
    meta: Optional[Dict[str, Any]] = None
    delivery_amount: int = Field(default=0, ge=0)
    discount_amount: int = Field(default=0, ge=0)
    use_bonus_points: int = Field(default=0, ge=0)
    use_glm_amount: int = Field(default=0, ge=0)
    gift_certificate: Optional[Dict[str, Any]] = None


def _rub_value(amount_kopeks: int) -> str:
    return f"{amount_kopeks / 100.0:.2f}"


def _bonus_points_to_kopeks(points: int) -> int:
    return max(0, int(points or 0)) * 100


async def _refresh_onec_orders_snapshot(db: AsyncSession) -> None:
    try:
        await write_orders_xml_snapshot(db)
    except Exception as e:
        logger.warning("Не удалось обновить orders.xml для обмена с 1С: %s", e)


def _extract_referral_code(meta: Dict[str, Any]) -> str | None:
    raw = meta.get("referral_code")
    if not raw and isinstance(meta.get("referral"), dict):
        raw = meta["referral"].get("code")
    value = str(raw or "").strip()
    return value or None


async def _attach_referral_to_order(
    db: AsyncSession,
    *,
    order: Order,
    current_user: User,
    order_meta: Dict[str, Any],
    commission_base: int,
) -> None:
    referral_code = _extract_referral_code(order_meta)
    existing = (
        await db.execute(
            select(ReferralAttribution)
            .where(
                ReferralAttribution.referee_user_id == current_user.id,
                ReferralAttribution.status.in_(["pending", "active"]),
            )
            .order_by(ReferralAttribution.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()

    service = ReferralService(db)
    attribution = existing
    code = None
    if attribution is None and referral_code:
        code = await service.validate_code(referral_code)
        if code is None:
            raise HTTPException(status_code=400, detail="Invalid referral code")
        member = (
            await db.execute(select(ReferralProgramMember).where(ReferralProgramMember.id == code.member_id))
        ).scalar_one_or_none()
        if member and member.user_id == current_user.id:
            raise HTTPException(status_code=400, detail="Cannot use own referral code")
        attribution = ReferralAttribution(
            referrer_member_id=code.member_id,
            referral_code_id=code.id,
            referee_user_id=current_user.id,
            status="hold",
            source="checkout",
            first_purchase_order_id=order.id,
            meta={"order_id": str(order.id)},
        )
        code.usage_count = int(code.usage_count or 0) + 1
        db.add(attribution)
        await db.flush()

    if attribution is None:
        return

    member = (
        await db.execute(select(ReferralProgramMember).where(ReferralProgramMember.id == attribution.referrer_member_id))
    ).scalar_one_or_none()
    if member is None or member.status != "active":
        return

    existing_commission = (
        await db.execute(
            select(ReferralCommission).where(
                ReferralCommission.order_id == order.id,
                ReferralCommission.referrer_member_id == member.id,
            )
        )
    ).scalar_one_or_none()
    if existing_commission is None:
        reward_mode = member.reward_mode or "points"
        rate, rate_promotion = service.effective_reward_rate(member)
        amount_kopecks = int(max(0, commission_base) * rate / Decimal("100"))
        points = amount_kopecks // 100 if reward_mode == "points" else 0
        commission_meta = {"order_id": str(order.id), "source": "checkout"}
        if rate_promotion:
            commission_meta["rate_promotion"] = {
                "id": rate_promotion.get("id"),
                "title": rate_promotion.get("title"),
                "rate_percent": rate_promotion.get("rate_percent"),
                "starts_at": rate_promotion.get("starts_at"),
                "ends_at": rate_promotion.get("ends_at"),
            }
        commission = ReferralCommission(
            attribution_id=attribution.id,
            referrer_member_id=member.id,
            referee_user_id=current_user.id,
            order_id=order.id,
            reward_mode=reward_mode,
            commission_base=max(0, commission_base),
            rate_percent=rate,
            amount_kopecks=amount_kopecks,
            points=points,
            status="pending",
            hold_until=ReferralService.default_hold_until(),
            meta=commission_meta,
        )
        db.add(commission)
        await db.flush()
        await GlameTokenService(db).issue_referral_commission_hold(
            commission=commission,
            member=member,
        )

    if attribution.status == "pending":
        now = datetime.now(timezone.utc)
        attribution.status = "active"
        attribution.first_purchase_order_id = order.id
        attribution.first_purchase_at = now
        attribution.activated_at = now

    referral_meta = {
        "code": code.code if code else referral_code,
        "attribution_id": str(attribution.id),
        "partner_member_id": str(member.id),
        "reward_mode": member.reward_mode,
    }
    order_meta["referral"] = referral_meta
    order.meta = order_meta


async def _ensure_checkout_customer_profile(
    db: AsyncSession,
    current_user: User,
    contact: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    contact_data = dict(contact or {})
    full_name = str(contact_data.get("name") or current_user.full_name or "").strip()
    phone_norm = normalize_phone(str(contact_data.get("phone") or current_user.phone or ""))

    if not full_name:
        raise HTTPException(status_code=400, detail="Customer name is required")
    if not phone_norm:
        raise HTTPException(status_code=400, detail="Customer phone is required")

    existing = (
        await db.execute(select(User).where(User.phone == phone_norm, User.id != current_user.id))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Phone already belongs to another customer")

    profile_changed = False
    if current_user.full_name != full_name:
        current_user.full_name = full_name
        profile_changed = True
    if current_user.phone != phone_norm:
        current_user.phone = phone_norm
        profile_changed = True
    if not current_user.is_customer:
        current_user.is_customer = True
        profile_changed = True
    if not current_user.role or str(current_user.role).strip().lower() in {"user"}:
        current_user.role = "customer"
        profile_changed = True

    if profile_changed:
        await db.commit()
        await db.refresh(current_user)

    if not current_user.customer_id_1c:
        try:
            payload = OneCUserRegistrationPayload(
                phone=phone_norm,
                full_name=full_name,
                email=current_user.email,
                inn=None,
                loyalty_program_key=None,
                source="app_checkout",
                customer_group_key=APP_CLIENT_CUSTOMER_GROUP_KEY,
            )
            await OneCUserSyncService(db).enqueue_registration(current_user, payload)
        except Exception as e:
            logger.warning("Не удалось запланировать создание покупателя в 1С из checkout: %s", e)

    contact_data["name"] = full_name
    contact_data["phone"] = phone_norm
    return contact_data


async def _save_preferred_delivery(
    db: AsyncSession,
    current_user: User,
    delivery: Optional[Dict[str, Any]],
) -> None:
    if not isinstance(delivery, dict) or not delivery:
        return
    prefs = dict(current_user.preferences or {})
    prefs["preferred_delivery"] = dict(delivery)
    current_user.preferences = prefs
    await db.commit()
    await db.refresh(current_user)


async def _get_or_create_cart(db: AsyncSession, user_id: UUID) -> Cart:
    cart = (await db.execute(select(Cart).where(Cart.user_id == user_id))).scalar_one_or_none()
    if cart:
        return cart
    cart = Cart(user_id=user_id)
    db.add(cart)
    await db.commit()
    await db.refresh(cart)
    return cart


@router.get("/cart")
async def get_cart(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cart = await _get_or_create_cart(db, current_user.id)
    items = (await db.execute(select(CartItem).where(CartItem.cart_id == cart.id))).scalars().all()
    product_ids = [x.product_id for x in items]
    products = {}
    if product_ids:
        rows = (await db.execute(select(Product).where(Product.id.in_(product_ids)))).scalars().all()
        products = {p.id: p for p in rows}

    resp_items = []
    subtotal = 0
    for item in items:
        product = products.get(item.product_id)
        unit_price = int(getattr(product, "price", 0) or 0) if product else 0
        line_total = unit_price * int(item.quantity or 0)
        subtotal += line_total
        resp_items.append(
            {
                "id": str(item.id),
                "product_id": str(item.product_id),
                "quantity": int(item.quantity),
                "unit_price": unit_price,
                "line_total": line_total,
                "product": {
                    "id": str(product.id),
                    "name": product.name,
                    "price": product.price,
                    "images": product.images or [],
                }
                if product
                else None,
            }
        )

    return {
        "cart_id": str(cart.id),
        "items": resp_items,
        "totals": {"subtotal": subtotal, "currency": "RUB"},
    }


@router.post("/cart/items")
async def add_cart_item(
    body: CartItemIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cart = await _get_or_create_cart(db, current_user.id)
    try:
        pid = UUID(body.product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid product_id")

    product = (await db.execute(select(Product).where(Product.id == pid))).scalar_one_or_none()
    if not product or not product.is_active:
        raise HTTPException(status_code=404, detail="Product not found")

    existing = (
        await db.execute(select(CartItem).where(CartItem.cart_id == cart.id, CartItem.product_id == pid))
    ).scalar_one_or_none()
    if existing:
        existing.quantity = int(existing.quantity) + int(body.quantity)
        await db.commit()
        return {"id": str(existing.id)}

    item = CartItem(cart_id=cart.id, product_id=pid, quantity=int(body.quantity))
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return {"id": str(item.id)}


@router.delete("/cart/items/{item_id}")
async def delete_cart_item(
    item_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cart = await _get_or_create_cart(db, current_user.id)
    try:
        iid = UUID(item_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid item_id")

    item = (
        await db.execute(select(CartItem).where(CartItem.id == iid, CartItem.cart_id == cart.id))
    ).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    await db.delete(item)
    await db.commit()
    return {"deleted": True}

@router.put("/cart/items/{item_id}")
async def update_cart_item_quantity(
    item_id: str,
    body: CartItemQtyIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cart = await _get_or_create_cart(db, current_user.id)
    try:
        iid = UUID(item_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid item_id")

    item = (
        await db.execute(select(CartItem).where(CartItem.id == iid, CartItem.cart_id == cart.id))
    ).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    qty = int(body.quantity or 0)
    if qty <= 0:
        await db.delete(item)
        await db.commit()
        return {"deleted": True}

    item.quantity = qty
    await db.commit()
    await db.refresh(item)
    return {"id": str(item.id), "quantity": int(item.quantity)}


@router.post("/checkout")
async def checkout(
    body: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payment_method = str(body.payment_method).strip().lower()
    svc = None

    cart = await _get_or_create_cart(db, current_user.id)
    cart_items = (await db.execute(select(CartItem).where(CartItem.cart_id == cart.id))).scalars().all()
    if not cart_items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    product_ids = [x.product_id for x in cart_items]
    products = {p.id: p for p in (await db.execute(select(Product).where(Product.id.in_(product_ids)))).scalars().all()}

    subtotal = 0
    order_items: List[OrderItem] = []
    glm_limit_lines: List[Dict[str, Any]] = []
    for ci in cart_items:
        product = products.get(ci.product_id)
        if not product or not product.is_active:
            raise HTTPException(status_code=400, detail="Cart contains inactive product")
        unit_price = int(product.price or 0)
        qty = int(ci.quantity or 0)
        line_total = unit_price * qty
        subtotal += line_total
        glm_limit_lines.append(
            {
                "product_id": str(product.id),
                "category": product.category,
                "tags": product.tags,
                "line_total": line_total,
            }
        )
        order_items.append(
            OrderItem(
                product_id=product.id,
                quantity=qty,
                unit_price=unit_price,
                line_total=line_total,
            )
        )

    delivery_amount = int(body.delivery_amount or 0)
    discount_amount = int(body.discount_amount or 0)
    gross_total = subtotal + delivery_amount
    if discount_amount > gross_total:
        raise HTTPException(status_code=400, detail="Invalid discount amount")

    requested_bonus_points = int(body.use_bonus_points or 0)
    available_bonus_points = int(current_user.loyalty_points or 0)
    if requested_bonus_points > available_bonus_points:
        raise HTTPException(status_code=400, detail="Not enough bonus points")

    payable_before_bonus = gross_total - discount_amount
    bonus_discount_amount = min(
        _bonus_points_to_kopeks(requested_bonus_points),
        payable_before_bonus,
    )
    bonus_points_to_spend = bonus_discount_amount // 100
    total_discount_amount = discount_amount + bonus_discount_amount
    payable_after_bonus = max(0, gross_total - total_discount_amount)

    requested_glm_amount = int(body.use_glm_amount or 0)
    glm_policy = GlameTokenService.calculate_checkout_glm_limit(glm_limit_lines)
    glm_discount_amount = 0
    glm_amount_to_spend = 0
    if requested_glm_amount > 0:
        token_account = (
            await db.execute(
                select(GlameTokenAccount).where(
                    GlameTokenAccount.user_id == current_user.id,
                    GlameTokenAccount.token_code == "GLM",
                )
            )
        ).scalar_one_or_none()
        available_glm = int(token_account.balance or 0) if token_account is not None else 0
        if requested_glm_amount > available_glm:
            raise HTTPException(status_code=400, detail="Not enough GLM")
        max_glm_by_policy = int(glm_policy.get("max_glm") or 0)
        payable_glm_cap = payable_after_bonus // 100
        glm_amount_to_spend = min(requested_glm_amount, available_glm, max_glm_by_policy, payable_glm_cap)
        if glm_amount_to_spend <= 0:
            raise HTTPException(status_code=400, detail="GLM cannot be applied to this order")
        glm_discount_amount = glm_amount_to_spend * 100
        total_discount_amount += glm_discount_amount
        payable_after_bonus = max(0, payable_after_bonus - glm_discount_amount)

    gift_certificate_payload = body.gift_certificate if isinstance(body.gift_certificate, dict) else {}
    gift_certificate_number = str(gift_certificate_payload.get("number") or "").strip()
    gift_certificate_pin = gift_certificate_payload.get("pin")
    requested_gift_amount = int(gift_certificate_payload.get("amount") or 0)
    gift_certificate_amount = 0
    if gift_certificate_number:
        cert_preview = await GiftCertificateService(db).get_valid_certificate(
            number=gift_certificate_number,
            pin=str(gift_certificate_pin) if gift_certificate_pin is not None else None,
            lock=False,
            require_pin=True,
        )
        gift_certificate_amount = min(
            requested_gift_amount if requested_gift_amount > 0 else payable_after_bonus,
            int(cert_preview.balance_amount or 0),
            payable_after_bonus,
        )
        if gift_certificate_amount <= 0:
            raise HTTPException(status_code=400, detail="Certificate cannot be applied")

    total = max(0, payable_after_bonus - gift_certificate_amount)
    if gross_total <= 0:
        raise HTTPException(status_code=400, detail="Invalid total amount")
    if payment_method == "card" and total > 0:
        svc = get_yookassa_service()
        if not svc:
            raise HTTPException(status_code=500, detail="YOOKASSA is not configured")

    contact_data = await _ensure_checkout_customer_profile(db, current_user, body.contact)
    await _save_preferred_delivery(db, current_user, body.delivery)

    order_meta = dict(body.meta or {})
    if bonus_points_to_spend > 0:
        order_meta["bonus_payment"] = {
            "points": bonus_points_to_spend,
            "amount": bonus_discount_amount,
            "rate": "1 point = 1 RUB",
        }
    if gift_certificate_amount > 0:
        order_meta["gift_certificate_payment"] = {
            "number": GiftCertificateService.normalize_number(gift_certificate_number),
            "amount": gift_certificate_amount,
            "status": "planned",
        }
    if glm_amount_to_spend > 0:
        order_meta["glm_payment"] = {
            "glm": glm_amount_to_spend,
            "amount": glm_discount_amount,
            "status": "planned",
            "rate": "1 GLM = 1 RUB internal value",
            "policy": glm_policy,
        }

    order = Order(
        user_id=current_user.id,
        status="pending",
        currency="RUB",
        subtotal_amount=subtotal,
        delivery_amount=delivery_amount,
        discount_amount=total_discount_amount,
        total_amount=total,
        delivery=body.delivery,
        contact=contact_data,
        meta=order_meta or None,
    )
    db.add(order)
    await db.flush()

    if gift_certificate_amount > 0:
        cert = await GiftCertificateService(db).reserve_for_order(
            number=gift_certificate_number,
            pin=str(gift_certificate_pin) if gift_certificate_pin is not None else None,
            amount=gift_certificate_amount,
            order_id=order.id,
        )
        gift_meta = dict(order_meta.get("gift_certificate_payment") or {})
        gift_meta.update(
            {
                "certificate_id": str(cert.id),
                "number": cert.number,
                "amount": gift_certificate_amount,
                "status": "reserved",
            }
        )
        order_meta["gift_certificate_payment"] = gift_meta
        order.meta = order_meta

    await db.flush()

    for oi in order_items:
        oi.order_id = order.id
        db.add(oi)
    await db.flush()

    await _attach_referral_to_order(
        db,
        order=order,
        current_user=current_user,
        order_meta=order_meta,
        commission_base=max(0, subtotal - total_discount_amount),
    )

    async def spend_order_bonuses() -> None:
        if bonus_points_to_spend <= 0:
            return
        await LoyaltyService(db).spend_points(
            user_id=current_user.id,
            points=bonus_points_to_spend,
            reason="order_payment",
            description=f"Оплата бонусами заказа {order.id}",
        )

    async def redeem_order_certificate() -> None:
        if gift_certificate_amount <= 0:
            return
        await GiftCertificateService(db).redeem_reserved_for_order(order.id)
        meta = dict(order.meta or {})
        gift_meta = dict(meta.get("gift_certificate_payment") or {})
        gift_meta["status"] = "redeemed"
        meta["gift_certificate_payment"] = gift_meta
        order.meta = meta

    async def redeem_order_glm() -> None:
        if glm_amount_to_spend <= 0:
            return
        tx = await GlameTokenService(db).redeem_checkout_internal_value(
            user_id=current_user.id,
            amount=glm_amount_to_spend,
            order_id=order.id,
            meta={
                "discount_amount": glm_discount_amount,
                "checkout_policy": glm_policy,
            },
        )
        meta = dict(order.meta or {})
        glm_meta = dict(meta.get("glm_payment") or {})
        glm_meta.update(
            {
                "status": "redeemed",
                "transaction_id": str(tx.id),
                "balance_after": int(tx.balance_after or 0),
            }
        )
        meta["glm_payment"] = glm_meta
        order.meta = meta

    if total == 0:
        order.status = "paid"
        payment = Payment(
            order_id=order.id,
            provider="internal_value" if glm_amount_to_spend > 0 else ("gift_certificate" if gift_certificate_amount > 0 else "bonus"),
            external_id=None,
            status="succeeded",
            currency="RUB",
            amount=0,
            idempotence_key=None,
            confirmation_url=None,
            raw={
                "payment_method": "internal_value" if glm_amount_to_spend > 0 else ("gift_certificate" if gift_certificate_amount > 0 else "bonus"),
                "bonus_points": bonus_points_to_spend,
                "bonus_amount": bonus_discount_amount,
                "glm_amount": glm_amount_to_spend,
                "glm_discount_amount": glm_discount_amount,
                "gift_certificate_amount": gift_certificate_amount,
                "gift_certificate_number": GiftCertificateService.normalize_number(gift_certificate_number)
                if gift_certificate_amount > 0
                else None,
            },
        )
        db.add(payment)
        await db.commit()
        await db.refresh(payment)
        await spend_order_bonuses()
        await redeem_order_glm()
        await redeem_order_certificate()

        await db.execute(delete(CartItem).where(CartItem.cart_id == cart.id))
        await db.commit()
        await _refresh_onec_orders_snapshot(db)

        return {
            "order_id": str(order.id),
            "payment_id": str(payment.id),
            "provider": payment.provider,
            "confirmation_url": None,
            "amount": total,
            "currency": "RUB",
            "bonus_points_spent": bonus_points_to_spend,
            "glm_amount_spent": glm_amount_to_spend,
            "glm_discount_amount": glm_discount_amount,
            "gift_certificate_amount": gift_certificate_amount,
        }

    if payment_method == "cod":
        payment = Payment(
            order_id=order.id,
            provider="cod",
            external_id=None,
            status="pending",
            currency="RUB",
            amount=total,
            idempotence_key=None,
            confirmation_url=None,
            raw={
                "payment_method": "cod",
                "bonus_points": bonus_points_to_spend,
                "bonus_amount": bonus_discount_amount,
                "glm_amount": glm_amount_to_spend,
                "glm_discount_amount": glm_discount_amount,
                "gift_certificate_amount": gift_certificate_amount,
                "gift_certificate_number": GiftCertificateService.normalize_number(gift_certificate_number)
                if gift_certificate_amount > 0
                else None,
            },
        )
        db.add(payment)
        await db.commit()
        await db.refresh(payment)
        await spend_order_bonuses()
        await redeem_order_glm()
        await redeem_order_certificate()

        await db.execute(delete(CartItem).where(CartItem.cart_id == cart.id))
        await db.commit()
        await _refresh_onec_orders_snapshot(db)

        return {
            "order_id": str(order.id),
            "payment_id": str(payment.id),
            "provider": "cod",
            "confirmation_url": None,
            "amount": total,
            "currency": "RUB",
            "bonus_points_spent": bonus_points_to_spend,
            "glm_amount_spent": glm_amount_to_spend,
            "glm_discount_amount": glm_discount_amount,
            "gift_certificate_amount": gift_certificate_amount,
        }

    return_url = str(body.return_url).strip()
    if not return_url:
        raise HTTPException(status_code=400, detail="return_url is required")
    if not svc:
        raise HTTPException(status_code=500, detail="YOOKASSA is not configured")

    description = f"Заказ {order.id} GLAME.JEWELRY"
    payment_data = await svc.create_payment(
        amount_rub=_rub_value(total),
        description=description,
        return_url=return_url,
        metadata={
            "order_id": str(order.id),
            "bonus_points": str(bonus_points_to_spend),
            "bonus_amount": str(bonus_discount_amount),
            "glm_amount": str(glm_amount_to_spend),
            "glm_discount_amount": str(glm_discount_amount),
            "gift_certificate_amount": str(gift_certificate_amount),
            "gift_certificate_number": GiftCertificateService.normalize_number(gift_certificate_number)
            if gift_certificate_amount > 0
            else "",
        },
    )

    confirmation = payment_data.get("confirmation") or {}
    confirmation_url = confirmation.get("confirmation_url")
    external_id = payment_data.get("id")
    status_value = payment_data.get("status") or "pending"
    idem_key = payment_data.get("_idempotence_key")

    payment = Payment(
        order_id=order.id,
        provider="yookassa",
        external_id=str(external_id) if external_id else None,
        status=str(status_value),
        currency="RUB",
        amount=total,
        idempotence_key=str(idem_key) if idem_key else None,
        confirmation_url=str(confirmation_url) if confirmation_url else None,
        raw=payment_data,
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)
    await spend_order_bonuses()
    await redeem_order_glm()

    await db.execute(delete(CartItem).where(CartItem.cart_id == cart.id))
    await db.commit()
    await _refresh_onec_orders_snapshot(db)

    return {
        "order_id": str(order.id),
        "payment_id": str(payment.id),
        "provider": "yookassa",
        "confirmation_url": confirmation_url,
        "amount": total,
        "currency": "RUB",
        "bonus_points_spent": bonus_points_to_spend,
        "glm_amount_spent": glm_amount_to_spend,
        "glm_discount_amount": glm_discount_amount,
        "gift_certificate_amount": gift_certificate_amount,
    }
