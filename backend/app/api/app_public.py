from datetime import datetime, timezone
import re
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession
import re

from app.database.connection import get_db
from app.models.app_banner import AppBanner
from app.models.app_home_slide import AppHomeSlide
from app.models.app_lookbook import AppLookbook
from app.models.app_news import AppNews
from app.models.app_promotion import AppPromotion
from app.models.app_store import AppStore

router = APIRouter()

APP_ADMIN_MEDIA_DIR = Path("static/app_admin_media")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/gift-certificate-textures")
async def get_gift_certificate_textures():
    target_dir = APP_ADMIN_MEDIA_DIR / "certificate_texture"
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


def _excerpt(text: str, limit: int = 160) -> str:
    s = (text or "").strip()
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) <= limit:
        return s
    return s[:limit].rstrip() + "…"


def _parse_uuid(value: str, *, field: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {field}")


def _normalize_placement(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    raw = (value or "").strip().lower()
    if not raw:
        return None
    if not re.fullmatch(r"[a-z0-9_\-]{2,64}", raw):
        raise HTTPException(status_code=400, detail="Invalid placement format")
    return raw


def _slide_action_payload(value):
    return value if isinstance(value, dict) else None


def _store_slug(city: Optional[str], title: Optional[str]) -> Optional[str]:
    normalized = f"{city or ''} {title or ''}".strip().lower()
    if "ялт" in normalized:
        return "yalta"
    if "симфер" in normalized:
        return "simferopol"
    return None


def _store_image_urls(store: AppStore) -> list[str]:
    raw = store.image_urls if isinstance(store.image_urls, list) else []
    image_urls = [str(url).strip() for url in raw if str(url).strip()]
    if not image_urls and store.image_url:
        image_urls = [str(store.image_url).strip()]
    return image_urls


def _store_space_media(store: AppStore) -> dict:
    image_urls = _store_image_urls(store)
    return {
        "slug": _store_slug(store.city, store.title),
        "card_image_url": image_urls[0] if len(image_urls) > 0 else store.image_url,
        "hero_image_url": image_urls[1] if len(image_urls) > 1 else (image_urls[0] if image_urls else store.image_url),
        "gallery_image_urls": image_urls[2:5] if len(image_urls) > 2 else image_urls[:3],
    }


def _normalize_home_block_key(value: Optional[str]) -> str:
    raw = (value or "style_inside").strip().lower()
    if not raw:
        raw = "style_inside"
    if not re.fullmatch(r"[a-z0-9_\-]{2,64}", raw):
        raise HTTPException(status_code=400, detail="Invalid block_key format")
    return raw


def _normalize_status(value: Optional[str]) -> str:
    v = (value or "").strip().lower()
    if not v:
        return "published"
    if v not in {"draft", "published", "archived"}:
        raise HTTPException(status_code=400, detail="Invalid status. Allowed: draft, published, archived")
    return v


@router.get("/banners")
async def get_app_banners(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    include_inactive: bool = Query(False),
    placement: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    now = _now_utc()
    placement_norm = _normalize_placement(placement)
    stmt = select(AppBanner)

    if placement_norm:
        stmt = stmt.where(AppBanner.placement == placement_norm)

    if not include_inactive:
        stmt = stmt.where(AppBanner.is_active == True)
        stmt = stmt.where(or_(AppBanner.starts_at.is_(None), AppBanner.starts_at <= now))
        stmt = stmt.where(or_(AppBanner.ends_at.is_(None), AppBanner.ends_at >= now))

    stmt = stmt.order_by(AppBanner.sort_order.asc(), AppBanner.updated_at.desc()).offset(skip).limit(limit)
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


@router.get("/home-slides")
async def get_app_home_slides(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    include_inactive: bool = Query(False),
    block_key: Optional[str] = Query("style_inside"),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AppHomeSlide).where(
        AppHomeSlide.block_key == _normalize_home_block_key(block_key)
    )
    if not include_inactive:
        stmt = stmt.where(AppHomeSlide.is_active == True)
    stmt = stmt.order_by(AppHomeSlide.sort_order.asc(), AppHomeSlide.updated_at.desc())
    stmt = stmt.offset(skip).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(x.id),
            "block_key": x.block_key,
            "title": x.title,
            "subtitle": x.subtitle,
            "background_image_url": getattr(x, "background_image_url", None),
            "image_url": x.image_url,
            "image_action_link": getattr(x, "image_action_link", None),
            "image_action_type": getattr(x, "image_action_type", None),
            "image_action_payload": _slide_action_payload(
                getattr(x, "image_action_payload", None)
            ),
            "primary_button_text": x.primary_button_text,
            "primary_button_link": x.primary_button_link,
            "primary_button_action_type": getattr(x, "primary_button_action_type", None),
            "primary_button_action_payload": _slide_action_payload(
                getattr(x, "primary_button_action_payload", None)
            ),
            "secondary_button_text": x.secondary_button_text,
            "secondary_button_link": x.secondary_button_link,
            "secondary_button_action_type": getattr(x, "secondary_button_action_type", None),
            "secondary_button_action_payload": _slide_action_payload(
                getattr(x, "secondary_button_action_payload", None)
            ),
            "sort_order": x.sort_order,
            "is_active": x.is_active,
            "updated_at": x.updated_at.isoformat() if x.updated_at else None,
        }
        for x in rows
    ]


@router.get("/stores")
async def get_app_stores(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AppStore)
    if not include_inactive:
        stmt = stmt.where(AppStore.is_active == True)
    stmt = stmt.order_by(AppStore.sort_order.asc(), AppStore.updated_at.desc()).offset(skip).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(x.id),
            "city": x.city,
            "title": x.title,
            "address": x.address,
            "working_hours": x.working_hours,
            "phone": x.phone,
            "comment": x.comment,
            "image_url": x.image_url,
            "image_urls": _store_image_urls(x),
            "latitude": x.latitude,
            "longitude": x.longitude,
            "sort_order": x.sort_order,
            "is_active": x.is_active,
            "updated_at": x.updated_at.isoformat() if x.updated_at else None,
            **_store_space_media(x),
        }
        for x in rows
    ]


@router.get("/lookbooks")
async def get_app_lookbooks(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    include_unpublished: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AppLookbook)
    if not include_unpublished:
        stmt = stmt.where(AppLookbook.is_published == True)
    stmt = stmt.order_by(desc(AppLookbook.updated_at)).offset(skip).limit(limit)
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


@router.get("/lookbooks/{lookbook_id}")
async def get_app_lookbook(
    lookbook_id: str,
    db: AsyncSession = Depends(get_db),
):
    lid = _parse_uuid(lookbook_id, field="lookbook_id")
    item = (await db.execute(select(AppLookbook).where(AppLookbook.id == lid))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Lookbook not found")
    return {
        "id": str(item.id),
        "title": item.title,
        "cover_image_url": item.cover_image_url,
        "description": item.description,
        "items": item.items or [],
        "is_published": item.is_published,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


@router.get("/promotions")
async def get_app_promotions(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None),
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    now = _now_utc()
    stmt = select(AppPromotion)
    normalized_status = _normalize_status(status)
    stmt = stmt.where(AppPromotion.status == normalized_status)

    if active_only and normalized_status == "published":
        stmt = stmt.where(or_(AppPromotion.starts_at.is_(None), AppPromotion.starts_at <= now))
        stmt = stmt.where(or_(AppPromotion.ends_at.is_(None), AppPromotion.ends_at >= now))

    stmt = stmt.order_by(desc(AppPromotion.updated_at)).offset(skip).limit(limit)
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


@router.get("/promotions/{promotion_id}")
async def get_app_promotion(
    promotion_id: str,
    db: AsyncSession = Depends(get_db),
):
    pid = _parse_uuid(promotion_id, field="promotion_id")
    item = (await db.execute(select(AppPromotion).where(AppPromotion.id == pid))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Promotion not found")
    return {
        "id": str(item.id),
        "title": item.title,
        "banner_image_url": item.banner_image_url,
        "body": item.body,
        "starts_at": item.starts_at.isoformat() if item.starts_at else None,
        "ends_at": item.ends_at.isoformat() if item.ends_at else None,
        "status": item.status,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


@router.get("/news")
async def get_app_news(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None),
    published_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    now = _now_utc()
    stmt = select(AppNews)
    normalized_status = _normalize_status(status)
    stmt = stmt.where(AppNews.status == normalized_status)

    if published_only and normalized_status == "published":
        stmt = stmt.where(or_(AppNews.published_at.is_(None), AppNews.published_at <= now))

    stmt = stmt.order_by(desc(AppNews.published_at), desc(AppNews.updated_at)).offset(skip).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(x.id),
            "title": x.title,
            "preview_image_url": x.preview_image_url,
            "cover_image_url": x.preview_image_url,
            "excerpt": _excerpt(x.body or ""),
            "description": _excerpt(x.body or ""),
            "body": x.body,
            "published_at": x.published_at.isoformat() if x.published_at else None,
            "status": x.status,
            "updated_at": x.updated_at.isoformat() if x.updated_at else None,
        }
        for x in rows
    ]


@router.get("/news/{news_id}")
async def get_app_news_item(
    news_id: str,
    db: AsyncSession = Depends(get_db),
):
    nid = _parse_uuid(news_id, field="news_id")
    item = (await db.execute(select(AppNews).where(AppNews.id == nid))).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="News not found")
    return {
        "id": str(item.id),
        "title": item.title,
        "preview_image_url": item.preview_image_url,
        "cover_image_url": item.preview_image_url,
        "excerpt": _excerpt(item.body or ""),
        "description": _excerpt(item.body or ""),
        "body": item.body,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "status": item.status,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }
