"""
API личного кабинета покупателя
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, status, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, text, func, asc, case
from pydantic import BaseModel
from typing import Optional, List, Any, Dict
from datetime import datetime, timezone
from uuid import UUID
from pathlib import Path
import logging
from uuid import uuid4
import re

from app.database.connection import get_db
from app.models.user import User
from app.models.purchase_history import PurchaseHistory
from app.models.product import Product
from app.models.cart import Cart
from app.models.cart_item import CartItem
from app.models.loyalty_transaction import LoyaltyTransaction
from app.models.saved_look import SavedLook
from app.models.customer_favorite_product import CustomerFavoriteProduct
from app.models.stylist_chat_message import StylistChatMessage
from app.models.live_stylist_conversation import LiveStylistConversation
from app.models.look import Look
from app.models.app_setting import AppSetting
from app.models.app_store import AppStore
from app.models.product_stock import ProductStock
from app.api.auth import get_current_user
from app.agents.stylist_agent import StylistAgent
from app.services.loyalty_service import LoyaltyService
from app.services.purchase_product_fields import derive_purchase_brand, derive_purchase_category
from app.services.live_stylist_service import get_live_stylist_status
from app.services.live_stylist_platform import ensure_live_stylist_schema, get_or_create_open_conversation

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_customer_visible_stylist_typing(conversation: LiveStylistConversation | None) -> Dict[str, Any] | None:
    if conversation is None:
        return None
    meta = conversation.meta if isinstance(conversation.meta, dict) else {}
    raw = meta.get("stylist_typing")
    if not isinstance(raw, dict):
        return None
    expires_raw = str(raw.get("expires_at") or "").strip()
    if expires_raw:
        try:
            expires_at = datetime.fromisoformat(expires_raw)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= datetime.now(timezone.utc):
                return None
        except ValueError:
            return None
    return {
        "is_typing": bool(raw.get("is_typing")),
        "stylist_user_id": raw.get("stylist_user_id"),
        "stylist_name": raw.get("stylist_name"),
        "updated_at": raw.get("updated_at"),
        "expires_at": raw.get("expires_at"),
    }


def _chat_ordering_asc():
    """
    Стабильный порядок сообщений в чате:
    1) created_at ASC
    2) при равном времени user -> assistant -> system
    3) id ASC как финальный tie-breaker
    """
    role_order = case(
        (StylistChatMessage.role == "user", 0),
        (StylistChatMessage.role == "assistant", 1),
        else_=2,
    )
    return asc(StylistChatMessage.created_at), asc(role_order), asc(StylistChatMessage.id)


def _product_image_url(product: Product) -> Optional[str]:
    images = product.images if isinstance(product.images, list) else []
    if not images:
        return None
    first = images[0]
    return str(first) if first else None


def _favorite_product_response(row: CustomerFavoriteProduct, product: Product) -> FavoriteProductResponse:
    return FavoriteProductResponse(
        id=str(row.id),
        product_id=str(row.product_id),
        name=product.name,
        brand=product.brand,
        category=product.category,
        article=product.article,
        external_code=product.external_code,
        price=((product.price or 0) / 100) if product.price is not None else None,
        image_url=_product_image_url(product),
        source=row.source,
        created_at=row.created_at.isoformat() if row.created_at else None,
    )


def _product_payload_for_customer_look(product: Product) -> Dict[str, Any]:
    return {
        "id": str(product.id),
        "name": product.name,
        "brand": product.brand,
        "category": product.category,
        "article": product.article,
        "external_code": product.external_code,
        "price": product.price,
        "image_url": _product_image_url(product),
        "images": product.images if isinstance(product.images, list) else [],
    }


async def _saved_look_response(db: AsyncSession, saved_look: SavedLook, look: Look) -> SavedLookResponse:
    product_ids: List[UUID] = []
    for raw_id in look.product_ids or []:
        try:
            product_ids.append(UUID(str(raw_id)))
        except Exception:
            continue

    products_by_id: Dict[str, Product] = {}
    if product_ids:
        products = (await db.execute(select(Product).where(Product.id.in_(product_ids)))).scalars().all()
        products_by_id = {str(product.id): product for product in products}

    product_rows: List[Dict[str, Any]] = []
    for raw_id in look.product_ids or []:
        product = products_by_id.get(str(raw_id))
        if product is not None:
            product_rows.append(_product_payload_for_customer_look(product))

    metadata = look.generation_metadata if isinstance(look.generation_metadata, dict) else {}
    image_urls = look.image_urls if isinstance(look.image_urls, list) else []

    return SavedLookResponse(
        id=str(saved_look.id),
        look_id=str(saved_look.look_id),
        look_name=look.name,
        save_type=saved_look.save_type,
        notes=saved_look.notes,
        is_purchased=saved_look.is_purchased,
        look_style=look.style,
        look_mood=look.mood,
        look_description=look.description,
        look_image_url=look.image_url,
        look_image_urls=image_urls,
        total_price=metadata.get("total_price") if isinstance(metadata.get("total_price"), int) else None,
        products=product_rows,
        is_user_created=look.source_provider == "customer_builder" or saved_look.save_type == "generated",
        created_at=saved_look.created_at.isoformat() if saved_look.created_at else datetime.now(timezone.utc).isoformat(),
    )


def _parse_product_uuid_list(raw_items: List[str]) -> List[UUID]:
    result: List[UUID] = []
    seen: set[UUID] = set()
    for raw in raw_items or []:
        try:
            parsed = UUID(str(raw).strip())
        except Exception:
            continue
        if parsed in seen:
            continue
        seen.add(parsed)
        result.append(parsed)
    return result


def _chat_ordering_desc():
    """
    Стабильный порядок сообщений в обратной сортировке (для выборки последних).
    """
    role_order = case(
        (StylistChatMessage.role == "assistant", 0),
        (StylistChatMessage.role == "user", 1),
        else_=2,
    )
    return desc(StylistChatMessage.created_at), asc(role_order), desc(StylistChatMessage.id)


async def _build_store_info_fallback(
    db: AsyncSession,
    message: str,
    current_city: Optional[str],
) -> Optional[str]:
    text_msg = (message or "").lower()
    asks_store = any(x in text_msg for x in ["магазин", "адрес", "как найти", "где вы", "есть в городе"])
    if not asks_store:
        return None

    city_hint: Optional[str] = None
    if "ялт" in text_msg:
        city_hint = "Ялта"
    elif "симферопол" in text_msg:
        city_hint = "Симферополь"
    elif current_city:
        city_hint = current_city

    stmt = select(AppStore).where(AppStore.is_active == True)
    if city_hint:
        stmt = stmt.where(func.lower(AppStore.city).ilike(f"%{city_hint.lower()}%"))
    stmt = stmt.order_by(AppStore.sort_order.asc(), AppStore.title.asc()).limit(3)
    stores = list((await db.execute(stmt)).scalars().all())

    if not stores and city_hint:
        alt_stmt = (
            select(AppStore)
            .where(AppStore.is_active == True)
            .order_by(AppStore.sort_order.asc(), AppStore.title.asc())
            .limit(2)
        )
        stores = list((await db.execute(alt_stmt)).scalars().all())

    if not stores:
        return "Сейчас не вижу активных магазинов в данных. Могу уточнить у команды и сразу вернуться к Вам с точным адресом."

    lines = []
    for s in stores:
        line = f"{s.city}: {s.title}, {s.address}"
        if s.working_hours:
            line += f" ({s.working_hours})"
        lines.append(line)

    intro = (
        f"Да, проверила магазины в городе {city_hint}. " if city_hint else "Проверила актуальные магазины. "
    )
    return intro + "Вот ближайшие варианты: " + " | ".join(lines)


class CustomerProfileResponse(BaseModel):
    id: str
    phone: Optional[str]
    email: Optional[str]
    full_name: Optional[str]
    discount_card_number: Optional[str]
    loyalty_points: int
    customer_segment: Optional[str]
    total_purchases: int
    total_spent: float
    average_check: Optional[float]
    last_purchase_date: Optional[str]
    purchase_preferences: Optional[dict]
    preferred_delivery: Optional[dict] = None

    class Config:
        from_attributes = True


class PurchaseHistoryItem(BaseModel):
    id: str
    purchase_date: str
    product_name: Optional[str]
    quantity: int
    total_amount: float
    category: Optional[str]
    brand: Optional[str]

    class Config:
        from_attributes = True


class PurchaseStatsResponse(BaseModel):
    total_purchases: int
    total_spent: float
    average_check: float
    favorite_categories: List[str]
    favorite_brands: List[str]


class SavedLookResponse(BaseModel):
    id: str
    look_id: str
    look_name: str
    save_type: str
    notes: Optional[str]
    is_purchased: bool
    look_style: Optional[str] = None
    look_mood: Optional[str] = None
    look_description: Optional[str] = None
    look_image_url: Optional[str] = None
    look_image_urls: List[Any] = []
    total_price: Optional[int] = None
    products: List[Dict[str, Any]] = []
    is_user_created: bool = False
    created_at: str

    class Config:
        from_attributes = True


class CustomerLookProduct(BaseModel):
    id: str
    role: Optional[str] = None
    selected_image_url: Optional[str] = None


class CustomerGeneratedLookRequest(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    goal: Optional[str] = None
    total_price: Optional[int] = None
    products: List[CustomerLookProduct]
    notes: Optional[str] = None


class FavoriteProductResponse(BaseModel):
    id: str
    product_id: str
    name: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    article: Optional[str] = None
    external_code: Optional[str] = None
    price: Optional[float] = None
    image_url: Optional[str] = None
    source: Optional[str] = None
    created_at: Optional[str] = None


class FavoriteProductSyncRequest(BaseModel):
    product_ids: List[str]
    source: Optional[str] = "app"


class StylistChatMessageResponse(BaseModel):
    id: str
    role: str
    text: Optional[str] = None
    attachments: List[dict] = []
    payload: Optional[dict] = None
    created_at: Optional[str] = None


class StylistChatSendResponse(BaseModel):
    messages: List[StylistChatMessageResponse]
    ai_enabled: bool


def _serialize_stylist_message(message: StylistChatMessage) -> StylistChatMessageResponse:
    return StylistChatMessageResponse(
        id=str(message.id),
        role=message.role,
        text=message.text,
        attachments=message.attachments or [],
        payload=message.payload or {},
        created_at=message.created_at.isoformat() if message.created_at else None,
    )


async def _ai_stylist_enabled(db: AsyncSession) -> bool:
    result = await db.execute(select(AppSetting).where(AppSetting.key == "ai_stylist_enabled"))
    setting = result.scalar_one_or_none()
    if setting is None:
        return True
    return str(setting.value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


async def _ensure_stylist_chat_schema(db: AsyncSession) -> None:
    """Safety net: create stylist chat schema if migration wasn't applied."""
    await ensure_live_stylist_schema(db)


def _safe_upload_name(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    return f"{uuid4().hex}{suffix}"


async def _get_or_create_cart(db: AsyncSession, user_id: UUID) -> Cart:
    cart = (await db.execute(select(Cart).where(Cart.user_id == user_id))).scalar_one_or_none()
    if cart:
        return cart
    cart = Cart(user_id=user_id)
    db.add(cart)
    await db.flush()
    return cart


async def _serialize_cart_payload(db: AsyncSession, cart: Cart) -> Dict[str, Any]:
    items = (
        await db.execute(select(CartItem).where(CartItem.cart_id == cart.id))
    ).scalars().all()
    product_ids = [x.product_id for x in items]
    products_map: Dict[UUID, Product] = {}
    if product_ids:
        products = (await db.execute(select(Product).where(Product.id.in_(product_ids)))).scalars().all()
        products_map = {p.id: p for p in products}

    payload_products: List[Dict[str, Any]] = []
    payload_items: List[Dict[str, Any]] = []
    total = 0

    for item in items:
        product = products_map.get(item.product_id)
        if not product:
            continue
        qty = int(item.quantity or 0)
        line_total = int(product.price or 0) * qty
        total += line_total
        payload_items.append(
            {
                "product_id": str(product.id),
                "name": product.name,
                "quantity": qty,
                "unit_price": int(product.price or 0),
                "line_total": line_total,
            }
        )
        payload_products.append(
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
        )

    return {
        "items": payload_items,
        "products": payload_products,
        "total_amount": total,
        "currency": "RUB",
    }


def _extract_cart_quantity(text: str) -> int:
    msg = (text or "").lower()
    with_units = re.search(r"\b(\d{1,2})\s*(шт|штуки|штук)\b", msg)
    if with_units:
        return max(1, min(int(with_units.group(1)), 99))
    add_number = re.search(r"\bдобав(?:ь|ить)?\s+(\d{1,2})\b", msg)
    if add_number:
        return max(1, min(int(add_number.group(1)), 99))
    return 1


def _parse_csv_tags(value: Optional[str]) -> List[str]:
    if not value:
        return []
    tags: List[str] = []
    for item in value.split(","):
        tag = item.strip().lower()
        if tag:
            tags.append(tag)
    # preserve order while removing duplicates
    unique: List[str] = []
    for tag in tags:
        if tag not in unique:
            unique.append(tag)
    return unique


def _parse_csv_uuids(value: Optional[str]) -> List[str]:
    if not value:
        return []
    parsed: List[str] = []
    for item in value.split(","):
        token = item.strip()
        if not token:
            continue
        try:
            parsed.append(str(UUID(token)))
        except ValueError:
            continue
    return parsed


async def _build_purchase_history_context(db: AsyncSession, user: User) -> Dict[str, Any]:
    rows = (
        await db.execute(
            select(PurchaseHistory)
            .where(PurchaseHistory.user_id == user.id)
            .order_by(desc(PurchaseHistory.purchase_date))
            .limit(20)
        )
    ).scalars().all()

    if not rows:
        return {
            "available": False,
            "last_purchases": [],
            "categories": [],
            "brands_or_lines": [],
            "metals_or_colors": [],
            "sizes": [],
            "average_item_price": None,
            "purchase_frequency": None,
            "gift_scenarios": [],
            "purchase_cities": [],
        }

    categories = list({x.category for x in rows if x.category})[:10]
    brands = list({x.brand for x in rows if x.brand})[:10]
    purchases = []
    for item in rows[:5]:
        purchases.append(
            {
                "date": item.purchase_date.isoformat() if item.purchase_date else None,
                "product_name": item.product_name,
                "category": item.category,
                "brand": item.brand,
                "total_amount": (item.total_amount or 0) / 100,
            }
        )

    average_item_price = None
    if user.average_check is not None:
        average_item_price = user.average_check / 100

    return {
        "available": True,
        "last_purchases": purchases,
        "categories": categories,
        "brands_or_lines": brands,
        "metals_or_colors": [],
        "sizes": [],
        "average_item_price": average_item_price,
        "purchase_frequency": user.total_purchases,
        "gift_scenarios": [],
        "purchase_cities": [user.city] if user.city else [],
    }


async def _find_product_for_cart_command(
    db: AsyncSession,
    text: str,
    product_id_hint: Optional[str] = None,
) -> Optional[Product]:
    if product_id_hint:
        try:
            pid = UUID(str(product_id_hint))
            product = (await db.execute(select(Product).where(Product.id == pid, Product.is_active == True))).scalar_one_or_none()
            if product:
                return product
        except ValueError:
            pass

    msg = (text or "").strip()
    if not msg:
        return None

    uuid_match = re.search(
        r"\b[0-9a-fA-F]{8}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{4}\-[0-9a-fA-F]{12}\b",
        msg,
    )
    if uuid_match:
        try:
            pid = UUID(uuid_match.group(0))
            product = (await db.execute(select(Product).where(Product.id == pid, Product.is_active == True))).scalar_one_or_none()
            if product:
                return product
        except ValueError:
            pass

    tokens = list({t for t in re.findall(r"[a-zA-Zа-яА-Я0-9_\-]{3,}", msg)})[:10]
    if not tokens:
        return None

    stop_words = {
        "добавь", "добавить", "корзину", "корзина", "удали", "удалить", "убери",
        "из", "покажи", "показать", "что", "в", "мне", "нужно", "товар", "товары",
        "артикул", "код", "шт", "штук", "штуки",
    }
    tokens = [t for t in tokens if t.lower() not in stop_words]
    if not tokens:
        return None

    clauses = []
    for token in tokens:
        like = f"%{token}%"
        clauses.extend(
            [
                Product.article == token,
                Product.external_code == token,
                Product.name.ilike(like),
                Product.article.ilike(like),
                Product.external_code.ilike(like),
            ]
        )
    result = await db.execute(select(Product).where(Product.is_active == True, or_(*clauses)).limit(20))
    products = list(result.scalars().all())
    if not products:
        return None

    normalized = {t.lower() for t in tokens}

    def _score(product: Product) -> tuple[int, int]:
        article = str(product.article or "").lower()
        ext = str(product.external_code or "").lower()
        exact = int(article in normalized or ext in normalized)
        has_images = int(isinstance(product.images, list) and len(product.images) > 0)
        return (exact, has_images)

    products.sort(key=_score, reverse=True)
    return products[0]


def _tokenize_similarity_text(value: str) -> set[str]:
    tokens = re.findall(r"[a-zA-Zа-яА-Я0-9]{2,}", (value or "").lower())
    stop_words = {
        "для", "или", "как", "что", "это", "очень", "под", "над", "без", "из",
        "the", "and", "with", "from", "this", "that",
    }
    return {t for t in tokens if t not in stop_words}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return float(inter / union) if union else 0.0


def _spec_tokens(product: Product) -> set[str]:
    specs = product.specifications if isinstance(product.specifications, dict) else {}
    tokens: set[str] = set()
    for key, value in specs.items():
        if isinstance(key, str):
            tokens |= _tokenize_similarity_text(key)
        if isinstance(value, str):
            tokens |= _tokenize_similarity_text(value)
        elif isinstance(value, (int, float)):
            tokens.add(str(value))
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    tokens |= _tokenize_similarity_text(item)
    return tokens


async def _serialize_chat_product(db: AsyncSession, product: Product, stock_cache: Optional[Dict[UUID, float]] = None) -> Dict[str, Any]:
    if stock_cache is not None and product.id in stock_cache:
        stock = float(stock_cache[product.id] or 0)
    else:
        stock = float(
            (
                await db.execute(
                    select(func.sum(ProductStock.available_quantity)).where(ProductStock.product_id == product.id)
                )
            ).scalar_one_or_none()
            or 0
        )
    return {
        "id": str(product.id),
        "name": product.name,
        "brand": product.brand,
        "price": int(product.price or 0),
        "images": product.images if isinstance(product.images, list) else [],
        "category": product.category,
        "tags": product.tags if isinstance(product.tags, list) else [],
        "stock": stock,
        "in_stock": stock > 0,
        "article": product.article,
        "external_code": product.external_code,
        "external_id": product.external_id,
    }


async def _find_similar_products(
    db: AsyncSession,
    source: Product,
    limit: int = 6,
    in_stock_only: bool = False,
    with_images_only: bool = False,
) -> List[Dict[str, Any]]:
    """
    Подбор похожих товаров с детерминированным скорингом:
    категория, характеристики, теги, текст, цена, наличие.
    """
    query = select(Product).where(Product.is_active == True, Product.id != source.id)
    if source.category:
        query = query.where(Product.category == source.category)
    source_price = int(source.price or 0)
    if source_price > 0:
        min_price = int(source_price * 0.35)
        max_price = int(source_price * 2.20)
        query = query.where(Product.price >= min_price, Product.price <= max_price)

    candidates = list((await db.execute(query.limit(350))).scalars().all())
    if not candidates:
        return []

    source_name_tokens = _tokenize_similarity_text(source.name or "")
    source_desc_tokens = _tokenize_similarity_text(source.description or "")
    source_tag_tokens = {str(x).lower() for x in (source.tags or []) if isinstance(x, str)}
    source_spec_tokens = _spec_tokens(source)

    candidate_ids = [x.id for x in candidates]
    stock_rows = (
        await db.execute(
            select(ProductStock.product_id, func.sum(ProductStock.available_quantity).label("qty"))
            .where(ProductStock.product_id.in_(candidate_ids))
            .group_by(ProductStock.product_id)
        )
    ).all()
    stock_map: Dict[UUID, float] = {row.product_id: float(row.qty or 0) for row in stock_rows}

    scored: List[tuple[float, Product]] = []
    for candidate in candidates:
        candidate_stock = float(stock_map.get(candidate.id, 0) or 0)
        if in_stock_only and candidate_stock <= 0:
            continue
        if with_images_only and (not isinstance(candidate.images, list) or len(candidate.images) == 0):
            continue
        c_name_tokens = _tokenize_similarity_text(candidate.name or "")
        c_desc_tokens = _tokenize_similarity_text(candidate.description or "")
        c_tag_tokens = {str(x).lower() for x in (candidate.tags or []) if isinstance(x, str)}
        c_spec_tokens = _spec_tokens(candidate)

        category_score = 1.0 if (source.category and candidate.category == source.category) else 0.0
        brand_score = 1.0 if (source.brand and candidate.brand and source.brand == candidate.brand) else 0.0
        tags_score = _jaccard(source_tag_tokens, c_tag_tokens)
        specs_score = _jaccard(source_spec_tokens, c_spec_tokens)
        name_score = _jaccard(source_name_tokens, c_name_tokens)
        desc_score = _jaccard(source_desc_tokens, c_desc_tokens)

        candidate_price = int(candidate.price or 0)
        if source_price > 0 and candidate_price > 0:
            price_score = max(0.0, 1.0 - abs(candidate_price - source_price) / float(source_price))
        else:
            price_score = 0.0

        in_stock_score = 1.0 if candidate_stock > 0 else 0.0
        image_score = 1.0 if isinstance(candidate.images, list) and len(candidate.images) > 0 else 0.0

        similarity = (
            0.20 * category_score
            + 0.08 * brand_score
            + 0.14 * tags_score
            + 0.20 * specs_score
            + 0.16 * name_score
            + 0.06 * desc_score
            + 0.12 * price_score
            + 0.03 * in_stock_score
            + 0.01 * image_score
        )
        scored.append((similarity, candidate))

    if not scored:
        return []

    scored.sort(
        key=lambda x: (
            x[0],
            int(float(stock_map.get(x[1].id, 0) or 0) > 0),
            int(isinstance(x[1].images, list) and len(x[1].images) > 0),
            int(x[1].price or 0),
        ),
        reverse=True,
    )
    top = scored[: max(limit, 1)]
    result = []
    for similarity, product in top:
        payload = await _serialize_chat_product(db, product, stock_cache=stock_map)
        payload["similarity_score"] = round(float(similarity), 3)
        result.append(payload)
    return result


async def _handle_cart_command_if_any(
    db: AsyncSession,
    current_user: User,
    text: str,
    product_id_hint: Optional[str] = None,
    has_attachments: bool = False,
) -> Optional[Dict[str, Any]]:
    if has_attachments:
        return None

    msg = (text or "").strip()
    if not msg:
        return None

    lower = msg.lower()
    show_cmd = any(x in lower for x in ["покажи корз", "показать корз", "что в корз", "моя корз", "корзина"])
    add_cmd = any(x in lower for x in ["добавь", "добавить"]) and "корз" in lower
    remove_cmd = any(x in lower for x in ["удали", "удалить", "убери"]) and "корз" in lower
    clear_cmd = any(x in lower for x in ["очисти корз", "очистить корз", "пустая корз", "очисти всю корз"])
    replace_cmd = any(x in lower for x in ["подбери замен", "подобери замен", "замена", "аналог", "похож"]) and (
        bool(product_id_hint) or any(x in lower for x in ["товар", "артикул", "код"])
    )

    if not any([show_cmd, add_cmd, remove_cmd, clear_cmd, replace_cmd]):
        return None

    cart = await _get_or_create_cart(db, current_user.id)

    if clear_cmd:
        existing_items = (
            await db.execute(select(CartItem).where(CartItem.cart_id == cart.id))
        ).scalars().all()
        for item in existing_items:
            await db.delete(item)
        await db.flush()
        cart_payload = await _serialize_cart_payload(db, cart)
        return {
            "text": "Готово, корзина очищена. Могу сразу собрать новый комплект под ваш запрос.",
            "payload": {"cart_action": "clear", "cart": cart_payload, "products": []},
        }

    if show_cmd and not add_cmd and not remove_cmd:
        cart_payload = await _serialize_cart_payload(db, cart)
        items_count = len(cart_payload.get("items") or [])
        if items_count == 0:
            reply = "Корзина пока пустая. Напишите, что добавить: артикул, код или название украшения."
        else:
            reply = f"В корзине {items_count} поз. на {int(cart_payload.get('total_amount') or 0) / 100:.0f} ₽."
        return {
            "text": reply,
            "payload": {"cart_action": "show", "cart": cart_payload, "products": cart_payload.get("products") or []},
        }

    if replace_cmd:
        source = await _find_product_for_cart_command(db, msg, product_id_hint=product_id_hint)
        if not source:
            return {
                "text": "Не смогла определить, какой товар заменить. Нажмите «Замена» у карточки или укажите артикул.",
                "payload": {"cart_action": "replace_not_found", "products": []},
            }
        alternatives = await _find_similar_products(
            db,
            source=source,
            limit=6,
            in_stock_only=True,
            with_images_only=True,
        )
        if not alternatives:
            return {
                "text": f"Для {source.name} пока не нашла близкие замены. Могу расширить критерии и предложить варианты по стилю.",
                "payload": {
                    "cart_action": "replace_empty",
                    "source_product": await _serialize_chat_product(db, source),
                    "products": [],
                },
            }
        return {
            "text": f"Подобрала замену для «{source.name}». Ниже похожие варианты, можно открыть карточку и добавить в корзину.",
            "payload": {
                "cart_action": "replace_suggest",
                "source_product": await _serialize_chat_product(db, source),
                "replace_strategy": "category+specs+tags+name+description+price+stock",
                "products": alternatives,
            },
        }

    product = await _find_product_for_cart_command(db, msg, product_id_hint=product_id_hint)
    if not product:
        return {
            "text": "Не нашла товар в каталоге. Напишите артикул, код или точное название, и я добавлю его в корзину.",
            "payload": {"cart_action": "not_found"},
        }

    if add_cmd:
        qty = _extract_cart_quantity(msg)
        existing = (
            await db.execute(
                select(CartItem).where(
                    CartItem.cart_id == cart.id,
                    CartItem.product_id == product.id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.quantity = max(1, min(int(existing.quantity or 0) + qty, 99))
        else:
            db.add(CartItem(cart_id=cart.id, product_id=product.id, quantity=qty))
        await db.flush()
        cart_payload = await _serialize_cart_payload(db, cart)
        return {
            "text": f"Добавила в корзину: {product.name} × {qty}. Могу предложить к нему комплект.",
            "payload": {"cart_action": "add", "cart": cart_payload, "products": cart_payload.get("products") or []},
        }

    if remove_cmd:
        existing = (
            await db.execute(
                select(CartItem).where(
                    CartItem.cart_id == cart.id,
                    CartItem.product_id == product.id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            await db.delete(existing)
            await db.flush()
            cart_payload = await _serialize_cart_payload(db, cart)
            return {
                "text": f"Убрала из корзины: {product.name}.",
                "payload": {"cart_action": "remove", "cart": cart_payload, "products": cart_payload.get("products") or []},
            }
        cart_payload = await _serialize_cart_payload(db, cart)
        return {
            "text": f"Товара {product.name} нет в корзине. Могу добавить его обратно при необходимости.",
            "payload": {"cart_action": "remove_miss", "cart": cart_payload, "products": cart_payload.get("products") or []},
        }

    return None


@router.get("/profile", response_model=CustomerProfileResponse)
async def get_customer_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Профиль покупателя"""
    if not current_user.is_customer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступно только для покупателей"
        )
    
    return CustomerProfileResponse(
        id=str(current_user.id),
        phone=current_user.phone,
        email=current_user.email,
        full_name=current_user.full_name,
        discount_card_number=current_user.discount_card_number,
        loyalty_points=current_user.loyalty_points or 0,
        customer_segment=current_user.customer_segment,
        total_purchases=current_user.total_purchases,
        total_spent=(current_user.total_spent or 0) / 100,
        average_check=(current_user.average_check / 100) if current_user.average_check else None,
        last_purchase_date=current_user.last_purchase_date.isoformat() if current_user.last_purchase_date else None,
        purchase_preferences=current_user.purchase_preferences,
        preferred_delivery=(current_user.preferences or {}).get("preferred_delivery")
    )


@router.get("/stylist-chat/messages", response_model=List[StylistChatMessageResponse])
async def get_stylist_chat_messages(
    limit: int = Query(80, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """История чата покупателя со стилистом."""
    await _ensure_stylist_chat_schema(db)
    open_conversation = (
        await db.execute(
            select(LiveStylistConversation)
            .where(
                LiveStylistConversation.customer_user_id == current_user.id,
                LiveStylistConversation.status != "completed",
            )
            .order_by(
                LiveStylistConversation.last_message_at.desc().nullslast(),
                LiveStylistConversation.created_at.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if open_conversation is not None and (open_conversation.unread_for_customer_count or 0) > 0:
        open_conversation.unread_for_customer_count = 0
        open_conversation.updated_at = datetime.now(timezone.utc)
        await db.commit()
    result = await db.execute(
        select(StylistChatMessage)
        .where(StylistChatMessage.user_id == current_user.id)
        .order_by(*_chat_ordering_asc())
        .limit(limit)
    )
    messages = list(result.scalars().all())
    return [_serialize_stylist_message(message) for message in messages]


@router.get("/stylist-chat/status")
async def get_stylist_chat_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    open_conversation = (
        await db.execute(
            select(LiveStylistConversation)
            .where(
                LiveStylistConversation.customer_user_id == current_user.id,
                LiveStylistConversation.status != "completed",
            )
            .order_by(
                LiveStylistConversation.last_message_at.desc().nullslast(),
                LiveStylistConversation.created_at.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return {
        **get_live_stylist_status(),
        "stylist_typing": _get_customer_visible_stylist_typing(open_conversation),
    }


@router.delete("/stylist-chat/messages")
async def clear_stylist_chat_messages(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Полная очистка истории чата покупателя со стилистом."""
    await _ensure_stylist_chat_schema(db)
    rows = (
        await db.execute(
            select(StylistChatMessage).where(StylistChatMessage.user_id == current_user.id)
        )
    ).scalars().all()
    deleted = 0
    for row in rows:
        await db.delete(row)
        deleted += 1
    await db.commit()
    return {"ok": True, "deleted": deleted}


@router.get("/stylist-chat/replacements/{product_id}", response_model=Dict[str, Any])
async def get_stylist_product_replacements(
    product_id: str,
    limit: int = Query(6, ge=1, le=12),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Подобрать замены для товара из наличия (без записи сообщения в чат)."""
    del current_user  # endpoint доступен авторизованным покупателям, user нужен для ACL/auth chain
    try:
        source_uuid = UUID(str(product_id))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный product_id")

    source = (
        await db.execute(select(Product).where(Product.id == source_uuid, Product.is_active == True))
    ).scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не найден")

    products = await _find_similar_products(
        db,
        source=source,
        limit=limit,
        in_stock_only=True,
        with_images_only=True,
    )
    return {
        "source_product": await _serialize_chat_product(db, source),
        "products": products,
        "replace_strategy": "category+specs+tags+name+description+price+stock(in_stock_only)",
    }


@router.post("/stylist-chat/messages", response_model=StylistChatSendResponse)
async def send_stylist_chat_message(
    text: str = Form(""),
    product_id: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    source: Optional[str] = Form(None),
    scenario: Optional[str] = Form(None),
    quick_tags: Optional[str] = Form(None),
    favorite_product_ids: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Отправить сообщение стилисту. Если AI включен, сразу сохраняет ответ AI."""
    await _ensure_stylist_chat_schema(db)
    text = (text or "").strip()
    attachments: List[dict] = []

    if photo is not None and photo.filename:
        media_dir = Path("static/stylist_chat") / str(current_user.id)
        media_dir.mkdir(parents=True, exist_ok=True)
        filename = _safe_upload_name(photo.filename)
        target = media_dir / filename
        content = await photo.read()
        if len(content) > 8 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Фото должно быть меньше 8 МБ")
        target.write_bytes(content)
        attachments.append(
            {
                "type": "image",
                "url": f"/static/stylist_chat/{current_user.id}/{filename}",
                "name": photo.filename,
            }
        )

    if not text and not attachments:
        raise HTTPException(status_code=400, detail="Сообщение или фото обязательны")

    live_status = get_live_stylist_status()
    payload: Dict[str, Any] = {}
    clean_product_id = (product_id or "").strip()
    quick_tags_list = _parse_csv_tags(quick_tags)
    favorite_ids_list = _parse_csv_uuids(favorite_product_ids)
    purchase_history_context = await _build_purchase_history_context(db, current_user)
    current_time = datetime.now(timezone.utc)

    request_payload: Dict[str, Any] = {
        "text": text,
        "quick_tags": quick_tags_list,
        "favorite_product_ids": favorite_ids_list,
        "source_product_id": clean_product_id or None,
    }

    payload.update(
        {
            "source": (source or "").strip() or "customer_stylist_chat",
            "scenario": (scenario or "").strip() or "live_stylist",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "working_hours_status": live_status.get("status"),
            "working_hours_status_text": live_status.get("status_text"),
            "authorization_status": "authorized",
            "user": {
                "is_authorized": True,
                "name": current_user.full_name,
                "phone": current_user.phone,
                "city": current_user.city,
            },
            "request": request_payload,
            "purchase_history": purchase_history_context,
        }
    )
    if clean_product_id:
        payload["product_id"] = clean_product_id

    conversation = await get_or_create_open_conversation(
        db=db,
        customer_user_id=current_user.id,
        source=payload.get("source"),
        scenario=payload.get("scenario"),
        working_hours_status=live_status.get("status"),
        meta={
            "latest_request": request_payload,
            "authorization_status": "authorized",
        },
    )
    meta = conversation.meta if isinstance(conversation.meta, dict) else {}
    meta.pop("stylist_typing", None)
    conversation.meta = meta
    conversation.last_message_at = current_time
    conversation.last_customer_message_at = current_time
    conversation.unread_for_stylist_count = (conversation.unread_for_stylist_count or 0) + 1
    conversation.updated_at = current_time

    user_message = StylistChatMessage(
        user_id=current_user.id,
        conversation_id=conversation.id,
        sender_user_id=current_user.id,
        role="user",
        text=text,
        attachments=attachments,
        payload=payload,
        created_at=current_time,
    )
    db.add(user_message)
    await db.flush()

    ai_enabled = await _ai_stylist_enabled(db)
    created_messages = [user_message]
    cart_command_result = await _handle_cart_command_if_any(
        db=db,
        current_user=current_user,
        text=text,
        product_id_hint=clean_product_id or None,
        has_attachments=bool(attachments),
    )

    if cart_command_result is not None:
        assistant_message = StylistChatMessage(
            user_id=current_user.id,
            conversation_id=conversation.id,
            role="assistant",
            text=cart_command_result.get("text") or "Обновила корзину.",
            attachments=[],
            payload=cart_command_result.get("payload") or {},
            created_at=datetime.now(timezone.utc),
        )
        db.add(assistant_message)
        created_messages.append(assistant_message)
    elif ai_enabled:
        latest_result = await db.execute(
            select(StylistChatMessage)
            .where(
                StylistChatMessage.user_id == current_user.id,
                StylistChatMessage.payload.isnot(None),
            )
            .order_by(desc(StylistChatMessage.created_at))
            .limit(12)
        )
        session_id = None
        for item in latest_result.scalars().all():
            payload_data = item.payload if isinstance(item.payload, dict) else {}
            raw = payload_data.get("stylist_session_id")
            if raw:
                try:
                    session_id = UUID(str(raw))
                    break
                except ValueError:
                    continue

        prompt_text = text or "Покупатель прикрепил фото и просит помочь с подбором."
        prompt_text += (
            f"\nКонтекст: source={payload.get('source')}, scenario={payload.get('scenario')}, "
            f"working_hours_status={payload.get('working_hours_status')}."
        )
        if quick_tags_list:
            prompt_text += f"\nБыстрые теги: {', '.join(quick_tags_list)}."
        if favorite_ids_list:
            prompt_text += f"\nИзбранные товары: {', '.join(favorite_ids_list)}."
        if attachments:
            prompt_text += "\nПокупатель прикрепил фото. Учитывай его как визуальный контекст для консультации."
        if clean_product_id:
            prompt_text += f"\nКонтекст карточки товара: {clean_product_id}."

        history_result = await db.execute(
            select(StylistChatMessage)
            .where(StylistChatMessage.user_id == current_user.id)
            .order_by(*_chat_ordering_desc())
            .limit(24)
        )
        history_rows = list(reversed(history_result.scalars().all()))
        conversation_history = []
        for msg_row in history_rows:
            txt = (msg_row.text or "").strip()
            has_image = any(
                isinstance(x, dict) and x.get("type") == "image"
                for x in (msg_row.attachments or [])
            )
            if not txt and has_image:
                txt = "[прикреплено фото]"
            if not txt:
                continue
            conversation_history.append(
                {
                    "role": msg_row.role,
                    "text": txt,
                    "created_at": msg_row.created_at.isoformat() if msg_row.created_at else None,
                }
            )
        # Передаем расширенное окно истории, чтобы агент не терял нить диалога.
        conversation_history = conversation_history[-40:]

        try:
            result = await StylistAgent(db).process(
                user_id=current_user.id,
                message=prompt_text,
                city=current_user.city,
                session_id=session_id,
                conversation_history=conversation_history,
            )
            if result.get("llm_fallback"):
                logger.warning(
                    "Stylist response used LLM fallback: user_id=%s reason=%s",
                    current_user.id,
                    result.get("llm_fallback_reason") or "unknown",
                )
            assistant_message = StylistChatMessage(
                user_id=current_user.id,
                conversation_id=conversation.id,
                role="assistant",
                text=result.get("reply") or "Я посмотрю и подберу для вас варианты.",
                attachments=[],
                payload={
                    "stylist_session_id": result.get("session_id"),
                    "persona": result.get("persona"),
                    "cjm_stage": result.get("cjm_stage"),
                    "dialog_step": result.get("dialog_step") or result.get("cjm_stage"),
                    "collections": result.get("collections") or [],
                    "brands": result.get("brands") or [],
                    "sections": result.get("sections") or [],
                    "looks": result.get("looks") or [],
                    "products": result.get("products") or [],
                    "stores_context": result.get("stores_context"),
                    "stores": result.get("stores") or [],
                    "show_stores": bool(result.get("show_stores")),
                    "store_stock_context": result.get("store_stock_context"),
                    "purchase_options": result.get("purchase_options"),
                    "cta": result.get("cta"),
                    "cta_type": result.get("cta_type"),
                    "next_action": result.get("next_action"),
                    "sales_decision": result.get("sales_decision") or {},
                    "style_dna": result.get("style_dna") or {},
                    "llm_fallback": bool(result.get("llm_fallback")),
                    "llm_fallback_reason": result.get("llm_fallback_reason"),
                },
                created_at=datetime.now(timezone.utc),
            )
        except Exception as e:
            logger.exception("Stylist chat processing failed: %s", e)
            fallback_text = await _build_store_info_fallback(
                db=db,
                message=prompt_text,
                current_city=current_user.city,
            )
            assistant_message = StylistChatMessage(
                user_id=current_user.id,
                conversation_id=conversation.id,
                role="assistant",
                text=(
                    fallback_text
                    or "Я на связи и уже обрабатываю Ваш запрос. Уточню детали и дам точный ответ в следующем сообщении."
                ),
                attachments=[],
                payload={"fallback": True, "fallback_reason": "stylist_processing_error"},
                created_at=datetime.now(timezone.utc),
            )
        db.add(assistant_message)
        created_messages.append(assistant_message)

    await db.commit()
    for message in created_messages:
        await db.refresh(message)

    return StylistChatSendResponse(
        messages=[_serialize_stylist_message(message) for message in created_messages],
        ai_enabled=ai_enabled,
    )


class CustomerProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    preferred_delivery: Optional[Dict[str, Any]] = None


@router.put("/profile")
async def update_customer_profile(
    body: CustomerProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Обновление профиля покупателя"""
    if not current_user.is_customer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступно только для покупателей"
        )
    
    if body.full_name is not None:
        current_user.full_name = body.full_name
    if body.email is not None:
        current_user.email = body.email
    if body.preferred_delivery is not None:
        prefs = dict(current_user.preferences or {})
        prefs["preferred_delivery"] = body.preferred_delivery
        current_user.preferences = prefs
    
    await db.commit()
    
    return {"success": True, "message": "Профиль обновлен"}


@router.get("/purchase-history", response_model=List[PurchaseHistoryItem])
async def get_purchase_history(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """История покупок"""
    if not current_user.is_customer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступно только для покупателей"
        )
    
    stmt = select(PurchaseHistory).where(PurchaseHistory.user_id == current_user.id)
    
    # Фильтр по дате
    if from_date:
        try:
            from_dt = datetime.fromisoformat(from_date.replace("Z", "+00:00"))
            stmt = stmt.where(PurchaseHistory.purchase_date >= from_dt)
        except:
            pass
    
    if to_date:
        try:
            to_dt = datetime.fromisoformat(to_date.replace("Z", "+00:00"))
            stmt = stmt.where(PurchaseHistory.purchase_date <= to_dt)
        except:
            pass
    
    stmt = (
        stmt.outerjoin(Product, PurchaseHistory.product_id == Product.id)
        .add_columns(Product.name, Product.article, Product.brand, Product.category)
        .order_by(desc(PurchaseHistory.purchase_date))
        .limit(limit)
        .offset(offset)
    )
    
    result = await db.execute(stmt)
    rows = result.all()
    
    return [
        PurchaseHistoryItem(
            id=str(purchase.id),
            purchase_date=purchase.purchase_date.isoformat(),
            product_name=purchase.product_name or product_name,
            quantity=purchase.quantity,
            total_amount=purchase.total_amount / 100,
            category=derive_purchase_category(purchase.product_name or product_name, purchase.category or product_category),
            brand=derive_purchase_brand(purchase.product_name or product_name, purchase.brand or product_brand, product_category or purchase.category)
        )
        for purchase, product_name, product_article, product_brand, product_category in rows
    ]


@router.get("/purchase-stats", response_model=PurchaseStatsResponse)
async def get_purchase_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Статистика покупок"""
    if not current_user.is_customer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступно только для покупателей"
        )
    
    preferences = current_user.purchase_preferences or {}
    
    return PurchaseStatsResponse(
        total_purchases=current_user.total_purchases,
        total_spent=(current_user.total_spent or 0) / 100,
        average_check=(current_user.average_check / 100) if current_user.average_check else 0,
        favorite_categories=preferences.get("favorite_categories", []),
        favorite_brands=preferences.get("favorite_brands", [])
    )


@router.get("/loyalty")
async def get_loyalty_info(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Программа лояльности"""
    if not current_user.is_customer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступно только для покупателей"
        )
    
    loyalty_service = LoyaltyService(db)
    balance = await loyalty_service.get_loyalty_balance(current_user.id)
    transactions = await loyalty_service.get_loyalty_transactions(current_user.id, limit=50)
    program_info = loyalty_service.get_loyalty_program_info()
    level_progress = loyalty_service.get_loyalty_level_progress(current_user.total_spent or 0)
    
    return {
        "balance": balance,
        "transactions": [
            {
                "id": str(t.id),
                "type": t.transaction_type,
                "points": t.points,
                "balance_after": t.balance_after,
                "reason": t.reason,
                "description": t.description,
                "created_at": t.created_at.isoformat()
            }
            for t in transactions
        ],
        "program_info": program_info,
        "level_progress": level_progress
    }


@router.get("/saved-looks", response_model=List[SavedLookResponse])
async def get_saved_looks(
    save_type: Optional[str] = Query(None, description="favorite или generated"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Сохраненные образы"""
    if not current_user.is_customer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступно только для покупателей"
        )
    
    stmt = (
        select(SavedLook, Look)
        .join(Look, SavedLook.look_id == Look.id)
        .where(SavedLook.user_id == current_user.id)
    )
    
    if save_type:
        stmt = stmt.where(SavedLook.save_type == save_type)
    
    stmt = stmt.order_by(desc(SavedLook.created_at))
    
    result = await db.execute(stmt)
    rows = result.all()
    
    return [await _saved_look_response(db, saved_look, look) for saved_look, look in rows]


@router.post("/saved-looks/generated", response_model=SavedLookResponse)
async def upsert_generated_saved_look(
    request: CustomerGeneratedLookRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Создать или обновить собранный покупателем образ и сохранить его в кабинете."""
    if not current_user.is_customer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступно только для покупателей"
        )

    product_ids = _parse_product_uuid_list([item.id for item in request.products])
    if not product_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нужно выбрать хотя бы один товар"
        )

    products = (await db.execute(select(Product).where(Product.id.in_(product_ids)))).scalars().all()
    products_by_id = {product.id: product for product in products}
    missing = [str(product_id) for product_id in product_ids if product_id not in products_by_id]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Товары не найдены: {', '.join(missing)}"
        )

    look_uuid: Optional[UUID] = None
    if request.id:
        try:
            look_uuid = UUID(str(request.id))
        except Exception:
            look_uuid = None

    look: Optional[Look] = None
    if look_uuid:
        look = (
            await db.execute(
                select(Look).where(
                    and_(
                        Look.id == look_uuid,
                        Look.user_id == current_user.id,
                        Look.source_provider == "customer_builder",
                    )
                )
            )
        ).scalar_one_or_none()

    name = (request.name or "").strip() or "Мой образ GLAME"
    goal = (request.goal or "").strip() or None
    description = f"Собранный вами комплект: {goal or 'персональный стиль'}, {len(product_ids)} издел."
    selected_image_urls = [
        (item.selected_image_url or "").strip()
        for item in request.products
        if (item.selected_image_url or "").strip()
    ]
    if not selected_image_urls:
        for product_id in product_ids:
            image_url = _product_image_url(products_by_id[product_id])
            if image_url:
                selected_image_urls.append(image_url)
    image_items = [{"type": "image", "url": url, "source": "customer_builder"} for url in selected_image_urls]
    product_layout = [
        {
            "product_id": str(item.id),
            "role": item.role or ("base" if idx == 0 else "accent"),
            "position": idx + 1,
            "selected_image_urls": [item.selected_image_url] if item.selected_image_url else [],
        }
        for idx, item in enumerate(request.products)
    ]
    generation_metadata = {
        "source": "mobile_look_builder",
        "total_price": request.total_price,
        "product_count": len(product_ids),
    }

    if look is None:
        look = Look(
            name=name,
            product_ids=[str(product_id) for product_id in product_ids],
            style=goal,
            description=description,
            image_url=image_items[0]["url"] if image_items else None,
            image_urls=image_items,
            current_image_index=0 if image_items else None,
            status="customer_created",
            approval_status="customer_created",
            generation_metadata=generation_metadata,
            user_id=current_user.id,
            product_layout=product_layout,
            source_provider="customer_builder",
            is_published=False,
        )
        db.add(look)
        await db.flush()
    else:
        look.name = name
        look.product_ids = [str(product_id) for product_id in product_ids]
        look.style = goal
        look.description = description
        look.image_url = image_items[0]["url"] if image_items else None
        look.image_urls = image_items
        look.current_image_index = 0 if image_items else None
        look.status = "customer_created"
        look.approval_status = "customer_created"
        look.generation_metadata = generation_metadata
        look.product_layout = product_layout
        look.source_provider = "customer_builder"
        look.updated_at = datetime.now(timezone.utc)

    saved_look = (
        await db.execute(
            select(SavedLook).where(
                and_(
                    SavedLook.user_id == current_user.id,
                    SavedLook.look_id == look.id,
                    SavedLook.save_type == "generated",
                )
            )
        )
    ).scalar_one_or_none()

    if saved_look is None:
        saved_look = SavedLook(
            user_id=current_user.id,
            look_id=look.id,
            save_type="generated",
            notes=request.notes,
            generation_context=generation_metadata,
        )
        db.add(saved_look)
        await db.flush()
    else:
        saved_look.notes = request.notes
        saved_look.generation_context = generation_metadata
        saved_look.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(look)
    await db.refresh(saved_look)
    return await _saved_look_response(db, saved_look, look)


@router.post("/saved-looks")
async def save_look(
    look_id: str,
    save_type: str,
    notes: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Сохранить образ"""
    if not current_user.is_customer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступно только для покупателей"
        )
    
    if save_type not in ["favorite", "generated"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="save_type должен быть 'favorite' или 'generated'"
        )
    
    # Проверяем существование образа
    try:
        look_uuid = UUID(look_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный формат look_id"
        )
    
    stmt = select(Look).where(Look.id == look_uuid)
    result = await db.execute(stmt)
    look = result.scalar_one_or_none()
    
    if not look:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Образ не найден"
        )
    
    # Проверяем, не сохранен ли уже
    stmt = select(SavedLook).where(
        and_(
            SavedLook.user_id == current_user.id,
            SavedLook.look_id == look_uuid
        )
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Образ уже сохранен"
        )
    
    # Создаем сохраненный образ
    saved_look = SavedLook(
        user_id=current_user.id,
        look_id=look_uuid,
        save_type=save_type,
        notes=notes
    )
    
    db.add(saved_look)
    await db.commit()
    
    return {"success": True, "message": "Образ сохранен", "id": str(saved_look.id)}


@router.delete("/saved-looks/{saved_look_id}")
async def delete_saved_look(
    saved_look_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Удалить сохраненный образ"""
    if not current_user.is_customer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступно только для покупателей"
        )
    
    try:
        saved_look_uuid = UUID(saved_look_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный формат saved_look_id"
        )
    
    stmt = select(SavedLook).where(
        and_(
            SavedLook.id == saved_look_uuid,
            SavedLook.user_id == current_user.id
        )
    )
    result = await db.execute(stmt)
    saved_look = result.scalar_one_or_none()
    
    if not saved_look:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Сохраненный образ не найден"
        )
    
    await db.delete(saved_look)
    await db.commit()
    
    return {"success": True, "message": "Образ удален"}


@router.get("/favorite-products", response_model=List[FavoriteProductResponse])
async def get_favorite_products(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Избранные товары покупателя, синхронизированные на сервер."""
    if not current_user.is_customer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступно только для покупателей"
        )

    rows = (
        await db.execute(
            select(CustomerFavoriteProduct, Product)
            .join(Product, CustomerFavoriteProduct.product_id == Product.id)
            .where(CustomerFavoriteProduct.user_id == current_user.id)
            .order_by(desc(CustomerFavoriteProduct.created_at))
        )
    ).all()
    return [_favorite_product_response(row, product) for row, product in rows]


@router.put("/favorite-products", response_model=List[FavoriteProductResponse])
async def sync_favorite_products(
    request: FavoriteProductSyncRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Заменить серверный wishlist списком из приложения."""
    if not current_user.is_customer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступно только для покупателей"
        )

    product_ids = _parse_product_uuid_list(request.product_ids)
    existing_products = []
    if product_ids:
        existing_products = (await db.execute(select(Product.id).where(Product.id.in_(product_ids)))).scalars().all()
    existing_product_ids = set(existing_products)

    current_rows = (
        await db.execute(select(CustomerFavoriteProduct).where(CustomerFavoriteProduct.user_id == current_user.id))
    ).scalars().all()
    current_by_product = {row.product_id: row for row in current_rows}

    for row in current_rows:
        if row.product_id not in existing_product_ids:
            await db.delete(row)

    for product_id in product_ids:
        if product_id not in existing_product_ids:
            continue
        row = current_by_product.get(product_id)
        if row:
            row.source = request.source or row.source or "app"
        else:
            db.add(
                CustomerFavoriteProduct(
                    user_id=current_user.id,
                    product_id=product_id,
                    source=request.source or "app",
                )
            )

    await db.commit()
    return await get_favorite_products(current_user=current_user, db=db)


@router.post("/favorite-products/{product_id}", response_model=List[FavoriteProductResponse])
async def add_favorite_product(
    product_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Добавить товар в избранное."""
    if not current_user.is_customer:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступно только для покупателей")
    try:
        product_uuid = UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат product_id")

    product = (await db.execute(select(Product).where(Product.id == product_uuid))).scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")

    existing = (
        await db.execute(
            select(CustomerFavoriteProduct).where(
                and_(
                    CustomerFavoriteProduct.user_id == current_user.id,
                    CustomerFavoriteProduct.product_id == product_uuid,
                )
            )
        )
    ).scalar_one_or_none()
    if not existing:
        db.add(CustomerFavoriteProduct(user_id=current_user.id, product_id=product_uuid, source="app"))
        await db.commit()
    return await get_favorite_products(current_user=current_user, db=db)


@router.delete("/favorite-products/{product_id}", response_model=List[FavoriteProductResponse])
async def delete_favorite_product(
    product_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Удалить товар из избранного."""
    if not current_user.is_customer:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Доступно только для покупателей")
    try:
        product_uuid = UUID(product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат product_id")

    row = (
        await db.execute(
            select(CustomerFavoriteProduct).where(
                and_(
                    CustomerFavoriteProduct.user_id == current_user.id,
                    CustomerFavoriteProduct.product_id == product_uuid,
                )
            )
        )
    ).scalar_one_or_none()
    if row:
        await db.delete(row)
        await db.commit()
    return await get_favorite_products(current_user=current_user, db=db)
