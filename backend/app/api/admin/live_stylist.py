from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID
import re
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.dependencies import require_any_role
from app.database.connection import get_db
from app.models.live_stylist_conversation import LiveStylistConversation
from app.models.live_stylist_conversation_event import LiveStylistConversationEvent
from app.models.loyalty_transaction import LoyaltyTransaction
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.product_stock import ProductStock
from app.models.purchase_history import PurchaseHistory
from app.models.saved_look import SavedLook
from app.models.stylist_chat_message import StylistChatMessage
from app.models.user import User
from app.models.look import Look
from app.services.admin_access import normalize_role
from app.services.live_stylist_platform import (
    ensure_live_stylist_schema,
    get_or_create_open_conversation,
    log_live_stylist_event,
    make_event_payload,
    normalize_conversation_priority,
    normalize_conversation_status,
    normalize_purchase_outcome,
    priority_label,
    purchase_outcome_label,
    status_label,
)
from app.services.live_stylist_service import get_live_stylist_status


router = APIRouter()
FIRST_RESPONSE_SLA_MINUTES = 5
STYLIST_TYPING_TTL_SECONDS = 8


class LiveStylistUserInfo(BaseModel):
    id: str
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    city: str | None = None
    role: str | None = None
    role_label: str | None = None


class LiveStylistMessageResponse(BaseModel):
    id: str
    conversation_id: str | None = None
    user_id: str
    sender_user_id: str | None = None
    role: str
    text: str | None = None
    attachments: list[dict] = Field(default_factory=list)
    payload: dict = Field(default_factory=dict)
    created_at: str | None = None
    sender: LiveStylistUserInfo | None = None


class LiveStylistConversationSummary(BaseModel):
    id: str
    source: str | None = None
    scenario: str | None = None
    status: str
    status_label: str
    priority: str
    priority_label: str
    unread_for_stylist_count: int
    unread_for_customer_count: int
    created_at: str | None = None
    updated_at: str | None = None
    last_message_at: str | None = None
    first_response_at: str | None = None
    closed_at: str | None = None
    result_purchase_status: str
    result_purchase_status_label: str
    result_order_id: str | None = None
    result_source: str | None = None
    recommended_product_ids: list[str] = Field(default_factory=list)
    internal_notes: str | None = None
    result_notes: str | None = None
    needs_attention: bool = False
    attention_reason: str | None = None
    waiting_minutes: int = 0
    first_response_due_at: str | None = None
    customer: LiveStylistUserInfo
    assigned_stylist: LiveStylistUserInfo | None = None
    last_message_preview: str | None = None


class LiveStylistOrderSummary(BaseModel):
    id: str
    status: str
    total_amount: int
    created_at: str | None = None
    product_ids: list[str] = Field(default_factory=list)


class LiveStylistCustomerPurchaseItem(BaseModel):
    id: str
    purchase_date: str | None = None
    product_id: str | None = None
    product_name: str | None = None
    category: str | None = None
    brand: str | None = None
    quantity: int = 0
    total_amount: int = 0


class LiveStylistCustomerFavoriteProduct(BaseModel):
    id: str
    name: str | None = None
    brand: str | None = None
    category: str | None = None
    article: str | None = None
    price: int | None = None
    image_url: str | None = None


class LiveStylistCustomerFavoriteLook(BaseModel):
    id: str
    look_id: str
    look_name: str | None = None
    save_type: str | None = None
    look_style: str | None = None
    look_mood: str | None = None
    look_image_url: str | None = None
    created_at: str | None = None


class LiveStylistCustomerLoyaltyTransaction(BaseModel):
    id: str
    transaction_type: str
    points: int
    balance_after: int
    reason: str | None = None
    description: str | None = None
    created_at: str | None = None


class LiveStylistCustomerContextResponse(BaseModel):
    customer_id: str
    is_registered: bool
    has_bonus_card: bool
    discount_card_number: str | None = None
    loyalty_points: int = 0
    customer_segment: str | None = None
    total_purchases: int = 0
    total_spent: int = 0
    average_check: int | None = None
    last_purchase_date: str | None = None
    preferred_store_name: str | None = None
    secondary_store_name: str | None = None
    favorite_categories: list[str] = Field(default_factory=list)
    favorite_brands: list[str] = Field(default_factory=list)
    favorite_products: list[LiveStylistCustomerFavoriteProduct] = Field(default_factory=list)
    favorite_looks: list[LiveStylistCustomerFavoriteLook] = Field(default_factory=list)
    recent_purchases: list[LiveStylistCustomerPurchaseItem] = Field(default_factory=list)
    loyalty_transactions: list[LiveStylistCustomerLoyaltyTransaction] = Field(default_factory=list)


class LiveStylistConversationEventResponse(BaseModel):
    id: str
    event_type: str
    event_label: str
    description: str
    created_at: str | None = None
    actor: LiveStylistUserInfo | None = None
    payload: dict = Field(default_factory=dict)


class LiveStylistAttachableProductResponse(BaseModel):
    id: str
    name: str | None = None
    brand: str | None = None
    category: str | None = None
    article: str | None = None
    external_code: str | None = None
    price: int | None = None
    image_url: str | None = None
    in_stock: bool = False


class LiveStylistConversationDetail(BaseModel):
    conversation: LiveStylistConversationSummary
    messages: list[LiveStylistMessageResponse]
    audit_events: list[LiveStylistConversationEventResponse] = Field(default_factory=list)
    recent_orders: list[LiveStylistOrderSummary]
    customer_context: LiveStylistCustomerContextResponse
    current_working_hours: dict


class LiveStylistConversationUpdateRequest(BaseModel):
    status: str | None = None
    priority: str | None = None
    assigned_stylist_user_id: str | None = None
    internal_notes: str | None = None
    result_purchase_status: str | None = None
    result_order_id: str | None = None
    result_notes: str | None = None
    recommended_product_ids: list[str] | None = None


class LiveStylistAssignRequest(BaseModel):
    stylist_user_id: str | None = None


class LiveStylistSendMessageRequest(BaseModel):
    text: str = Field(min_length=1)


class LiveStylistTypingStateRequest(BaseModel):
    is_typing: bool = False


class LiveStylistUnreadBadgeResponse(BaseModel):
    total_unread_messages: int
    requested_conversations: int
    high_priority_conversations: int
    mine_unread_messages: int
    open_conversations: int
    unassigned_conversations: int
    purchased_conversations: int
    attention_conversations: int
    overdue_first_response_conversations: int


def _safe_upload_name(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    return f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex}{suffix}"


def _message_preview(text: str | None, attachments: list[dict] | None) -> str:
    clean_text = (text or "").strip()
    if clean_text:
        return clean_text[:200]
    attachment_items = attachments or []
    photo_count = sum(1 for item in attachment_items if isinstance(item, dict) and item.get("type") == "image")
    product_count = sum(1 for item in attachment_items if isinstance(item, dict) and item.get("type") == "product")
    if photo_count and product_count:
        return f"Фото и товары: {photo_count} / {product_count}"
    if photo_count:
        return f"Фотосообщение ({photo_count})"
    if product_count:
        return f"Рекомендованы товары ({product_count})"
    return "Сообщение без текста"


def _set_stylist_typing_meta(
    conversation: LiveStylistConversation,
    *,
    current_user: User | None,
    is_typing: bool,
) -> None:
    meta = conversation.meta if isinstance(conversation.meta, dict) else {}
    if is_typing:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=STYLIST_TYPING_TTL_SECONDS)
        meta["stylist_typing"] = {
            "is_typing": True,
            "stylist_user_id": str(current_user.id) if current_user is not None else None,
            "stylist_name": (
                current_user.full_name
                or current_user.email
                or current_user.phone
                if current_user is not None
                else None
            ),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": expires_at.isoformat(),
        }
    else:
        meta.pop("stylist_typing", None)
    conversation.meta = meta


async def _serialize_attachable_product(db: AsyncSession, product: Product) -> LiveStylistAttachableProductResponse:
    stock = float(
        (
            await db.execute(
                select(func.sum(func.coalesce(ProductStock.available_quantity, 0)))
                .where(ProductStock.product_id == product.id)
            )
        ).scalar_one_or_none()
        or 0
    )
    image_url = (product.images or [None])[0] if isinstance(product.images, list) and product.images else None
    return LiveStylistAttachableProductResponse(
        id=str(product.id),
        name=product.name,
        brand=product.brand,
        category=product.category,
        article=product.article,
        external_code=product.external_code,
        price=product.price,
        image_url=image_url,
        in_stock=stock > 0,
    )


async def _find_products_for_message(db: AsyncSession, query: str, limit: int = 8) -> list[Product]:
    normalized = (query or "").strip()
    if len(normalized) < 2:
        return []
    tokens = list({t for t in re.findall(r"[a-zA-Zа-яА-Я0-9_\-]{2,}", normalized)})[:10]
    if not tokens:
        return []

    clauses = []
    for token in tokens:
        like = f"%{token}%"
        clauses.extend(
            [
                Product.article == token,
                Product.external_code == token,
                Product.name.ilike(like),
                Product.brand.ilike(like),
                Product.article.ilike(like),
                Product.external_code.ilike(like),
            ]
        )

    rows = (
        await db.execute(select(Product).where(Product.is_active == True, or_(*clauses)).limit(max(limit * 3, 20)))
    ).scalars().all()
    if not rows:
        return []

    normalized_tokens = {token.lower() for token in tokens}

    def _score(item: Product) -> tuple[int, int, int, str]:
        article = str(item.article or "").lower()
        external_code = str(item.external_code or "").lower()
        brand = str(item.brand or "").lower()
        name = str(item.name or "").lower()
        exact = int(article in normalized_tokens or external_code in normalized_tokens)
        starts = int(any(article.startswith(token) or external_code.startswith(token) for token in normalized_tokens))
        text_match = int(
            any(
                token in brand or token in name
                for token in normalized_tokens
            )
        )
        has_image = int(isinstance(item.images, list) and len(item.images) > 0)
        return (exact, starts, text_match, has_image, item.name or "")

    return sorted(rows, key=_score, reverse=True)[:limit]


def _get_first_response_due_at(conversation: LiveStylistConversation) -> datetime | None:
    if conversation.first_response_at is not None or conversation.created_at is None:
        return None
    return conversation.created_at + timedelta(minutes=FIRST_RESPONSE_SLA_MINUTES)


def _get_attention_state(conversation: LiveStylistConversation) -> tuple[bool, str | None, int, datetime | None]:
    now = datetime.now(timezone.utc)
    waiting_minutes = 0
    if conversation.created_at is not None:
        waiting_minutes = max(0, int((now - conversation.created_at).total_seconds() // 60))

    if conversation.status == "completed":
        return False, None, waiting_minutes, _get_first_response_due_at(conversation)

    due_at = _get_first_response_due_at(conversation)
    if due_at is not None and now >= due_at:
        return True, "overdue_first_response", waiting_minutes, due_at
    if conversation.status == "requested" and conversation.assigned_stylist_user_id is None:
        return True, "unassigned_request", waiting_minutes, due_at
    if (conversation.unread_for_stylist_count or 0) > 0 and conversation.status in {"requested", "in_progress"}:
        return True, "unread_customer_message", waiting_minutes, due_at
    return False, None, waiting_minutes, due_at


def _user_info(user: User | None) -> LiveStylistUserInfo | None:
    if user is None:
        return None
    role = normalize_role(getattr(user, "role", None))
    role_label = {
        "admin": "Админ",
        "seller": "Продавец",
        "manager": "Управляющий",
        "marketer": "Маркетолог",
    }.get(role or "")
    return LiveStylistUserInfo(
        id=str(user.id),
        full_name=getattr(user, "full_name", None),
        email=getattr(user, "email", None),
        phone=getattr(user, "phone", None),
        city=getattr(user, "city", None),
        role=role,
        role_label=role_label,
    )


def _serialize_message(message: StylistChatMessage, sender: User | None) -> LiveStylistMessageResponse:
    return LiveStylistMessageResponse(
        id=str(message.id),
        conversation_id=str(message.conversation_id) if message.conversation_id else None,
        user_id=str(message.user_id),
        sender_user_id=str(message.sender_user_id) if message.sender_user_id else None,
        role=message.role,
        text=message.text,
        attachments=message.attachments or [],
        payload=message.payload or {},
        created_at=message.created_at.isoformat() if message.created_at else None,
        sender=_user_info(sender),
    )


def _event_label(event_type: str) -> str:
    return {
        "conversation_created": "Обращение создано",
        "assigned": "Назначен стилист",
        "status_changed": "Изменен статус",
        "priority_changed": "Изменен приоритет",
        "notes_updated": "Обновлены заметки",
        "recommendations_updated": "Обновлены рекомендации",
        "result_updated": "Обновлен итог",
        "message_sent": "Отправлено сообщение",
        "chat_cleared": "Очищен чат",
        "auto_purchase_detected": "Автоопределена покупка",
    }.get(event_type, "Изменение обращения")


def _event_description(event: LiveStylistConversationEvent, actor: User | None) -> str:
    payload = event.payload if isinstance(event.payload, dict) else {}
    actor_name = getattr(actor, "full_name", None) or getattr(actor, "email", None) or "Система"
    if event.event_type == "conversation_created":
        source = payload.get("source") or "unknown source"
        return f"{actor_name} создал(а) обращение из источника {source}."
    if event.event_type == "assigned":
        assigned_name = payload.get("assigned_stylist_name") or "Не назначен"
        return f"{actor_name} назначил(а) стилиста: {assigned_name}."
    if event.event_type == "status_changed":
        return f"{actor_name} сменил(а) статус: {payload.get('from_label') or '—'} -> {payload.get('to_label') or '—'}."
    if event.event_type == "priority_changed":
        return f"{actor_name} сменил(а) приоритет: {payload.get('from_label') or '—'} -> {payload.get('to_label') or '—'}."
    if event.event_type == "notes_updated":
        return f"{actor_name} обновил(а) внутренние заметки."
    if event.event_type == "recommendations_updated":
        count = len(payload.get("recommended_product_ids") or [])
        return f"{actor_name} обновил(а) рекомендованные товары. Всего: {count}."
    if event.event_type == "result_updated":
        result_label = payload.get("result_label") or "Не отмечено"
        order_id = payload.get("result_order_id")
        return f"{actor_name} обновил(а) итог обращения: {result_label}{f' · заказ {order_id}' if order_id else ''}."
    if event.event_type == "message_sent":
        return f"{actor_name} отправил(а) сообщение покупателю."
    if event.event_type == "chat_cleared":
        deleted = payload.get("deleted_message_count") or 0
        return f"{actor_name} очистил(а) чат обращения. Удалено сообщений: {deleted}."
    if event.event_type == "auto_purchase_detected":
        result_label = payload.get("result_label") or "Покупка определена"
        order_id = payload.get("result_order_id")
        return f"Система автоматически отметила итог: {result_label}{f' · заказ {order_id}' if order_id else ''}."
    return f"{actor_name} изменил(а) обращение."


def _serialize_event(event: LiveStylistConversationEvent, actor: User | None) -> LiveStylistConversationEventResponse:
    return LiveStylistConversationEventResponse(
        id=str(event.id),
        event_type=event.event_type,
        event_label=_event_label(event.event_type),
        description=_event_description(event, actor),
        created_at=event.created_at.isoformat() if event.created_at else None,
        actor=_user_info(actor),
        payload=event.payload or {},
    )


def _assigned_stylist_name(stylist: User | None) -> str:
    if stylist is None:
        return "Не назначен"
    return getattr(stylist, "full_name", None) or getattr(stylist, "email", None) or str(stylist.id)


async def _get_staff_user_or_400(db: AsyncSession, user_id: UUID) -> User:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Стилист не найден")
    role = normalize_role(getattr(user, "role", None))
    if bool(getattr(user, "is_customer", False)) or role not in {"admin", "seller", "manager"}:
        raise HTTPException(status_code=400, detail="Пользователь не может быть назначен стилистом")
    return user


async def _fetch_last_message_previews(
    db: AsyncSession,
    conversation_ids: list[UUID],
) -> dict[UUID, str]:
    previews: dict[UUID, str] = {}
    if not conversation_ids:
        return previews
    for conversation_id in conversation_ids:
        result = await db.execute(
            select(StylistChatMessage)
            .where(StylistChatMessage.conversation_id == conversation_id)
            .order_by(StylistChatMessage.created_at.desc())
            .limit(1)
        )
        message = result.scalar_one_or_none()
        if message:
            previews[conversation_id] = _message_preview(message.text, message.attachments)
    return previews


async def _serialize_conversation_summary(
    db: AsyncSession,
    conversation: LiveStylistConversation,
    last_message_preview: str | None = None,
) -> LiveStylistConversationSummary:
    customer = (await db.execute(select(User).where(User.id == conversation.customer_user_id))).scalar_one()
    assigned = None
    if conversation.assigned_stylist_user_id:
        assigned = (
            await db.execute(select(User).where(User.id == conversation.assigned_stylist_user_id))
        ).scalar_one_or_none()
    needs_attention, attention_reason, waiting_minutes, due_at = _get_attention_state(conversation)
    return LiveStylistConversationSummary(
        id=str(conversation.id),
        source=conversation.source,
        scenario=conversation.scenario,
        status=conversation.status,
        status_label=status_label(conversation.status),
        priority=conversation.priority,
        priority_label=priority_label(conversation.priority),
        unread_for_stylist_count=conversation.unread_for_stylist_count or 0,
        unread_for_customer_count=conversation.unread_for_customer_count or 0,
        created_at=conversation.created_at.isoformat() if conversation.created_at else None,
        updated_at=conversation.updated_at.isoformat() if conversation.updated_at else None,
        last_message_at=conversation.last_message_at.isoformat() if conversation.last_message_at else None,
        first_response_at=conversation.first_response_at.isoformat() if conversation.first_response_at else None,
        closed_at=conversation.closed_at.isoformat() if conversation.closed_at else None,
        result_purchase_status=conversation.result_purchase_status,
        result_purchase_status_label=purchase_outcome_label(conversation.result_purchase_status),
        result_order_id=str(conversation.result_order_id) if conversation.result_order_id else None,
        result_source=((conversation.meta or {}).get("result_source") if isinstance(conversation.meta, dict) else None),
        recommended_product_ids=[str(item) for item in (conversation.recommended_product_ids or [])],
        internal_notes=conversation.internal_notes,
        result_notes=conversation.result_notes,
        needs_attention=needs_attention,
        attention_reason=attention_reason,
        waiting_minutes=waiting_minutes,
        first_response_due_at=due_at.isoformat() if due_at else None,
        customer=_user_info(customer),
        assigned_stylist=_user_info(assigned),
        last_message_preview=last_message_preview,
    )


async def _fetch_messages(
    db: AsyncSession,
    conversation_id: UUID,
) -> list[LiveStylistMessageResponse]:
    rows = (
        await db.execute(
            select(StylistChatMessage)
            .where(StylistChatMessage.conversation_id == conversation_id)
            .order_by(StylistChatMessage.created_at.asc(), StylistChatMessage.id.asc())
        )
    ).scalars().all()
    sender_ids = {row.sender_user_id for row in rows if row.sender_user_id}
    senders: dict[UUID, User] = {}
    if sender_ids:
        users = (await db.execute(select(User).where(User.id.in_(list(sender_ids))))).scalars().all()
        senders = {user.id: user for user in users}
    return [_serialize_message(row, senders.get(row.sender_user_id)) for row in rows]


async def _fetch_audit_events(
    db: AsyncSession,
    conversation_id: UUID,
) -> list[LiveStylistConversationEventResponse]:
    rows = (
        await db.execute(
            select(LiveStylistConversationEvent)
            .where(LiveStylistConversationEvent.conversation_id == conversation_id)
            .order_by(LiveStylistConversationEvent.created_at.desc(), LiveStylistConversationEvent.id.desc())
        )
    ).scalars().all()
    actor_ids = {row.actor_user_id for row in rows if row.actor_user_id}
    actors: dict[UUID, User] = {}
    if actor_ids:
        users = (await db.execute(select(User).where(User.id.in_(list(actor_ids))))).scalars().all()
        actors = {user.id: user for user in users}
    return [_serialize_event(row, actors.get(row.actor_user_id)) for row in rows]


async def _fetch_recent_orders(db: AsyncSession, customer_user_id: UUID) -> list[LiveStylistOrderSummary]:
    orders = (
        await db.execute(
            select(Order)
            .where(Order.user_id == customer_user_id)
            .order_by(Order.created_at.desc())
            .limit(10)
        )
    ).scalars().all()
    if not orders:
        return []
    order_ids = [order.id for order in orders]
    order_items = (
        await db.execute(select(OrderItem).where(OrderItem.order_id.in_(order_ids)))
    ).scalars().all()
    items_by_order: dict[UUID, list[str]] = {}
    for item in order_items:
        items_by_order.setdefault(item.order_id, []).append(str(item.product_id))
    return [
        LiveStylistOrderSummary(
            id=str(order.id),
            status=order.status,
            total_amount=order.total_amount,
            created_at=order.created_at.isoformat() if order.created_at else None,
            product_ids=items_by_order.get(order.id, []),
        )
        for order in orders
    ]


async def _fetch_customer_context(
    db: AsyncSession,
    customer: User,
    conversation: LiveStylistConversation | None = None,
) -> LiveStylistCustomerContextResponse:
    purchase_preferences = customer.purchase_preferences if isinstance(customer.purchase_preferences, dict) else {}
    favorite_product_ids_raw = purchase_preferences.get("favorite_products") or []
    if conversation is not None and isinstance(conversation.meta, dict):
        latest_request = conversation.meta.get("latest_request")
        if isinstance(latest_request, dict):
            favorite_product_ids_raw = [
                *favorite_product_ids_raw,
                *(latest_request.get("favorite_product_ids") or []),
            ]
    favorite_product_ids: list[UUID] = []
    seen_favorite_product_ids: set[UUID] = set()
    for raw in favorite_product_ids_raw:
        try:
            parsed = UUID(str(raw))
        except (TypeError, ValueError):
            continue
        if parsed in seen_favorite_product_ids:
            continue
        seen_favorite_product_ids.add(parsed)
        favorite_product_ids.append(parsed)

    favorite_products_map: dict[UUID, Product] = {}
    if favorite_product_ids:
        products = (
            await db.execute(select(Product).where(Product.id.in_(favorite_product_ids)))
        ).scalars().all()
        favorite_products_map = {product.id: product for product in products}

    recent_purchases_rows = (
        await db.execute(
            select(PurchaseHistory)
            .where(PurchaseHistory.user_id == customer.id)
            .order_by(PurchaseHistory.purchase_date.desc())
            .limit(8)
        )
    ).scalars().all()

    loyalty_rows = (
        await db.execute(
            select(LoyaltyTransaction)
            .where(LoyaltyTransaction.user_id == customer.id)
            .order_by(LoyaltyTransaction.created_at.desc())
            .limit(5)
        )
    ).scalars().all()

    saved_look_rows = (
        await db.execute(
            select(SavedLook, Look)
            .join(Look, SavedLook.look_id == Look.id)
            .where(
                SavedLook.user_id == customer.id,
                SavedLook.save_type == "favorite",
            )
            .order_by(SavedLook.created_at.desc())
            .limit(6)
        )
    ).all()

    return LiveStylistCustomerContextResponse(
        customer_id=str(customer.id),
        is_registered=bool(customer.is_customer or customer.email or customer.phone or customer.discount_card_number),
        has_bonus_card=bool((customer.discount_card_number or "").strip()),
        discount_card_number=customer.discount_card_number,
        loyalty_points=int(customer.loyalty_points or 0),
        customer_segment=customer.customer_segment,
        total_purchases=int(customer.total_purchases or 0),
        total_spent=int(customer.total_spent or 0),
        average_check=int(customer.average_check) if customer.average_check is not None else None,
        last_purchase_date=customer.last_purchase_date.isoformat() if customer.last_purchase_date else None,
        preferred_store_name=customer.preferred_store_name,
        secondary_store_name=customer.secondary_store_name,
        favorite_categories=[str(item) for item in (purchase_preferences.get("favorite_categories") or []) if str(item).strip()],
        favorite_brands=[str(item) for item in (purchase_preferences.get("favorite_brands") or []) if str(item).strip()],
        favorite_products=[
            LiveStylistCustomerFavoriteProduct(
                id=str(product.id),
                name=product.name,
                brand=product.brand,
                category=product.category,
                article=product.article,
                price=product.price,
                image_url=((product.images or [None])[0] if isinstance(product.images, list) and product.images else None),
            )
            for product_id in favorite_product_ids
            for product in [favorite_products_map.get(product_id)]
            if product is not None
        ],
        favorite_looks=[
            LiveStylistCustomerFavoriteLook(
                id=str(saved_look.id),
                look_id=str(saved_look.look_id),
                look_name=look.name,
                save_type=saved_look.save_type,
                look_style=look.style,
                look_mood=look.mood,
                look_image_url=look.image_url or ((look.image_urls or [None])[0] if isinstance(look.image_urls, list) and look.image_urls else None),
                created_at=saved_look.created_at.isoformat() if saved_look.created_at else None,
            )
            for saved_look, look in saved_look_rows
        ],
        recent_purchases=[
            LiveStylistCustomerPurchaseItem(
                id=str(item.id),
                purchase_date=item.purchase_date.isoformat() if item.purchase_date else None,
                product_id=str(item.product_id) if item.product_id else None,
                product_name=item.product_name,
                category=item.category,
                brand=item.brand,
                quantity=int(item.quantity or 0),
                total_amount=int(item.total_amount or 0),
            )
            for item in recent_purchases_rows
        ],
        loyalty_transactions=[
            LiveStylistCustomerLoyaltyTransaction(
                id=str(item.id),
                transaction_type=item.transaction_type,
                points=int(item.points or 0),
                balance_after=int(item.balance_after or 0),
                reason=item.reason,
                description=item.description,
                created_at=item.created_at.isoformat() if item.created_at else None,
            )
            for item in loyalty_rows
        ],
    )


async def _build_conversation_detail(
    db: AsyncSession,
    conversation: LiveStylistConversation,
    *,
    last_message_preview: str | None = None,
) -> LiveStylistConversationDetail:
    customer = (await db.execute(select(User).where(User.id == conversation.customer_user_id))).scalar_one()
    messages = await _fetch_messages(db, conversation.id)
    audit_events = await _fetch_audit_events(db, conversation.id)
    orders = await _fetch_recent_orders(db, conversation.customer_user_id)
    customer_context = await _fetch_customer_context(db, customer, conversation)
    return LiveStylistConversationDetail(
        conversation=await _serialize_conversation_summary(
            db,
            conversation,
            last_message_preview=last_message_preview,
        ),
        messages=messages,
        audit_events=audit_events,
        recent_orders=orders,
        customer_context=customer_context,
        current_working_hours=get_live_stylist_status(),
    )


async def _fetch_orders_for_customers(
    db: AsyncSession,
    customer_ids: list[UUID],
) -> tuple[dict[UUID, list[Order]], dict[UUID, list[str]]]:
    if not customer_ids:
        return {}, {}
    orders = (
        await db.execute(
            select(Order)
            .where(Order.user_id.in_(customer_ids))
            .order_by(Order.created_at.desc())
        )
    ).scalars().all()
    orders_by_customer: dict[UUID, list[Order]] = {}
    for order in orders:
        orders_by_customer.setdefault(order.user_id, []).append(order)
    order_ids = [order.id for order in orders]
    if not order_ids:
        return orders_by_customer, {}
    order_items = (
        await db.execute(select(OrderItem).where(OrderItem.order_id.in_(order_ids)))
    ).scalars().all()
    items_by_order: dict[UUID, list[str]] = {}
    for item in order_items:
        items_by_order.setdefault(item.order_id, []).append(str(item.product_id))
    return orders_by_customer, items_by_order


def _sync_auto_purchase_result(
    conversation: LiveStylistConversation,
    customer_orders: list[Order],
    items_by_order: dict[UUID, list[str]],
) -> dict | None:
    if normalize_purchase_outcome(conversation.result_purchase_status) != "unknown":
        return None
    if conversation.result_order_id is not None:
        return None

    created_at = conversation.created_at
    if created_at is None:
        return None

    recommended = {str(item) for item in (conversation.recommended_product_ids or []) if str(item).strip()}
    valid_orders = [
        order
        for order in customer_orders
        if order.created_at and order.created_at >= created_at and order.status not in {"cancelled", "canceled", "failed"}
    ]
    if not valid_orders:
        return None

    matched_order: Order | None = None
    detected_status = "purchased_other"
    if recommended:
        for order in valid_orders:
            product_ids = set(items_by_order.get(order.id, []))
            if product_ids.intersection(recommended):
                matched_order = order
                detected_status = "purchased_recommended"
                break
    if matched_order is None:
        matched_order = valid_orders[0]

    meta = conversation.meta if isinstance(conversation.meta, dict) else {}
    meta["result_source"] = "auto"
    meta["result_auto_detected_at"] = datetime.now(timezone.utc).isoformat()
    conversation.meta = meta
    conversation.result_purchase_status = detected_status
    conversation.result_order_id = matched_order.id
    conversation.updated_at = datetime.now(timezone.utc)
    return make_event_payload(
        result_purchase_status=detected_status,
        result_label=purchase_outcome_label(detected_status),
        result_order_id=matched_order.id,
    )


async def _apply_auto_purchase_results(
    db: AsyncSession,
    conversations: list[LiveStylistConversation],
) -> None:
    customer_ids = list({conversation.customer_user_id for conversation in conversations if conversation.customer_user_id})
    orders_by_customer, items_by_order = await _fetch_orders_for_customers(db, customer_ids)
    changed = False
    for conversation in conversations:
        customer_orders = orders_by_customer.get(conversation.customer_user_id, [])
        audit_payload = _sync_auto_purchase_result(conversation, customer_orders, items_by_order)
        if audit_payload:
            await log_live_stylist_event(
                db=db,
                conversation_id=conversation.id,
                event_type="auto_purchase_detected",
                payload=audit_payload,
            )
            changed = True
    if changed:
        await db.commit()
        for conversation in conversations:
            await db.refresh(conversation)


@router.get("/stylists", response_model=list[LiveStylistUserInfo])
async def list_stylists(
    _current_user: User = Depends(require_any_role(["admin", "seller", "manager"])),
    db: AsyncSession = Depends(get_db),
):
    await ensure_live_stylist_schema(db)
    users = (
        await db.execute(
            select(User)
            .where(
                User.is_customer == False,
                User.role.in_(["admin", "seller", "manager"]),
            )
            .order_by(User.full_name.asc().nullslast(), User.email.asc().nullslast())
        )
    ).scalars().all()
    return [_user_info(user) for user in users if _user_info(user) is not None]


@router.get("/products/search", response_model=list[LiveStylistAttachableProductResponse])
async def search_products_for_stylist_message(
    query: str = Query(..., min_length=2),
    limit: int = Query(8, ge=1, le=20),
    _current_user: User = Depends(require_any_role(["admin", "seller", "manager"])),
    db: AsyncSession = Depends(get_db),
):
    products = await _find_products_for_message(db, query, limit=limit)
    return [await _serialize_attachable_product(db, product) for product in products]


@router.get("/inbox-badge", response_model=LiveStylistUnreadBadgeResponse)
async def get_inbox_badge(
    current_user: User = Depends(require_any_role(["admin", "seller", "manager"])),
    db: AsyncSession = Depends(get_db),
):
    await ensure_live_stylist_schema(db)
    total_unread_messages = (
        await db.execute(select(func.coalesce(func.sum(LiveStylistConversation.unread_for_stylist_count), 0)))
    ).scalar_one()
    requested_conversations = (
        await db.execute(
            select(func.count())
            .select_from(LiveStylistConversation)
            .where(LiveStylistConversation.status == "requested")
        )
    ).scalar_one()
    high_priority_conversations = (
        await db.execute(
            select(func.count())
            .select_from(LiveStylistConversation)
            .where(LiveStylistConversation.priority == "high")
        )
    ).scalar_one()
    mine_unread_messages = (
        await db.execute(
            select(func.coalesce(func.sum(LiveStylistConversation.unread_for_stylist_count), 0)).where(
                LiveStylistConversation.assigned_stylist_user_id == current_user.id
            )
        )
    ).scalar_one()
    open_conversations = (
        await db.execute(
            select(func.count())
            .select_from(LiveStylistConversation)
            .where(LiveStylistConversation.status != "completed")
        )
    ).scalar_one()
    unassigned_conversations = (
        await db.execute(
            select(func.count())
            .select_from(LiveStylistConversation)
            .where(LiveStylistConversation.assigned_stylist_user_id.is_(None))
        )
    ).scalar_one()
    purchased_conversations = (
        await db.execute(
            select(func.count())
            .select_from(LiveStylistConversation)
            .where(LiveStylistConversation.result_purchase_status.in_(["purchased_recommended", "purchased_other"]))
        )
    ).scalar_one()
    all_conversations = (await db.execute(select(LiveStylistConversation))).scalars().all()
    attention_conversations = 0
    overdue_first_response_conversations = 0
    for conversation in all_conversations:
        needs_attention, reason, _waiting_minutes, _due_at = _get_attention_state(conversation)
        if needs_attention:
            attention_conversations += 1
        if reason == "overdue_first_response":
            overdue_first_response_conversations += 1
    return LiveStylistUnreadBadgeResponse(
        total_unread_messages=int(total_unread_messages or 0),
        requested_conversations=int(requested_conversations or 0),
        high_priority_conversations=int(high_priority_conversations or 0),
        mine_unread_messages=int(mine_unread_messages or 0),
        open_conversations=int(open_conversations or 0),
        unassigned_conversations=int(unassigned_conversations or 0),
        purchased_conversations=int(purchased_conversations or 0),
        attention_conversations=attention_conversations,
        overdue_first_response_conversations=overdue_first_response_conversations,
    )


@router.get("/conversations", response_model=list[LiveStylistConversationSummary])
async def list_conversations(
    status: str | None = Query(None),
    purchase_status: str | None = Query(None),
    search: str | None = Query(None),
    mine_only: bool = Query(False),
    unassigned_only: bool = Query(False),
    attention_only: bool = Query(False),
    limit: int = Query(100, ge=1, le=300),
    _current_user: User = Depends(require_any_role(["admin", "seller", "manager"])),
    db: AsyncSession = Depends(get_db),
):
    await ensure_live_stylist_schema(db)
    customer_alias = aliased(User)
    stmt = select(LiveStylistConversation).join(
        customer_alias, customer_alias.id == LiveStylistConversation.customer_user_id
    )
    if status:
        stmt = stmt.where(LiveStylistConversation.status == normalize_conversation_status(status))
    if purchase_status:
        stmt = stmt.where(
            LiveStylistConversation.result_purchase_status == normalize_purchase_outcome(purchase_status)
        )
    search_value = (search or "").strip()
    if search_value:
        like = f"%{search_value}%"
        stmt = stmt.where(
            or_(
                customer_alias.full_name.ilike(like),
                customer_alias.phone.ilike(like),
                customer_alias.email.ilike(like),
                LiveStylistConversation.source.ilike(like),
            )
        )
    if mine_only:
        stmt = stmt.where(LiveStylistConversation.assigned_stylist_user_id == _current_user.id)
    if unassigned_only:
        stmt = stmt.where(LiveStylistConversation.assigned_stylist_user_id.is_(None))
    stmt = stmt.order_by(
        LiveStylistConversation.unread_for_stylist_count.desc(),
        LiveStylistConversation.last_message_at.desc().nullslast(),
        LiveStylistConversation.created_at.desc(),
    ).limit(limit)
    conversations = (await db.execute(stmt)).scalars().all()
    await _apply_auto_purchase_results(db, conversations)
    if attention_only:
        conversations = [item for item in conversations if _get_attention_state(item)[0]]
    previews = await _fetch_last_message_previews(db, [item.id for item in conversations])
    return [
        await _serialize_conversation_summary(db, item, last_message_preview=previews.get(item.id))
        for item in conversations
    ]


@router.get("/conversations/{conversation_id}", response_model=LiveStylistConversationDetail)
async def get_conversation_detail(
    conversation_id: UUID,
    _current_user: User = Depends(require_any_role(["admin", "seller", "manager"])),
    db: AsyncSession = Depends(get_db),
):
    await ensure_live_stylist_schema(db)
    conversation = (
        await db.execute(select(LiveStylistConversation).where(LiveStylistConversation.id == conversation_id))
    ).scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Обращение не найдено")
    conversation.unread_for_stylist_count = 0
    conversation.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(conversation)
    await _apply_auto_purchase_results(db, [conversation])
    messages = await _fetch_messages(db, conversation.id)
    preview = _message_preview(messages[-1].text if messages else None, messages[-1].attachments if messages else None)
    return await _build_conversation_detail(db, conversation, last_message_preview=preview)


@router.post("/conversations/{conversation_id}/assign", response_model=LiveStylistConversationSummary)
async def assign_conversation(
    conversation_id: UUID,
    payload: LiveStylistAssignRequest,
    current_user: User = Depends(require_any_role(["admin", "seller", "manager"])),
    db: AsyncSession = Depends(get_db),
):
    await ensure_live_stylist_schema(db)
    conversation = (
        await db.execute(select(LiveStylistConversation).where(LiveStylistConversation.id == conversation_id))
    ).scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Обращение не найдено")
    target_user_id = payload.stylist_user_id or str(current_user.id)
    try:
        stylist_uuid = UUID(target_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Некорректный ID стилиста") from exc
    assigned_user = await _get_staff_user_or_400(db, stylist_uuid)
    previous_assigned_stylist = conversation.assigned_stylist_user_id
    conversation.assigned_stylist_user_id = stylist_uuid
    conversation.assigned_at = conversation.assigned_at or datetime.now(timezone.utc)
    if conversation.status == "requested":
        conversation.status = "in_progress"
    conversation.updated_at = datetime.now(timezone.utc)
    await log_live_stylist_event(
        db=db,
        conversation_id=conversation.id,
        actor_user_id=current_user.id,
        event_type="assigned",
        payload=make_event_payload(
            previous_assigned_stylist_user_id=previous_assigned_stylist,
            assigned_stylist_user_id=assigned_user.id,
            assigned_stylist_name=_assigned_stylist_name(assigned_user),
        ),
    )
    await db.commit()
    await db.refresh(conversation)
    last_previews = await _fetch_last_message_previews(db, [conversation.id])
    return await _serialize_conversation_summary(db, conversation, last_previews.get(conversation.id))


@router.patch("/conversations/{conversation_id}", response_model=LiveStylistConversationSummary)
async def update_conversation(
    conversation_id: UUID,
    payload: LiveStylistConversationUpdateRequest,
    current_user: User = Depends(require_any_role(["admin", "seller", "manager"])),
    db: AsyncSession = Depends(get_db),
):
    await ensure_live_stylist_schema(db)
    conversation = (
        await db.execute(select(LiveStylistConversation).where(LiveStylistConversation.id == conversation_id))
    ).scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Обращение не найдено")

    if payload.status is not None:
        previous_status = conversation.status
        conversation.status = normalize_conversation_status(payload.status)
        conversation.closed_at = datetime.now(timezone.utc) if conversation.status == "completed" else None
        if conversation.status != previous_status:
            await log_live_stylist_event(
                db=db,
                conversation_id=conversation.id,
                actor_user_id=current_user.id,
                event_type="status_changed",
                payload=make_event_payload(
                    from_status=previous_status,
                    from_label=status_label(previous_status),
                    to_status=conversation.status,
                    to_label=status_label(conversation.status),
                ),
            )
    if payload.priority is not None:
        previous_priority = conversation.priority
        conversation.priority = normalize_conversation_priority(payload.priority)
        if conversation.priority != previous_priority:
            await log_live_stylist_event(
                db=db,
                conversation_id=conversation.id,
                actor_user_id=current_user.id,
                event_type="priority_changed",
                payload=make_event_payload(
                    from_priority=previous_priority,
                    from_label=priority_label(previous_priority),
                    to_priority=conversation.priority,
                    to_label=priority_label(conversation.priority),
                ),
            )
    if payload.assigned_stylist_user_id is not None:
        previous_assigned_stylist = conversation.assigned_stylist_user_id
        assigned_user: User | None = None
        if payload.assigned_stylist_user_id == "":
            conversation.assigned_stylist_user_id = None
        else:
            try:
                stylist_uuid = UUID(payload.assigned_stylist_user_id)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Некорректный ID стилиста") from exc
            assigned_user = await _get_staff_user_or_400(db, stylist_uuid)
            conversation.assigned_stylist_user_id = stylist_uuid
            conversation.assigned_at = conversation.assigned_at or datetime.now(timezone.utc)
        if conversation.assigned_stylist_user_id != previous_assigned_stylist:
            await log_live_stylist_event(
                db=db,
                conversation_id=conversation.id,
                actor_user_id=current_user.id,
                event_type="assigned",
                payload=make_event_payload(
                    previous_assigned_stylist_user_id=previous_assigned_stylist,
                    assigned_stylist_user_id=conversation.assigned_stylist_user_id,
                    assigned_stylist_name=_assigned_stylist_name(assigned_user),
                ),
            )
    if payload.internal_notes is not None:
        previous_notes = (conversation.internal_notes or "").strip()
        conversation.internal_notes = payload.internal_notes.strip() or None
        if (conversation.internal_notes or "").strip() != previous_notes:
            await log_live_stylist_event(
                db=db,
                conversation_id=conversation.id,
                actor_user_id=current_user.id,
                event_type="notes_updated",
            )
    if payload.result_purchase_status is not None:
        conversation.result_purchase_status = normalize_purchase_outcome(payload.result_purchase_status)
        meta = conversation.meta if isinstance(conversation.meta, dict) else {}
        meta["result_source"] = "manual"
        meta["result_manual_updated_at"] = datetime.now(timezone.utc).isoformat()
        conversation.meta = meta
    if payload.result_order_id is not None:
        if payload.result_order_id.strip():
            try:
                conversation.result_order_id = UUID(payload.result_order_id.strip())
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Некорректный ID заказа") from exc
        else:
            conversation.result_order_id = None
    if payload.result_notes is not None:
        conversation.result_notes = payload.result_notes.strip() or None
    if payload.recommended_product_ids is not None:
        previous_recommended_ids = [str(item) for item in (conversation.recommended_product_ids or [])]
        conversation.recommended_product_ids = [str(item).strip() for item in payload.recommended_product_ids if str(item).strip()]
        if conversation.recommended_product_ids != previous_recommended_ids:
            await log_live_stylist_event(
                db=db,
                conversation_id=conversation.id,
                actor_user_id=current_user.id,
                event_type="recommendations_updated",
                payload=make_event_payload(recommended_product_ids=conversation.recommended_product_ids),
            )

    if payload.result_purchase_status is not None or payload.result_order_id is not None or payload.result_notes is not None:
        await log_live_stylist_event(
            db=db,
            conversation_id=conversation.id,
            actor_user_id=current_user.id,
            event_type="result_updated",
            payload=make_event_payload(
                result_purchase_status=conversation.result_purchase_status,
                result_label=purchase_outcome_label(conversation.result_purchase_status),
                result_order_id=conversation.result_order_id,
                has_result_notes=bool((conversation.result_notes or "").strip()),
                result_source=(conversation.meta or {}).get("result_source") if isinstance(conversation.meta, dict) else None,
            ),
        )

    conversation.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(conversation)
    last_previews = await _fetch_last_message_previews(db, [conversation.id])
    return await _serialize_conversation_summary(db, conversation, last_previews.get(conversation.id))


async def _send_stylist_message_common(
    *,
    db: AsyncSession,
    conversation_id: UUID,
    current_user: User,
    text_value: str,
    attachments: list[dict],
    payload: dict,
    recommended_product_ids: list[str],
) -> LiveStylistConversationDetail:
    await ensure_live_stylist_schema(db)
    conversation = (
        await db.execute(select(LiveStylistConversation).where(LiveStylistConversation.id == conversation_id))
    ).scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Обращение не найдено")
    if not text_value and not attachments:
        raise HTTPException(status_code=400, detail="Сообщение, карточка товара или фото обязательны")

    now = datetime.now(timezone.utc)
    if not conversation.assigned_stylist_user_id:
        conversation.assigned_stylist_user_id = current_user.id
        conversation.assigned_at = now

    message_payload = {"channel": "admin_live_stylist", **(payload or {})}
    message = StylistChatMessage(
        user_id=conversation.customer_user_id,
        conversation_id=conversation.id,
        sender_user_id=current_user.id,
        role="stylist",
        text=text_value or None,
        attachments=attachments,
        payload=message_payload,
        created_at=now,
    )
    db.add(message)

    previous_recommended_ids = [str(item) for item in (conversation.recommended_product_ids or []) if str(item).strip()]
    merged_recommended_ids = previous_recommended_ids[:]
    for product_id in recommended_product_ids:
        if product_id not in merged_recommended_ids:
            merged_recommended_ids.append(product_id)
    conversation.recommended_product_ids = merged_recommended_ids

    conversation.status = "in_progress" if conversation.status == "requested" else conversation.status
    conversation.last_message_at = now
    conversation.last_stylist_message_at = now
    conversation.first_response_at = conversation.first_response_at or now
    conversation.unread_for_customer_count = (conversation.unread_for_customer_count or 0) + 1
    conversation.unread_for_stylist_count = 0
    conversation.updated_at = now
    _set_stylist_typing_meta(conversation, current_user=current_user, is_typing=False)

    if merged_recommended_ids != previous_recommended_ids:
        await log_live_stylist_event(
            db=db,
            conversation_id=conversation.id,
            actor_user_id=current_user.id,
            event_type="recommendations_updated",
            payload=make_event_payload(recommended_product_ids=merged_recommended_ids),
            created_at=now,
        )

    await log_live_stylist_event(
        db=db,
        conversation_id=conversation.id,
        actor_user_id=current_user.id,
        event_type="message_sent",
        payload=make_event_payload(
            text_preview=(text_value or "")[:160],
            attachment_count=len(attachments),
            image_count=sum(1 for item in attachments if isinstance(item, dict) and item.get("type") == "image"),
            product_ids=recommended_product_ids,
        ),
        created_at=now,
    )
    await db.commit()
    await db.refresh(conversation)
    preview = _message_preview(text_value, attachments)
    return await _build_conversation_detail(db, conversation, last_message_preview=preview)


@router.post("/conversations/{conversation_id}/messages", response_model=LiveStylistConversationDetail)
async def send_stylist_message(
    conversation_id: UUID,
    payload: LiveStylistSendMessageRequest,
    current_user: User = Depends(require_any_role(["admin", "seller", "manager"])),
    db: AsyncSession = Depends(get_db),
):
    return await _send_stylist_message_common(
        db=db,
        conversation_id=conversation_id,
        current_user=current_user,
        text_value=payload.text.strip(),
        attachments=[],
        payload={},
        recommended_product_ids=[],
    )


@router.post("/conversations/{conversation_id}/messages/compose", response_model=LiveStylistConversationDetail)
async def compose_stylist_message(
    conversation_id: UUID,
    text: str = Form(""),
    product_ids: str = Form(""),
    photo: UploadFile | None = File(None),
    photos: list[UploadFile] | None = File(None),
    current_user: User = Depends(require_any_role(["admin", "seller", "manager"])),
    db: AsyncSession = Depends(get_db),
):
    text_value = (text or "").strip()
    product_id_values: list[str] = []
    product_uuid_values: list[UUID] = []
    for item in (product_ids or "").split(","):
        token = item.strip()
        if not token:
            continue
        try:
            parsed = UUID(token)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Некорректный product_id: {token}") from exc
        if str(parsed) not in product_id_values:
            product_id_values.append(str(parsed))
            product_uuid_values.append(parsed)

    selected_products: list[Product] = []
    if product_uuid_values:
        selected_products = (
            await db.execute(
                select(Product).where(Product.id.in_(product_uuid_values), Product.is_active == True)
            )
        ).scalars().all()
        found_ids = {str(item.id) for item in selected_products}
        missing_ids = [item for item in product_id_values if item not in found_ids]
        if missing_ids:
            raise HTTPException(status_code=404, detail=f"Товары не найдены: {', '.join(missing_ids)}")

    attachments: list[dict] = []
    for product in sorted(selected_products, key=lambda item: product_id_values.index(str(item.id))):
        product_card = await _serialize_attachable_product(db, product)
        attachments.append(
            {
                "type": "product",
                "product_id": product_card.id,
                "name": product_card.name,
                "brand": product_card.brand,
                "category": product_card.category,
                "article": product_card.article,
                "external_code": product_card.external_code,
                "price": product_card.price,
                "image_url": product_card.image_url,
                "in_stock": product_card.in_stock,
            }
        )

    uploaded_photos: list[UploadFile] = []
    if photo is not None and photo.filename:
        uploaded_photos.append(photo)
    uploaded_photos.extend([file for file in (photos or []) if file and file.filename])
    if uploaded_photos:
        media_dir = Path("static/stylist_chat") / str(conversation_id)
        media_dir.mkdir(parents=True, exist_ok=True)
    for photo in uploaded_photos:
        content = await photo.read()
        if len(content) > 8 * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"Фото {photo.filename} должно быть меньше 8 МБ")
        filename = _safe_upload_name(photo.filename)
        target = media_dir / filename
        target.write_bytes(content)
        attachments.append(
            {
                "type": "image",
                "url": f"/static/stylist_chat/{conversation_id}/{filename}",
                "name": photo.filename,
            }
        )

    return await _send_stylist_message_common(
        db=db,
        conversation_id=conversation_id,
        current_user=current_user,
        text_value=text_value,
        attachments=attachments,
        payload={
            "products": [
                {
                    "id": str(product.id),
                    "name": product.name,
                    "brand": product.brand,
                    "price": int(product.price or 0),
                    "images": product.images if isinstance(product.images, list) else [],
                    "category": product.category,
                    "article": product.article,
                    "external_code": product.external_code,
                    "external_id": product.external_id,
                }
                for product in selected_products
            ],
        },
        recommended_product_ids=product_id_values,
    )


@router.post("/conversations/{conversation_id}/typing")
async def update_stylist_typing_state(
    conversation_id: UUID,
    payload: LiveStylistTypingStateRequest,
    current_user: User = Depends(require_any_role(["admin", "seller", "manager"])),
    db: AsyncSession = Depends(get_db),
):
    conversation = (
        await db.execute(select(LiveStylistConversation).where(LiveStylistConversation.id == conversation_id))
    ).scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Обращение не найдено")

    _set_stylist_typing_meta(conversation, current_user=current_user, is_typing=payload.is_typing)
    conversation.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True, "is_typing": payload.is_typing}


@router.delete("/conversations/{conversation_id}/messages", response_model=LiveStylistConversationDetail)
async def clear_conversation_messages(
    conversation_id: UUID,
    current_user: User = Depends(require_any_role(["admin", "seller", "manager"])),
    db: AsyncSession = Depends(get_db),
):
    await ensure_live_stylist_schema(db)
    conversation = (
        await db.execute(select(LiveStylistConversation).where(LiveStylistConversation.id == conversation_id))
    ).scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Обращение не найдено")

    messages = (
        await db.execute(
            select(StylistChatMessage).where(StylistChatMessage.conversation_id == conversation.id)
        )
    ).scalars().all()
    deleted_count = len(messages)
    for message in messages:
        await db.delete(message)

    conversation.unread_for_customer_count = 0
    conversation.unread_for_stylist_count = 0
    conversation.last_message_at = None
    conversation.last_stylist_message_at = None
    conversation.first_response_at = None
    conversation.recommended_product_ids = []
    conversation.updated_at = datetime.now(timezone.utc)
    _set_stylist_typing_meta(conversation, current_user=current_user, is_typing=False)

    await log_live_stylist_event(
        db=db,
        conversation_id=conversation.id,
        actor_user_id=current_user.id,
        event_type="chat_cleared",
        payload=make_event_payload(deleted_message_count=deleted_count),
        created_at=conversation.updated_at,
    )
    await db.commit()
    await db.refresh(conversation)
    return await _build_conversation_detail(db, conversation, last_message_preview=None)


@router.post("/conversations/open-for-customer/{customer_user_id}", response_model=LiveStylistConversationSummary)
async def ensure_customer_conversation(
    customer_user_id: UUID,
    source: str | None = Query(None),
    scenario: str | None = Query(None),
    _current_user: User = Depends(require_any_role(["admin", "seller", "manager"])),
    db: AsyncSession = Depends(get_db),
):
    await ensure_live_stylist_schema(db)
    conversation = await get_or_create_open_conversation(
        db=db,
        customer_user_id=customer_user_id,
        source=source,
        scenario=scenario,
        working_hours_status=get_live_stylist_status().get("status"),
    )
    await db.commit()
    await db.refresh(conversation)
    previews = await _fetch_last_message_previews(db, [conversation.id])
    return await _serialize_conversation_summary(db, conversation, previews.get(conversation.id))
