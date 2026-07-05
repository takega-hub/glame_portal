import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
import re

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_any_role, require_content_manager, require_marketer
from app.database.connection import get_db
from app.models.user import User
from app.models.analytics_event import AnalyticsEvent
from app.models.sales_record import SalesRecord
from app.models.app_banner import AppBanner
from app.models.app_home_slide import AppHomeSlide
from app.models.app_lookbook import AppLookbook
from app.models.app_promotion import AppPromotion
from app.models.app_news import AppNews
from app.models.app_store import AppStore

logger = logging.getLogger(__name__)

router = APIRouter()


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        return dt
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid datetime format: {value}")


def _normalize_status(value: Optional[str]) -> str:
    v = (value or "draft").strip().lower()
    if v not in {"draft", "published", "archived"}:
        raise HTTPException(status_code=400, detail="Invalid status. Allowed: draft, published, archived")
    return v


def _normalize_placement(value: Optional[str]) -> str:
    raw = (value or "home_hero").strip().lower()
    if not raw:
        raw = "home_hero"
    if not re.fullmatch(r"[a-z0-9_\-]{2,64}", raw):
        raise HTTPException(status_code=400, detail="Invalid placement format")
    return raw


def _normalize_media_type(value: Optional[str]) -> str:
    v = (value or "image").strip().lower()
    if v not in {"image", "video"}:
        raise HTTPException(status_code=400, detail="Invalid media_type. Allowed: image, video")
    return v


def _normalize_home_block_key(value: Optional[str]) -> str:
    raw = (value or "style_inside").strip().lower()
    if not raw:
        raw = "style_inside"
    if not re.fullmatch(r"[a-z0-9_\-]{2,64}", raw):
        raise HTTPException(status_code=400, detail="Invalid block_key format")
    return raw


def _normalize_slide_action_type(value: Optional[str]) -> Optional[str]:
    raw = (value or "").strip().lower()
    if not raw:
        return None
    if raw not in {"catalog", "looks", "selection", "stylist", "url", "home_block"}:
        raise HTTPException(status_code=400, detail="Invalid slide action type")
    return raw


def _normalize_slide_action_payload(value: Any) -> Optional[Dict[str, Any]]:
    if value in (None, "", {}):
        return None
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail="slide action payload must be an object")
    payload: Dict[str, Any] = {}
    for key, raw in value.items():
        key_text = str(key or "").strip()
        if not key_text:
            continue
        if isinstance(raw, (str, int, float, bool)) or raw is None:
            payload[key_text] = raw
        elif isinstance(raw, list):
            payload[key_text] = [
                item
                for item in raw
                if isinstance(item, (str, int, float, bool)) or item is None
            ]
        else:
            payload[key_text] = str(raw)
    return payload or None


def _normalize_optional_button_text(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


APP_MEDIA_DIR = Path("static/app_admin_media")
APP_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
APP_MEDIA_ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
APP_MEDIA_MAX_BYTES = 15 * 1024 * 1024


def _store_slug(city: Optional[str], title: Optional[str]) -> Optional[str]:
    normalized = f"{city or ''} {title or ''}".strip().lower()
    if "ялт" in normalized:
        return "yalta"
    if "симфер" in normalized:
        return "simferopol"
    return None


def _store_space_media_payload(
    image_urls: List[str],
    *,
    city: Optional[str],
    title: Optional[str],
    image_url: Optional[str],
) -> Dict[str, Any]:
    return {
        "slug": _store_slug(city, title),
        "card_image_url": image_urls[0] if len(image_urls) > 0 else image_url,
        "hero_image_url": image_urls[1] if len(image_urls) > 1 else (image_urls[0] if image_urls else image_url),
        "gallery_image_urls": image_urls[2:5] if len(image_urls) > 2 else image_urls[:3],
    }


def _requires_space_media_validation(city: Optional[str], title: Optional[str]) -> bool:
    return _store_slug(city, title) in {"yalta", "simferopol"}


def _validate_store_space_media(
    *,
    city: Optional[str],
    title: Optional[str],
    image_urls: List[str],
) -> None:
    if not _requires_space_media_validation(city, title):
        return
    if len(image_urls) < 5:
        raise HTTPException(
            status_code=400,
            detail=(
                "Для пространств GLAME Ялта и Симферополь нужно минимум 5 фото: "
                "карточка Home, Hero пространства, Галерея main, Галерея 01, Галерея 02"
            ),
        )


@router.get("/kpi/dashboard")
async def get_app_kpi_dashboard(
    days: int = Query(30, ge=1, le=365),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: User = Depends(require_marketer()),
    db: AsyncSession = Depends(get_db),
):
    if start_date and end_date:
        start = _parse_iso_datetime(start_date)
        end = _parse_iso_datetime(end_date)
        if not start or not end:
            raise HTTPException(status_code=400, detail="start_date and end_date are required")
    else:
        end = datetime.now()
        start = end - timedelta(days=days)

    events_stmt = (
        select(AnalyticsEvent.event_type, func.count(AnalyticsEvent.id))
        .where(AnalyticsEvent.timestamp >= start, AnalyticsEvent.timestamp <= end)
        .group_by(AnalyticsEvent.event_type)
    )
    events_rows = (await db.execute(events_stmt)).all()
    events_by_type = {row[0]: int(row[1] or 0) for row in events_rows if row[0]}
    total_events = sum(events_by_type.values())

    sales_stmt = select(
        func.coalesce(func.sum(SalesRecord.revenue), 0).label("revenue"),
        func.count(SalesRecord.id).label("orders"),
    ).where(SalesRecord.sale_date >= start, SalesRecord.sale_date <= end)
    sales_row = (await db.execute(sales_stmt)).first()
    revenue = float((sales_row.revenue or 0) / 100.0) if sales_row else 0.0
    orders = int(sales_row.orders or 0) if sales_row else 0

    users_total_stmt = select(func.count(User.id))
    users_total = int((await db.execute(users_total_stmt)).scalar() or 0)
    customers_stmt = select(func.count(User.id)).where(User.is_customer == True)
    customers_total = int((await db.execute(customers_stmt)).scalar() or 0)

    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "sales": {"revenue": revenue, "orders": orders},
        "users": {"total": users_total, "customers": customers_total},
        "events": {"total": total_events, "by_type": events_by_type},
    }


@router.post("/media/upload")
async def upload_app_admin_media(
    kind: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(require_any_role(["admin", "content_manager", "ai_marketer"])),
):
    safe_kind = (kind or "").strip().lower()
    if safe_kind not in {"banner", "lookbook", "promotion", "news", "store", "home_slide", "certificate_texture"}:
        raise HTTPException(status_code=400, detail="Invalid kind")
    content_type = (file.content_type or "").lower()
    if content_type not in APP_MEDIA_ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Допускаются только изображения: JPEG, PNG, WEBP")
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Файл пустой")
    if len(file_bytes) > APP_MEDIA_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Файл превышает лимит 15 MB")

    ext = APP_MEDIA_ALLOWED_TYPES[content_type]
    target_dir = APP_MEDIA_DIR / safe_kind
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{ext}"
    target_path = target_dir / filename
    target_path.write_bytes(file_bytes)
    return {"url": f"/static/app_admin_media/{safe_kind}/{filename}"}


@router.get("/gift-certificate-textures")
async def list_gift_certificate_textures(
    current_user: User = Depends(require_any_role(["admin", "content_manager", "ai_marketer"])),
):
    target_dir = APP_MEDIA_DIR / "certificate_texture"
    if not target_dir.exists():
        return []
    rows = []
    for idx, path in enumerate(sorted(target_dir.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True)):
        if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        rows.append(
            {
                "id": path.stem,
                "title": f"Текстура {idx + 1}",
                "image_url": f"/static/app_admin_media/certificate_texture/{path.name}",
                "sort_order": idx,
                "is_active": True,
            }
        )
    return rows


def _store_payload(x: AppStore) -> Dict[str, Any]:
    image_urls = [
        str(url).strip()
        for url in (x.image_urls or [])
        if str(url).strip()
    ]
    if not image_urls and x.image_url:
        image_urls = [x.image_url]
    return {
        "id": str(x.id),
        "city": x.city,
        "title": x.title,
        "address": x.address,
        "working_hours": x.working_hours,
        "phone": x.phone,
        "comment": x.comment,
        "image_url": x.image_url,
        "image_urls": image_urls,
        "latitude": x.latitude,
        "longitude": x.longitude,
        "sort_order": x.sort_order,
        "is_active": x.is_active,
        "updated_at": x.updated_at.isoformat() if x.updated_at else None,
        **_store_space_media_payload(
            image_urls,
            city=x.city,
            title=x.title,
            image_url=x.image_url,
        ),
    }


def _normalize_store_image_urls(payload: Dict[str, Any]) -> List[str]:
    raw_items = payload.get("image_urls")
    if not isinstance(raw_items, list):
        raw_items = []
    normalized: List[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        url = str(raw or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        normalized.append(url)
    fallback = str(payload.get("image_url") or "").strip()
    if fallback and fallback not in seen:
        normalized.insert(0, fallback)
    return normalized


def _home_slide_payload(x: AppHomeSlide) -> Dict[str, Any]:
    return {
        "id": str(x.id),
        "block_key": x.block_key,
        "title": x.title,
        "subtitle": x.subtitle,
        "background_image_url": getattr(x, "background_image_url", None),
        "image_url": x.image_url,
        "image_action_link": x.image_action_link,
        "image_action_type": x.image_action_type,
        "image_action_payload": x.image_action_payload,
        "primary_button_text": x.primary_button_text,
        "primary_button_link": x.primary_button_link,
        "primary_button_action_type": x.primary_button_action_type,
        "primary_button_action_payload": x.primary_button_action_payload,
        "secondary_button_text": x.secondary_button_text,
        "secondary_button_link": x.secondary_button_link,
        "secondary_button_action_type": x.secondary_button_action_type,
        "secondary_button_action_payload": x.secondary_button_action_payload,
        "sort_order": x.sort_order,
        "is_active": x.is_active,
        "updated_at": x.updated_at.isoformat() if x.updated_at else None,
    }


@router.get("/stores")
async def list_stores(
    include_inactive: bool = Query(False),
    current_user: User = Depends(require_content_manager()),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AppStore)
    if not include_inactive:
        stmt = stmt.where(AppStore.is_active == True)
    stmt = stmt.order_by(AppStore.sort_order.asc(), AppStore.updated_at.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return [_store_payload(x) for x in rows]


@router.post("/stores")
async def create_store(
    payload: Dict[str, Any],
    current_user: User = Depends(require_content_manager()),
    db: AsyncSession = Depends(get_db),
):
    image_urls = _normalize_store_image_urls(payload)
    city = str(payload.get("city") or "").strip()
    title = str(payload.get("title") or "").strip()
    address = str(payload.get("address") or "").strip()
    if not city:
        raise HTTPException(status_code=400, detail="city is required")
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    if not address:
        raise HTTPException(status_code=400, detail="address is required")
    _validate_store_space_media(city=city, title=title, image_urls=image_urls)

    store = AppStore(
        city=city,
        title=title,
        address=address,
        working_hours=(str(payload.get("working_hours")).strip() if payload.get("working_hours") else None),
        phone=(str(payload.get("phone")).strip() if payload.get("phone") else None),
        comment=(str(payload.get("comment")).strip() if payload.get("comment") else None),
        image_url=(str(payload.get("image_url")).strip() if payload.get("image_url") else None) or (image_urls[0] if image_urls else None),
        image_urls=image_urls,
        latitude=(float(payload.get("latitude")) if payload.get("latitude") not in {None, ""} else None),
        longitude=(float(payload.get("longitude")) if payload.get("longitude") not in {None, ""} else None),
        sort_order=int(payload.get("sort_order") or 0),
        is_active=bool(payload.get("is_active", True)),
        updated_by_user_id=current_user.id,
    )
    db.add(store)
    await db.commit()
    await db.refresh(store)
    return {"id": str(store.id)}


@router.put("/stores/{store_id}")
async def update_store(
    store_id: str,
    payload: Dict[str, Any],
    current_user: User = Depends(require_content_manager()),
    db: AsyncSession = Depends(get_db),
):
    try:
        sid = UUID(store_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid store id")
    store = (await db.execute(select(AppStore).where(AppStore.id == sid))).scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")

    if payload.get("city") is not None:
        store.city = str(payload.get("city") or "").strip()
    if payload.get("title") is not None:
        store.title = str(payload.get("title") or "").strip()
    if payload.get("address") is not None:
        store.address = str(payload.get("address") or "").strip()
    if payload.get("working_hours") is not None:
        store.working_hours = (str(payload.get("working_hours")).strip() or None)
    if payload.get("phone") is not None:
        store.phone = (str(payload.get("phone")).strip() or None)
    if payload.get("comment") is not None:
        store.comment = (str(payload.get("comment")).strip() or None)
    if payload.get("image_url") is not None:
        store.image_url = (str(payload.get("image_url")).strip() or None)
    if payload.get("image_urls") is not None or payload.get("image_url") is not None:
        store.image_urls = _normalize_store_image_urls(payload)
        if not store.image_url and store.image_urls:
            store.image_url = store.image_urls[0]
    if payload.get("latitude") is not None:
        store.latitude = (float(payload.get("latitude")) if str(payload.get("latitude")).strip() else None)
    if payload.get("longitude") is not None:
        store.longitude = (float(payload.get("longitude")) if str(payload.get("longitude")).strip() else None)
    if payload.get("sort_order") is not None:
        store.sort_order = int(payload.get("sort_order") or 0)
    if payload.get("is_active") is not None:
        store.is_active = bool(payload.get("is_active"))

    if not store.city:
        raise HTTPException(status_code=400, detail="city is required")
    if not store.title:
        raise HTTPException(status_code=400, detail="title is required")
    if not store.address:
        raise HTTPException(status_code=400, detail="address is required")
    _validate_store_space_media(
        city=store.city,
        title=store.title,
        image_urls=[str(url).strip() for url in (store.image_urls or []) if str(url).strip()],
    )

    store.updated_by_user_id = current_user.id
    await db.commit()
    return {"success": True}


@router.delete("/stores/{store_id}")
async def delete_store(
    store_id: str,
    current_user: User = Depends(require_content_manager()),
    db: AsyncSession = Depends(get_db),
):
    try:
        sid = UUID(store_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid store id")
    store = (await db.execute(select(AppStore).where(AppStore.id == sid))).scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    await db.delete(store)
    await db.commit()
    return {"deleted": True}


@router.get("/banners")
async def list_banners(
    include_inactive: bool = Query(False),
    current_user: User = Depends(require_content_manager()),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AppBanner)
    if not include_inactive:
        stmt = stmt.where(AppBanner.is_active == True)
    stmt = stmt.order_by(AppBanner.sort_order.asc(), AppBanner.updated_at.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(x.id),
            "title": x.title,
            "placement": getattr(x, "placement", "home_hero"),
            "media_type": getattr(x, "media_type", "image"),
            "image_url": x.image_url,
            "video_url": getattr(x, "video_url", None),
            "link_url": x.link_url,
            "sort_order": x.sort_order,
            "is_active": x.is_active,
            "starts_at": x.starts_at.isoformat() if x.starts_at else None,
            "ends_at": x.ends_at.isoformat() if x.ends_at else None,
            "updated_at": x.updated_at.isoformat() if x.updated_at else None,
        }
        for x in rows
    ]


@router.post("/banners")
async def create_banner(
    payload: Dict[str, Any],
    current_user: User = Depends(require_content_manager()),
    db: AsyncSession = Depends(get_db),
):
    title = str(payload.get("title") or "").strip() or None
    image_url = str(payload.get("image_url") or "").strip()
    if not image_url:
        raise HTTPException(status_code=400, detail="image_url is required")
    placement = _normalize_placement(payload.get("placement"))
    media_type = _normalize_media_type(payload.get("media_type"))
    video_url = (str(payload.get("video_url")).strip() if payload.get("video_url") else None)
    if media_type == "video" and not video_url:
        raise HTTPException(status_code=400, detail="video_url is required for media_type=video")
    banner = AppBanner(
        title=title,
        placement=placement,
        media_type=media_type,
        image_url=image_url,
        video_url=video_url,
        link_url=(str(payload.get("link_url")).strip() if payload.get("link_url") else None),
        sort_order=int(payload.get("sort_order") or 0),
        is_active=bool(payload.get("is_active", True)),
        starts_at=_parse_iso_datetime(payload.get("starts_at")),
        ends_at=_parse_iso_datetime(payload.get("ends_at")),
        updated_by_user_id=current_user.id,
    )
    db.add(banner)
    await db.commit()
    await db.refresh(banner)
    return {"id": str(banner.id)}


@router.put("/banners/{banner_id}")
async def update_banner(
    banner_id: str,
    payload: Dict[str, Any],
    current_user: User = Depends(require_content_manager()),
    db: AsyncSession = Depends(get_db),
):
    try:
        bid = UUID(banner_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid banner id")
    banner = (await db.execute(select(AppBanner).where(AppBanner.id == bid))).scalar_one_or_none()
    if not banner:
        raise HTTPException(status_code=404, detail="Banner not found")
    if payload.get("title") is not None:
        banner.title = str(payload.get("title") or "").strip()
    if payload.get("placement") is not None:
        banner.placement = _normalize_placement(payload.get("placement"))
    if payload.get("media_type") is not None:
        banner.media_type = _normalize_media_type(payload.get("media_type"))
    if payload.get("image_url") is not None:
        banner.image_url = str(payload.get("image_url") or "").strip()
    if payload.get("video_url") is not None:
        banner.video_url = (str(payload.get("video_url")).strip() or None)
    if payload.get("link_url") is not None:
        banner.link_url = (str(payload.get("link_url")).strip() or None)
    if payload.get("sort_order") is not None:
        banner.sort_order = int(payload.get("sort_order") or 0)
    if payload.get("is_active") is not None:
        banner.is_active = bool(payload.get("is_active"))
    if payload.get("starts_at") is not None:
        banner.starts_at = _parse_iso_datetime(payload.get("starts_at"))
    if payload.get("ends_at") is not None:
        banner.ends_at = _parse_iso_datetime(payload.get("ends_at"))

    if getattr(banner, "media_type", "image") == "video" and not getattr(banner, "video_url", None):
        raise HTTPException(status_code=400, detail="video_url is required for media_type=video")
    banner.updated_by_user_id = current_user.id
    await db.commit()
    return {"success": True}


@router.delete("/banners/{banner_id}")
async def delete_banner(
    banner_id: str,
    current_user: User = Depends(require_content_manager()),
    db: AsyncSession = Depends(get_db),
):
    try:
        bid = UUID(banner_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid banner id")
    banner = (await db.execute(select(AppBanner).where(AppBanner.id == bid))).scalar_one_or_none()
    if not banner:
        raise HTTPException(status_code=404, detail="Banner not found")
    await db.delete(banner)
    await db.commit()
    return {"deleted": True}


@router.get("/home-slides")
async def list_home_slides(
    include_inactive: bool = Query(True),
    block_key: Optional[str] = Query("style_inside"),
    current_user: User = Depends(require_content_manager()),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AppHomeSlide).where(
        AppHomeSlide.block_key == _normalize_home_block_key(block_key)
    )
    if not include_inactive:
        stmt = stmt.where(AppHomeSlide.is_active == True)
    stmt = stmt.order_by(AppHomeSlide.sort_order.asc(), AppHomeSlide.updated_at.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return [_home_slide_payload(x) for x in rows]


@router.post("/home-slides")
async def create_home_slide(
    payload: Dict[str, Any],
    current_user: User = Depends(require_content_manager()),
    db: AsyncSession = Depends(get_db),
):
    title = str(payload.get("title") or "").strip() or None
    image_url = str(payload.get("image_url") or "").strip()
    if not image_url:
        raise HTTPException(status_code=400, detail="image_url is required")
    primary_button_text = _normalize_optional_button_text(
        payload.get("primary_button_text")
    )
    secondary_button_text = _normalize_optional_button_text(
        payload.get("secondary_button_text")
    )

    slide = AppHomeSlide(
        block_key=_normalize_home_block_key(payload.get("block_key")),
        title=title,
        subtitle=(str(payload.get("subtitle")).strip() if payload.get("subtitle") else None),
        background_image_url=(
            str(payload.get("background_image_url")).strip()
            if payload.get("background_image_url")
            else None
        ),
        image_url=image_url,
        image_action_link=(
            str(payload.get("image_action_link")).strip()
            if payload.get("image_action_link")
            else None
        ),
        image_action_type=_normalize_slide_action_type(
            payload.get("image_action_type")
        ),
        image_action_payload=_normalize_slide_action_payload(
            payload.get("image_action_payload")
        ),
        primary_button_text=primary_button_text,
        primary_button_link=(
            str(payload.get("primary_button_link")).strip()
            if payload.get("primary_button_link") and primary_button_text
            else None
        ),
        primary_button_action_type=(
            _normalize_slide_action_type(payload.get("primary_button_action_type"))
            if primary_button_text
            else None
        ),
        primary_button_action_payload=(
            _normalize_slide_action_payload(payload.get("primary_button_action_payload"))
            if primary_button_text
            else None
        ),
        secondary_button_text=secondary_button_text,
        secondary_button_link=(
            str(payload.get("secondary_button_link")).strip()
            if payload.get("secondary_button_link") and secondary_button_text
            else None
        ),
        secondary_button_action_type=(
            _normalize_slide_action_type(payload.get("secondary_button_action_type"))
            if secondary_button_text
            else None
        ),
        secondary_button_action_payload=(
            _normalize_slide_action_payload(payload.get("secondary_button_action_payload"))
            if secondary_button_text
            else None
        ),
        sort_order=int(payload.get("sort_order") or 0),
        is_active=bool(payload.get("is_active", True)),
        updated_by_user_id=current_user.id,
    )
    db.add(slide)
    await db.commit()
    await db.refresh(slide)
    return {"id": str(slide.id)}


@router.put("/home-slides/{slide_id}")
async def update_home_slide(
    slide_id: str,
    payload: Dict[str, Any],
    current_user: User = Depends(require_content_manager()),
    db: AsyncSession = Depends(get_db),
):
    try:
        sid = UUID(slide_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid home slide id")

    slide = (
        await db.execute(select(AppHomeSlide).where(AppHomeSlide.id == sid))
    ).scalar_one_or_none()
    if not slide:
        raise HTTPException(status_code=404, detail="Home slide not found")

    if payload.get("block_key") is not None:
        slide.block_key = _normalize_home_block_key(payload.get("block_key"))
    if payload.get("title") is not None:
        slide.title = str(payload.get("title") or "").strip() or None
    if payload.get("subtitle") is not None:
        slide.subtitle = str(payload.get("subtitle") or "").strip() or None
    if payload.get("background_image_url") is not None:
        slide.background_image_url = (
            str(payload.get("background_image_url") or "").strip() or None
        )
    if payload.get("image_url") is not None:
        slide.image_url = str(payload.get("image_url") or "").strip()
    if payload.get("image_action_link") is not None:
        slide.image_action_link = (
            str(payload.get("image_action_link") or "").strip() or None
        )
    if payload.get("image_action_type") is not None:
        slide.image_action_type = _normalize_slide_action_type(
            payload.get("image_action_type")
        )
    if payload.get("image_action_payload") is not None:
        slide.image_action_payload = _normalize_slide_action_payload(
            payload.get("image_action_payload")
        )
    if payload.get("primary_button_text") is not None:
        slide.primary_button_text = (
            str(payload.get("primary_button_text") or "").strip() or None
        )
    if payload.get("primary_button_link") is not None:
        slide.primary_button_link = (
            str(payload.get("primary_button_link") or "").strip() or None
        )
    if payload.get("primary_button_action_type") is not None:
        slide.primary_button_action_type = _normalize_slide_action_type(
            payload.get("primary_button_action_type")
        )
    if payload.get("primary_button_action_payload") is not None:
        slide.primary_button_action_payload = _normalize_slide_action_payload(
            payload.get("primary_button_action_payload")
        )
    if payload.get("secondary_button_text") is not None:
        slide.secondary_button_text = (
            str(payload.get("secondary_button_text") or "").strip() or None
        )
    if payload.get("secondary_button_link") is not None:
        slide.secondary_button_link = (
            str(payload.get("secondary_button_link") or "").strip() or None
        )
    if payload.get("secondary_button_action_type") is not None:
        slide.secondary_button_action_type = _normalize_slide_action_type(
            payload.get("secondary_button_action_type")
        )
    if payload.get("secondary_button_action_payload") is not None:
        slide.secondary_button_action_payload = _normalize_slide_action_payload(
            payload.get("secondary_button_action_payload")
        )
    if payload.get("sort_order") is not None:
        slide.sort_order = int(payload.get("sort_order") or 0)
    if payload.get("is_active") is not None:
        slide.is_active = bool(payload.get("is_active"))

    if not (slide.image_url or "").strip():
        raise HTTPException(status_code=400, detail="image_url is required")
    if not slide.primary_button_text:
        slide.primary_button_link = None
        slide.primary_button_action_type = None
        slide.primary_button_action_payload = None
    if not slide.secondary_button_text:
        slide.secondary_button_link = None
        slide.secondary_button_action_type = None
        slide.secondary_button_action_payload = None

    slide.updated_by_user_id = current_user.id
    await db.commit()
    return {"success": True}


@router.delete("/home-slides/{slide_id}")
async def delete_home_slide(
    slide_id: str,
    current_user: User = Depends(require_content_manager()),
    db: AsyncSession = Depends(get_db),
):
    try:
        sid = UUID(slide_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid home slide id")

    slide = (
        await db.execute(select(AppHomeSlide).where(AppHomeSlide.id == sid))
    ).scalar_one_or_none()
    if not slide:
        raise HTTPException(status_code=404, detail="Home slide not found")
    await db.delete(slide)
    await db.commit()
    return {"deleted": True}


@router.get("/lookbooks")
async def list_lookbooks(
    include_unpublished: bool = Query(True),
    current_user: User = Depends(require_content_manager()),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AppLookbook)
    if not include_unpublished:
        stmt = stmt.where(AppLookbook.is_published == True)
    stmt = stmt.order_by(desc(AppLookbook.updated_at))
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(x.id),
            "title": x.title,
            "cover_image_url": x.cover_image_url,
            "description": x.description,
            "items": x.items or [],
            "is_published": x.is_published,
            "updated_at": x.updated_at.isoformat() if x.updated_at else None,
        }
        for x in rows
    ]


@router.post("/lookbooks")
async def create_lookbook(
    payload: Dict[str, Any],
    current_user: User = Depends(require_content_manager()),
    db: AsyncSession = Depends(get_db),
):
    title = str(payload.get("title") or "").strip()
    cover_image_url = str(payload.get("cover_image_url") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    if not cover_image_url:
        raise HTTPException(status_code=400, detail="cover_image_url is required")
    items = payload.get("items")
    if items is None:
        items = []
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="items must be a list")

    lookbook = AppLookbook(
        title=title,
        cover_image_url=cover_image_url,
        description=(str(payload.get("description")).strip() if payload.get("description") else None),
        items=items,
        is_published=bool(payload.get("is_published", False)),
        updated_by_user_id=current_user.id,
    )
    db.add(lookbook)
    await db.commit()
    await db.refresh(lookbook)
    return {"id": str(lookbook.id)}


@router.put("/lookbooks/{lookbook_id}")
async def update_lookbook(
    lookbook_id: str,
    payload: Dict[str, Any],
    current_user: User = Depends(require_content_manager()),
    db: AsyncSession = Depends(get_db),
):
    try:
        lid = UUID(lookbook_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid lookbook id")
    lookbook = (await db.execute(select(AppLookbook).where(AppLookbook.id == lid))).scalar_one_or_none()
    if not lookbook:
        raise HTTPException(status_code=404, detail="Lookbook not found")

    if payload.get("title") is not None:
        lookbook.title = str(payload.get("title") or "").strip()
    if payload.get("cover_image_url") is not None:
        lookbook.cover_image_url = str(payload.get("cover_image_url") or "").strip()
    if payload.get("description") is not None:
        lookbook.description = (str(payload.get("description")).strip() or None)
    if payload.get("items") is not None:
        items = payload.get("items")
        if not isinstance(items, list):
            raise HTTPException(status_code=400, detail="items must be a list")
        lookbook.items = items
    if payload.get("is_published") is not None:
        lookbook.is_published = bool(payload.get("is_published"))
    lookbook.updated_by_user_id = current_user.id
    await db.commit()
    return {"success": True}


@router.delete("/lookbooks/{lookbook_id}")
async def delete_lookbook(
    lookbook_id: str,
    current_user: User = Depends(require_content_manager()),
    db: AsyncSession = Depends(get_db),
):
    try:
        lid = UUID(lookbook_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid lookbook id")
    lookbook = (await db.execute(select(AppLookbook).where(AppLookbook.id == lid))).scalar_one_or_none()
    if not lookbook:
        raise HTTPException(status_code=404, detail="Lookbook not found")
    await db.delete(lookbook)
    await db.commit()
    return {"deleted": True}


@router.get("/promotions")
async def list_promotions(
    status: Optional[str] = Query(None),
    current_user: User = Depends(require_marketer()),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AppPromotion)
    if status:
        stmt = stmt.where(AppPromotion.status == _normalize_status(status))
    stmt = stmt.order_by(desc(AppPromotion.updated_at))
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(x.id),
            "title": x.title,
            "banner_image_url": x.banner_image_url,
            "body": x.body,
            "starts_at": x.starts_at.isoformat() if x.starts_at else None,
            "ends_at": x.ends_at.isoformat() if x.ends_at else None,
            "status": x.status,
            "updated_at": x.updated_at.isoformat() if x.updated_at else None,
        }
        for x in rows
    ]


@router.post("/promotions")
async def create_promotion(
    payload: Dict[str, Any],
    current_user: User = Depends(require_marketer()),
    db: AsyncSession = Depends(get_db),
):
    title = str(payload.get("title") or "").strip()
    body = str(payload.get("body") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    if not body:
        raise HTTPException(status_code=400, detail="body is required")
    promo = AppPromotion(
        title=title,
        banner_image_url=(str(payload.get("banner_image_url")).strip() if payload.get("banner_image_url") else None),
        body=body,
        starts_at=_parse_iso_datetime(payload.get("starts_at")),
        ends_at=_parse_iso_datetime(payload.get("ends_at")),
        status=_normalize_status(payload.get("status")),
        updated_by_user_id=current_user.id,
    )
    db.add(promo)
    await db.commit()
    await db.refresh(promo)
    return {"id": str(promo.id)}


@router.put("/promotions/{promotion_id}")
async def update_promotion(
    promotion_id: str,
    payload: Dict[str, Any],
    current_user: User = Depends(require_marketer()),
    db: AsyncSession = Depends(get_db),
):
    try:
        pid = UUID(promotion_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid promotion id")
    promo = (await db.execute(select(AppPromotion).where(AppPromotion.id == pid))).scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=404, detail="Promotion not found")
    if payload.get("title") is not None:
        promo.title = str(payload.get("title") or "").strip()
    if payload.get("banner_image_url") is not None:
        promo.banner_image_url = (str(payload.get("banner_image_url")).strip() or None)
    if payload.get("body") is not None:
        promo.body = str(payload.get("body") or "").strip()
    if payload.get("starts_at") is not None:
        promo.starts_at = _parse_iso_datetime(payload.get("starts_at"))
    if payload.get("ends_at") is not None:
        promo.ends_at = _parse_iso_datetime(payload.get("ends_at"))
    if payload.get("status") is not None:
        promo.status = _normalize_status(payload.get("status"))
    promo.updated_by_user_id = current_user.id
    await db.commit()
    return {"success": True}


@router.delete("/promotions/{promotion_id}")
async def delete_promotion(
    promotion_id: str,
    current_user: User = Depends(require_marketer()),
    db: AsyncSession = Depends(get_db),
):
    try:
        pid = UUID(promotion_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid promotion id")
    promo = (await db.execute(select(AppPromotion).where(AppPromotion.id == pid))).scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=404, detail="Promotion not found")
    await db.delete(promo)
    await db.commit()
    return {"deleted": True}


@router.get("/news")
async def list_news(
    status: Optional[str] = Query(None),
    current_user: User = Depends(require_marketer()),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AppNews)
    if status:
        stmt = stmt.where(AppNews.status == _normalize_status(status))
    stmt = stmt.order_by(desc(AppNews.updated_at))
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(x.id),
            "title": x.title,
            "preview_image_url": x.preview_image_url,
            "body": x.body,
            "published_at": x.published_at.isoformat() if x.published_at else None,
            "status": x.status,
            "updated_at": x.updated_at.isoformat() if x.updated_at else None,
        }
        for x in rows
    ]


@router.post("/news")
async def create_news(
    payload: Dict[str, Any],
    current_user: User = Depends(require_marketer()),
    db: AsyncSession = Depends(get_db),
):
    title = str(payload.get("title") or "").strip()
    body = str(payload.get("body") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    if not body:
        raise HTTPException(status_code=400, detail="body is required")
    published_at = _parse_iso_datetime(payload.get("published_at"))
    status = _normalize_status(payload.get("status"))
    if status == "published" and published_at is None:
        published_at = datetime.now(timezone.utc)

    item = AppNews(
        title=title,
        preview_image_url=(str(payload.get("preview_image_url")).strip() if payload.get("preview_image_url") else None),
        body=body,
        published_at=published_at,
        status=status,
        updated_by_user_id=current_user.id,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return {"id": str(item.id)}


@router.put("/news/{news_id}")
async def update_news(
    news_id: str,
    payload: Dict[str, Any],
    current_user: User = Depends(require_marketer()),
    db: AsyncSession = Depends(get_db),
):
    try:
        nid = UUID(news_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid news id")
    item = (await db.execute(select(AppNews).where(AppNews.id == nid))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="News not found")
    if payload.get("title") is not None:
        item.title = str(payload.get("title") or "").strip()
    if payload.get("preview_image_url") is not None:
        item.preview_image_url = (str(payload.get("preview_image_url")).strip() or None)
    if payload.get("body") is not None:
        item.body = str(payload.get("body") or "").strip()
    if payload.get("published_at") is not None:
        item.published_at = _parse_iso_datetime(payload.get("published_at"))
    if payload.get("status") is not None:
        item.status = _normalize_status(payload.get("status"))
        if item.status == "published" and item.published_at is None:
            item.published_at = datetime.now(timezone.utc)
    item.updated_by_user_id = current_user.id
    await db.commit()
    return {"success": True}


@router.delete("/news/{news_id}")
async def delete_news(
    news_id: str,
    current_user: User = Depends(require_marketer()),
    db: AsyncSession = Depends(get_db),
):
    try:
        nid = UUID(news_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid news id")
    item = (await db.execute(select(AppNews).where(AppNews.id == nid))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="News not found")
    await db.delete(item)
    await db.commit()
    return {"deleted": True}
