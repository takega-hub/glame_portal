from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, desc, func, or_, select, text
from pydantic import BaseModel
from typing import List, Optional, Any
from uuid import UUID, uuid4
from datetime import datetime
import logging
import asyncio
import time
import re
import json
from pathlib import Path
from urllib.parse import unquote

from app.database.connection import get_db, AsyncSessionLocal
from app.api.auth import get_current_user, get_current_user_optional
from app.api.dependencies import require_any_role
from app.models.look import Look
from app.models.look_reaction import LookReaction
from app.models.saved_look import SavedLook
from app.models.content_item import ContentItem
from app.models.product import Product
from app.models.app_setting import AppSetting
from app.models.agent_system_prompt import AgentSystemPrompt
from app.models.user import User
from app.services.instagram_service import InstagramService
from app.services.llm_service import llm_service
from app.agents.stylist_agent import StylistAgent

logger = logging.getLogger(__name__)

router = APIRouter()


class LookResponse(BaseModel):
    id: str
    name: str
    product_ids: List[str]
    style: str | None = None
    mood: str | None = None
    style_values: List[str] = []
    mood_values: List[str] = []
    style_dna: str | None = None
    radical: str | None = None
    style_dna_values: List[str] = []
    radical_values: List[str] = []
    description: str | None = None
    image_url: str | None = None
    image_urls: List[Any] = []
    current_image_index: int | None = None
    status: str | None = None
    approval_status: str | None = None
    try_on_image_url: str | None = None
    generation_metadata: dict = {}
    caption: str | None = None
    media_items: List[dict] = []
    product_layout: List[dict] = []
    source_provider: str | None = None
    source_media_id: str | None = None
    source_permalink: str | None = None
    is_published: bool = False
    is_new: bool = False
    published_at: str | None = None
    like_count: int = 0
    favorite_count: int = 0


class LookGenerateRequest(BaseModel):
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    style: Optional[str] = None
    mood: Optional[str] = None
    persona: Optional[str] = None
    user_request: Optional[str] = None
    generate_image: bool = True
    use_default_model: bool = False
    digital_model: Optional[str] = None


class DigitalModelInfo(BaseModel):
    id: str
    name: str
    source_images: List[str]
    source_images_count: int
    portfolio_images_count: int
    portfolio_images: List[str]


def _sanitize_model_name(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = re.sub(r"[^a-zA-Z0-9_\- ]+", "", str(value)).strip()
    if not cleaned:
        return None
    return re.sub(r"\s+", "_", cleaned).lower()


def _static_roots() -> List[Path]:
    """
    Возвращает существующие корни static для разных вариантов cwd:
    - ./static            (когда backend запущен из backend/)
    - ./backend/static    (когда backend запущен из repo root)
    - <repo>/backend/static (по пути от текущего файла)
    """
    candidate_roots = [
        Path("static"),
        Path("backend/static"),
        Path(__file__).resolve().parents[2] / "static",
    ]
    roots: List[Path] = []
    seen: set[str] = set()
    for root in candidate_roots:
        try:
            resolved = root.resolve()
        except Exception:
            continue
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        if resolved.exists() and resolved.is_dir():
            roots.append(resolved)
    return roots


def _first_existing_static_subdir(relative_subdir: str) -> Optional[Path]:
    rel = relative_subdir.strip().strip("/").replace("\\", "/")
    for root in _static_roots():
        candidate = root / rel
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def _iter_existing_static_subdirs(relative_subdir: str) -> List[Path]:
    rel = relative_subdir.strip().strip("/").replace("\\", "/")
    subdirs: List[Path] = []
    for root in _static_roots():
        candidate = root / rel
        if candidate.exists() and candidate.is_dir():
            subdirs.append(candidate)
    return subdirs


LOOK_MANUAL_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

LOOK_MANUAL_VIDEO_TYPES = {
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
}

LOOK_MANUAL_IMAGE_MAX_BYTES = 15 * 1024 * 1024
LOOK_MANUAL_VIDEO_MAX_BYTES = 100 * 1024 * 1024
MANUAL_LOOK_COPY_AGENT_TYPE = "manual-look-copywriter"
REAL_SHOOT_MODEL_ID = "real_shoot"
REAL_SHOOT_MODEL_NAME = "Реальная съемка"
MANUAL_LOOK_OPTION_DEFAULTS = {
    "manual_look_style_options": [],
    "manual_look_mood_options": [],
    "manual_look_style_dna_options": [],
    "manual_look_radical_options": [],
}
MANUAL_LOOK_COPY_FALLBACK_PROMPT = """Ты fashion-редактор и стилист бренда GLAME.

Твоя задача: по данным товаров, их описаниям и параметрам образа придумать:
1. Короткое выразительное название образа.
2. Живое и продающее описание образа.

Правила:
- Используй только факты и характеристики, которые можно обосновать данными товаров и параметрами образа.
- Сохраняй tone of voice GLAME: премиально, тепло, современно, без пафоса.
- Название: 2-5 слов, без кавычек, без эмодзи.
- Описание: 2-4 коротких абзаца или 3-5 предложений.
- Обязательно опирайся на стиль, настроение, стилевой ДНК и радикал, если они переданы.
- Используй описания товаров как основу для образа: материалы, формы, акценты, настроение, способ сочетания.
- Не выдумывай характеристики, которых нет в товарных данных.
- Не перечисляй товары сухим списком. Сначала опиши идею образа, затем как украшения работают вместе.
- Верни только JSON вида {"name":"...", "description":"..."}.
"""


def _preferred_static_root() -> Path:
    roots = _static_roots()
    if roots:
        return roots[0]
    fallback = Path(__file__).resolve().parents[2] / "static"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


async def _save_manual_look_upload(file: UploadFile, folder: str, allowed_types: dict[str, str], max_bytes: int) -> str:
    content_type = (file.content_type or "").lower()
    if content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Недопустимый тип файла для ручного образа")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Один из файлов пустой")
    if len(file_bytes) > max_bytes:
        raise HTTPException(status_code=400, detail="Файл превышает допустимый размер")

    target_dir = _preferred_static_root() / "look_images" / folder
    target_dir.mkdir(parents=True, exist_ok=True)

    ext = allowed_types[content_type]
    filename = f"{uuid4().hex}{ext}"
    target_path = target_dir / filename
    target_path.write_bytes(file_bytes)
    return f"/static/look_images/{folder}/{filename}"


async def _ensure_app_settings_table(session: AsyncSession) -> None:
    await session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
              key VARCHAR(100) PRIMARY KEY,
              value VARCHAR(500) NOT NULL,
              updated_at TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
    )
    await session.commit()


def _normalized_option_values(values: List[str]) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for item in values:
        value = str(item or "").strip()
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _normalize_multi_values(values: Any, fallback_single: Optional[str] = None) -> List[str]:
    raw_items: List[str] = []
    if isinstance(values, list):
        raw_items = [str(item) for item in values]
    elif isinstance(values, str):
        raw_items = [part.strip() for part in values.split(",")]
    elif values is not None:
        raw_items = [str(values)]
    if fallback_single:
        raw_items.append(str(fallback_single))
    return _normalized_option_values(raw_items)


def _primary_multi_value(values: List[str], fallback_single: Optional[str] = None) -> Optional[str]:
    normalized = _normalize_multi_values(values, fallback_single)
    return normalized[0] if normalized else None


async def _get_setting_list(db: AsyncSession, key: str, default: List[str]) -> List[str]:
    await _ensure_app_settings_table(db)
    row = (await db.execute(select(AppSetting).where(AppSetting.key == key))).scalar_one_or_none()
    if not row or not row.value:
        return _normalized_option_values(default)
    try:
        parsed = json.loads(row.value)
        if isinstance(parsed, list):
            return _normalized_option_values([str(item) for item in parsed])
    except Exception:
        pass
    return _normalized_option_values(default)


async def _append_setting_list_value(db: AsyncSession, key: str, value: Optional[str], default: List[str]) -> None:
    clean_value = str(value or "").strip()
    if not clean_value:
        return
    current = await _get_setting_list(db, key, default)
    normalized = {item.casefold() for item in current}
    if clean_value.casefold() in normalized:
        return
    updated = current + [clean_value]
    row = (await db.execute(select(AppSetting).where(AppSetting.key == key))).scalar_one_or_none()
    payload = json.dumps(updated, ensure_ascii=True)
    if row:
        row.value = payload
    else:
        db.add(AppSetting(key=key, value=payload))


async def _append_setting_list_values(db: AsyncSession, key: str, values: List[str], default: List[str]) -> None:
    for value in _normalize_multi_values(values):
        await _append_setting_list_value(db, key, value, default)


async def _get_active_prompt_text(db: AsyncSession, agent_type: str, fallback_prompt: str) -> str:
    try:
        result = await db.execute(
            select(AgentSystemPrompt).where(
                AgentSystemPrompt.agent_type == agent_type,
                AgentSystemPrompt.is_active == True,
            )
        )
        prompt_obj = result.scalar_one_or_none()
        if prompt_obj and prompt_obj.system_prompt:
            return str(prompt_obj.system_prompt)
    except Exception as e:
        logger.warning("Не удалось получить активный системный промпт для %s: %s", agent_type, e)
    return fallback_prompt


def _product_text_for_manual_look(product: Product) -> str:
    tags = ", ".join(product.tags or []) if isinstance(product.tags, list) and product.tags else "—"
    specs = product.specifications if isinstance(product.specifications, dict) else {}
    specs_chunks = []
    for key, value in list(specs.items())[:8]:
        if value in (None, "", [], {}):
            continue
        specs_chunks.append(f"{key}: {value}")
    specs_text = "; ".join(specs_chunks) if specs_chunks else "—"
    return (
        f"Товар: {product.name}\n"
        f"Бренд: {product.brand or 'GLAME'}\n"
        f"Категория: {product.category or '—'}\n"
        f"Артикул: {getattr(product, 'article', None) or getattr(product, 'external_code', None) or '—'}\n"
        f"Теги: {tags}\n"
        f"Краткое описание: {product.description or '—'}\n"
        f"Полное описание: {getattr(product, 'full_description', None) or '—'}\n"
        f"Характеристики: {specs_text}"
    )


def _collect_real_shoot_portfolio_images(looks: List[Look]) -> List[str]:
    urls: List[str] = []
    seen: set[str] = set()

    def add_url(url: Optional[str]) -> None:
        normalized = _normalize_portfolio_url(url)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        urls.append(normalized)

    for look in looks:
        if (look.source_provider or "").strip().lower() != REAL_SHOOT_MODEL_ID:
            continue
        if isinstance(look.image_urls, list):
            for image_data in look.image_urls:
                if isinstance(image_data, dict):
                    add_url(image_data.get("url"))
                else:
                    add_url(str(image_data))
        add_url(look.image_url)
    return urls


def _discover_digital_models() -> List[dict]:
    models_root = _first_existing_static_subdir("models")
    if not models_root:
        return []

    exts = {".jpg", ".jpeg", ".png", ".webp"}
    model_dirs = sorted([p for p in models_root.iterdir() if p.is_dir()], key=lambda p: p.name.lower())
    models: List[dict] = []

    for model_dir in model_dirs:
        files = sorted(
            [p for p in model_dir.iterdir() if p.is_file() and p.suffix.lower() in exts],
            key=lambda p: p.name.lower(),
        )
        models.append(
            {
                "id": model_dir.name,
                "name": model_dir.name.replace("_", " "),
                "source_images": [f"/static/models/{model_dir.name}/{f.name}" for f in files],
                "source_images_count": len(files),
            }
        )

    if models:
        return models

    # Backward compatibility: если изображения лежат прямо в static/models
    root_files = sorted(
        [p for p in models_root.iterdir() if p.is_file() and p.suffix.lower() in exts],
        key=lambda p: p.name.lower(),
    )
    if root_files:
        return [
            {
                "id": "default",
                "name": "default",
                "source_images": [f"/static/models/{f.name}" for f in root_files],
                "source_images_count": len(root_files),
            }
        ]

    return []


def _collect_portfolio_images_for_model(model_id: str, looks: List[Look], content_items: List[ContentItem]) -> List[str]:
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    model_norm = _sanitize_model_name(model_id) or ""
    urls: List[str] = []
    seen: set[str] = set()

    def add_url(url: Optional[str]):
        if not url:
            return
        normalized = str(url).strip()
        if not normalized:
            return
        if normalized.startswith("/static/lcimages/"):
            normalized = normalized.replace("/static/lcimages/", "/static/look_images/")
        if normalized not in seen:
            seen.add(normalized)
            urls.append(normalized)

    # 1) Из образов (Look): явная привязка по generation_metadata.digital_model
    for look in looks:
        metadata = look.generation_metadata or {}
        look_model = _sanitize_model_name(metadata.get("digital_model"))
        if look_model != model_norm:
            continue
        if isinstance(look.image_urls, list):
            for image_data in look.image_urls:
                if isinstance(image_data, dict):
                    add_url(image_data.get("url"))
                else:
                    add_url(str(image_data))
        add_url(look.image_url)

    # 2) Из content_items: по spec.media_task.model_profile / persona_type
    for item in content_items:
        spec = item.spec if isinstance(item.spec, dict) else {}
        media_task = spec.get("media_task") if isinstance(spec.get("media_task"), dict) else {}
        profile = _sanitize_model_name(
            media_task.get("model_id")
            or media_task.get("model_profile")
            or media_task.get("persona_type")
            or item.persona
        )
        if profile != model_norm:
            continue
        generated = item.generated if isinstance(item.generated, dict) else {}
        media = generated.get("media") if isinstance(generated.get("media"), dict) else {}
        media_items = media.get("items") if isinstance(media.get("items"), list) else []
        for media_item in media_items:
            if isinstance(media_item, dict):
                add_url(media_item.get("url"))

    # 3) Из файлов (fallback): по имени файла, если в нем встречается model_id
    for look_model_root in _iter_existing_static_subdirs(f"look_images/models/{model_norm}"):
        for file_path in sorted(look_model_root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if file_path.is_file() and file_path.suffix.lower() in exts:
                add_url(f"/static/look_images/models/{model_norm}/{file_path.name}")

    for look_images_dir in _iter_existing_static_subdirs("look_images"):
        for file_path in sorted(look_images_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not file_path.is_file() or file_path.suffix.lower() not in exts:
                continue
            stem_norm = _sanitize_model_name(file_path.stem) or ""
            if model_norm and model_norm in stem_norm:
                add_url(f"/static/look_images/{file_path.name}")

    for content_images_dir in _iter_existing_static_subdirs("content_post_images"):
        for file_path in sorted(content_images_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not file_path.is_file() or file_path.suffix.lower() not in exts:
                continue
            stem_norm = _sanitize_model_name(file_path.stem) or ""
            # Явно поддерживаем формат post_<model_id>_... для привязки к портфолио модели.
            file_name_lower = file_path.name.lower()
            has_model_prefix = bool(model_norm and file_name_lower.startswith(f"post_{model_norm}_"))
            if model_norm and (model_norm in stem_norm or has_model_prefix):
                add_url(f"/static/content_post_images/{file_path.name}")

    return urls


def _normalize_portfolio_url(url: Optional[str]) -> str:
    """Нормализация URL изображений портфолио к /static/... формату."""
    if not url:
        return ""
    normalized = unquote(str(url).strip())
    if not normalized:
        return ""
    if normalized.startswith("/static/lcimages/"):
        normalized = normalized.replace("/static/lcimages/", "/static/look_images/")
    if normalized.startswith("look_images/"):
        normalized = f"/{normalized}"
    if normalized.startswith("/look_images/"):
        normalized = normalized.replace("/look_images/", "/static/look_images/", 1)
    if normalized.startswith("/content_post_images/"):
        normalized = normalized.replace("/content_post_images/", "/static/content_post_images/", 1)
    return normalized


def _resolve_static_path_from_url(url: str) -> Optional[Path]:
    """Преобразует URL /static/... в локальный путь static/... с защитой от path traversal."""
    normalized = _normalize_portfolio_url(url)
    if not normalized.startswith("/static/"):
        return None
    rel_path = normalized.removeprefix("/static/").lstrip("/")
    for base in _static_roots():
        try:
            target = (base / rel_path).resolve()
        except Exception:
            continue
        if str(target).startswith(str(base)):
            return target
    return None


def _portfolio_urls_equal(a: Optional[str], b: Optional[str]) -> bool:
    return _normalize_portfolio_url(a) == _normalize_portfolio_url(b)


async def _ensure_look_has_catalog_products(
    db: AsyncSession,
    look: Look,
    require_image_refs: bool = False,
) -> None:
    """
    Гарантирует, что у образа есть товары из каталога.
    Если product_ids пустой — подбираем 3-5 активных товаров и сохраняем в look.
    """
    if look.product_ids and len(look.product_ids) > 0:
        # Если ID уже есть — проверяем, что такие товары реально существуют в каталоге.
        existing_ids: List[UUID] = []
        for pid in look.product_ids:
            try:
                existing_ids.append(UUID(str(pid)))
            except (ValueError, TypeError):
                continue
        if existing_ids:
            existing_products_result = await db.execute(select(Product).where(Product.id.in_(existing_ids)))
            existing_products = list(existing_products_result.scalars().all())
            if existing_products:
                if not require_image_refs:
                    return
                has_image_refs = any(
                    isinstance(p.images, list) and any(isinstance(img, str) and img.strip() for img in p.images)
                    for p in existing_products
                )
                if has_image_refs:
                    return

    stylist_agent = StylistAgent(db)
    rec = stylist_agent.recommendation_service
    metadata = look.generation_metadata or {}
    persona = metadata.get("persona")

    # Сначала пробуем осмысленный текстовый подбор по описанию/стилю/настроению.
    query_text = " ".join(
        [part for part in [look.style or "", look.mood or "", look.description or "", look.name or ""] if part]
    ).strip()
    products = await rec.search_products(
        query_text=query_text or "украшения",
        limit=5,
        only_active=True,
        require_images=True,
    )

    # Если текстовый поиск дал мало результатов — добираем из общего каталога.
    if len(products) < 3:
        fallback_products = await rec.recommend_products(
            persona=persona,
            limit=5,
            randomize=True,
            require_images=True,
        )
        existing_ids = {p.id for p in products}
        for p in fallback_products:
            if p.id not in existing_ids:
                products.append(p)
            if len(products) >= 5:
                break

    if not products:
        return

    look.product_ids = [str(p.id) for p in products[:5]]
    await db.commit()
    await db.refresh(look)


class LookTryOnRequest(BaseModel):
    user_id: Optional[str] = None


class LookUpdateRequest(BaseModel):
    name: Optional[str] = None
    style: Optional[str] = None
    mood: Optional[str] = None
    style_values: Optional[List[str]] = None
    mood_values: Optional[List[str]] = None
    style_dna: Optional[str] = None
    radical: Optional[str] = None
    style_dna_values: Optional[List[str]] = None
    radical_values: Optional[List[str]] = None
    description: Optional[str] = None
    product_ids: Optional[List[str]] = None
    product_layout: Optional[List[dict]] = None
    is_new: Optional[bool] = None
    regenerate_image: bool = False
    use_default_model: bool = False


class LookPublishRequest(BaseModel):
    is_published: bool


class LookImportRequest(BaseModel):
    instagram_media_id: str
    name: Optional[str] = None
    product_ids: List[str] = []
    product_layout: List[dict] = []
    publish: bool = False


class ManualLookCopyRequest(BaseModel):
    product_ids: List[str] = []
    style: Optional[str] = None
    mood: Optional[str] = None
    style_values: List[str] = []
    mood_values: List[str] = []
    style_dna: Optional[str] = None
    radical: Optional[str] = None
    style_dna_values: List[str] = []
    radical_values: List[str] = []
    source_provider: Optional[str] = None
    current_name: Optional[str] = None
    current_description: Optional[str] = None


def _look_multi_value_payload(look: Look, field_name: str) -> List[str]:
    values = getattr(look, field_name, None)
    fallback_map = {
        "style_values": getattr(look, "style", None),
        "mood_values": getattr(look, "mood", None),
        "style_dna_values": getattr(look, "style_dna", None),
        "radical_values": getattr(look, "radical", None),
    }
    return _normalize_multi_values(values if isinstance(values, list) else [], fallback_map.get(field_name))


def _look_media_items(look: Look) -> List[dict]:
    if isinstance(look.media_items, list) and look.media_items:
        return look.media_items

    media_items: List[dict] = []
    image_urls = look.image_urls if isinstance(look.image_urls, list) else []
    for image_data in image_urls:
        url = image_data.get("url") if isinstance(image_data, dict) else str(image_data)
        if url:
            media_items.append({"type": "image", "url": url, "source": "look"})
    if not media_items and look.image_url:
        media_items.append({"type": "image", "url": look.image_url, "source": "look"})
    if not media_items and look.try_on_image_url:
        media_items.append({"type": "image", "url": look.try_on_image_url, "source": "try_on"})
    return media_items


def _normalize_look_image_items(image_urls: Any) -> List[dict]:
    items: List[dict] = []
    for raw_item in image_urls or []:
        if isinstance(raw_item, dict):
            url = str(raw_item.get("url") or "").strip()
            if not url:
                continue
            item = dict(raw_item)
            item["url"] = url
            item.setdefault("type", "image")
            item.setdefault("source", "look")
            items.append(item)
        else:
            url = str(raw_item or "").strip()
            if url:
                items.append({"type": "image", "url": url, "source": "look"})
    return items


def _gallery_image_items_from_product_layout(product_layout: Any) -> List[dict]:
    items: List[dict] = []
    seen: set[str] = set()
    for raw_item in product_layout or []:
        if not isinstance(raw_item, dict):
            continue
        for raw_url in raw_item.get("selected_image_urls") or []:
            url = str(raw_url or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            items.append({"type": "image", "url": url, "source": "product_gallery"})
    return items


def _ordered_image_items(image_items: List[dict], ordered_image_urls: Optional[List[str]] = None) -> List[dict]:
    normalized_order = [str(url or "").strip() for url in (ordered_image_urls or []) if str(url or "").strip()]
    if not normalized_order:
        return image_items
    order_map = {url: idx for idx, url in enumerate(normalized_order)}
    indexed_items = list(enumerate(image_items))
    indexed_items.sort(key=lambda pair: (order_map.get(str(pair[1].get("url") or "").strip(), 10**9), pair[0]))
    return [item for _, item in indexed_items]


def _sync_look_media_items(
    look: Look,
    *,
    non_gallery_image_items: Optional[List[dict]] = None,
    video_items: Optional[List[dict]] = None,
    preferred_main_image_url: Optional[str] = None,
    ordered_image_urls: Optional[List[str]] = None,
) -> None:
    current_image_items = _normalize_look_image_items(look.image_urls or [])
    current_media_items = _look_media_items(look)

    if non_gallery_image_items is None:
        non_gallery_image_items = [
            item
            for item in current_image_items
            if str(item.get("source") or "").strip().lower() != "product_gallery"
        ]
    else:
        non_gallery_image_items = _normalize_look_image_items(non_gallery_image_items)

    if video_items is None:
        normalized_videos: List[dict] = []
        for raw_item in current_media_items:
            if not isinstance(raw_item, dict):
                continue
            if str(raw_item.get("type") or "").strip().lower() != "video":
                continue
            url = str(raw_item.get("url") or "").strip()
            if not url:
                continue
            item = dict(raw_item)
            item["url"] = url
            item["type"] = "video"
            item.setdefault("source", "manual_upload")
            normalized_videos.append(item)
        video_items = normalized_videos

    gallery_image_items = _gallery_image_items_from_product_layout(look.product_layout)
    final_image_items = _ordered_image_items(non_gallery_image_items + gallery_image_items, ordered_image_urls)
    final_media_items = final_image_items + list(video_items or [])

    previous_current_url = None
    if current_image_items:
        current_idx = look.current_image_index if look.current_image_index is not None else 0
        if 0 <= current_idx < len(current_image_items):
            previous_current_url = current_image_items[current_idx].get("url")

    look.image_urls = final_image_items
    look.media_items = final_media_items

    main_url = (preferred_main_image_url or "").strip() or previous_current_url
    if final_image_items:
        resolved_index = 0
        if main_url:
            for idx, item in enumerate(final_image_items):
                if item.get("url") == main_url:
                    resolved_index = idx
                    break
        look.current_image_index = resolved_index
        look.image_url = final_image_items[resolved_index].get("url")
    else:
        look.current_image_index = None
        look.image_url = None


def _product_payload(product: Product) -> dict:
    return {
        "id": str(product.id),
        "name": product.name,
        "brand": product.brand,
        "price": product.price,
        "images": product.images if product.images is not None else [],
        "category": product.category,
        "tags": product.tags if product.tags is not None else [],
        "article": getattr(product, "article", None),
        "external_code": getattr(product, "external_code", None),
        "stock": getattr(product, "stock", None),
        "description": getattr(product, "description", None),
        "specifications": getattr(product, "specifications", None),
    }


def _json_parent_external_id(product: Product) -> str | None:
    for payload in (product.specifications, product.sync_metadata):
        if not isinstance(payload, dict):
            continue
        value = (
            payload.get("parent_external_id")
            or payload.get("Parent_Key")
            or payload.get("parent_key")
        )
        if value and value != "00000000-0000-0000-0000-000000000000":
            return str(value).strip()
    return None


async def _load_products_by_ids(db: AsyncSession, product_ids: List[Any]) -> List[Product]:
    ids: List[UUID] = []
    for pid in product_ids or []:
        try:
            ids.append(UUID(str(pid)))
        except (ValueError, TypeError):
            continue
    if not ids:
        return []
    result = await db.execute(select(Product).where(Product.id.in_(ids)))
    products = list(result.scalars().all())
    from app.models.product_stock import ProductStock

    async def _resolve_best_variant(product: Product) -> Product:
        if _json_parent_external_id(product):
            return product

        candidate_variants: List[Product] = []
        parent_external_id = str(product.external_id).strip() if getattr(product, "external_id", None) else None
        if parent_external_id:
            variants_result = await db.execute(
                select(Product).where(
                    and_(
                        Product.is_active == True,
                        or_(
                            func.jsonb_extract_path_text(Product.specifications, "parent_external_id") == parent_external_id,
                            func.jsonb_extract_path_text(Product.specifications, "Parent_Key") == parent_external_id,
                            func.jsonb_extract_path_text(Product.specifications, "parent_key") == parent_external_id,
                            func.jsonb_extract_path_text(Product.sync_metadata, "parent_external_id") == parent_external_id,
                            func.jsonb_extract_path_text(Product.sync_metadata, "Parent_Key") == parent_external_id,
                            func.jsonb_extract_path_text(Product.sync_metadata, "parent_key") == parent_external_id,
                        ),
                    )
                )
            )
            candidate_variants = list(variants_result.scalars().all())

        if not candidate_variants and getattr(product, "article", None):
            base_article = re.split(r"[-_\s]", str(product.article).strip(), maxsplit=1)[0].strip()
            if base_article:
                article_variants_result = await db.execute(
                    select(Product).where(
                        and_(
                            Product.is_active == True,
                            Product.id != product.id,
                            Product.article.isnot(None),
                            or_(
                                Product.article == base_article,
                                Product.article.like(f"{base_article}-%"),
                                Product.article.like(f"{base_article}_%"),
                                Product.article.like(f"{base_article} %"),
                            ),
                            or_(
                                func.jsonb_extract_path_text(Product.specifications, "parent_external_id").isnot(None),
                                func.jsonb_extract_path_text(Product.specifications, "Parent_Key").isnot(None),
                                func.jsonb_extract_path_text(Product.specifications, "parent_key").isnot(None),
                                func.jsonb_extract_path_text(Product.sync_metadata, "parent_external_id").isnot(None),
                                func.jsonb_extract_path_text(Product.sync_metadata, "Parent_Key").isnot(None),
                                func.jsonb_extract_path_text(Product.sync_metadata, "parent_key").isnot(None),
                            ),
                        )
                    )
                )
                candidate_variants = list(article_variants_result.scalars().all())

        if not candidate_variants:
            return product

        variant_ids = [variant.id for variant in candidate_variants]
        variant_stocks_result = await db.execute(
            select(
                ProductStock.product_id,
                func.sum(ProductStock.available_quantity).label("total_stock"),
            )
            .where(ProductStock.product_id.in_(variant_ids))
            .group_by(ProductStock.product_id)
        )
        variant_stocks_by_id = {str(row[0]): float(row[1]) for row in variant_stocks_result.all()}

        def _spec_score(candidate: Product) -> int:
            specs = candidate.specifications if isinstance(candidate.specifications, dict) else {}
            score = 0
            for key, value in specs.items():
                if key in {"parent_external_id", "Parent_Key", "parent_key", "characteristic_id", "quantity", "barcode"}:
                    continue
                if value in (None, "", [], {}, "00000000-0000-0000-0000-000000000000"):
                    continue
                score += 1
            return score

        def _variant_sort_key(candidate: Product) -> tuple[int, int, int, int, str]:
            stock = variant_stocks_by_id.get(str(candidate.id)) or 0
            return (
                1 if stock > 0 else 0,
                1 if (candidate.price or 0) > 0 else 0,
                _spec_score(candidate),
                1 if candidate.images else 0,
                candidate.article or candidate.external_code or candidate.name or "",
            )

        best_variant = sorted(candidate_variants, key=_variant_sort_key, reverse=True)[0]
        setattr(best_variant, "stock", variant_stocks_by_id.get(str(best_variant.id)))
        return best_variant

    stocks_result = await db.execute(
        select(
            ProductStock.product_id,
            func.sum(ProductStock.available_quantity).label("total_stock"),
        )
        .where(ProductStock.product_id.in_(ids))
        .group_by(ProductStock.product_id)
    )
    stocks_by_id = {str(row[0]): float(row[1]) for row in stocks_result.all()}

    parents_by_external_id = {
        str(product.external_id): product
        for product in products
        if getattr(product, "external_id", None)
    }
    missing_parent_ids = {
        parent_id
        for parent_id in (_json_parent_external_id(product) for product in products)
        if parent_id and parent_id not in parents_by_external_id
    }
    if missing_parent_ids:
        parents_result = await db.execute(select(Product).where(Product.external_id.in_(list(missing_parent_ids))))
        for parent_product in parents_result.scalars().all():
            if parent_product.external_id:
                parents_by_external_id[str(parent_product.external_id)] = parent_product

    resolved_products: List[Product] = []
    for product in products:
        resolved = await _resolve_best_variant(product)
        current_stock = getattr(resolved, "stock", None)
        setattr(resolved, "stock", stocks_by_id.get(str(resolved.id), current_stock))
        if not resolved.images:
            parent_id = _json_parent_external_id(resolved)
            parent_product = parents_by_external_id.get(parent_id) if parent_id else None
            if parent_product and parent_product.images:
                resolved.images = parent_product.images
        resolved_products.append(resolved)

    order = {str(pid): idx for idx, pid in enumerate(product_ids or [])}
    resolved_products.sort(key=lambda p: order.get(str(p.id), 9999))
    return resolved_products


async def _serialize_feed_look(db: AsyncSession, look: Look, current_user: Optional[User] = None) -> dict:
    products = await _load_products_by_ids(db, look.product_ids or [])
    liked = False
    favorited = False

    if current_user:
        like_result = await db.execute(
            select(LookReaction.id).where(
                and_(
                    LookReaction.look_id == look.id,
                    LookReaction.user_id == current_user.id,
                    LookReaction.reaction_type == "like",
                )
            )
        )
        liked = like_result.scalar_one_or_none() is not None

        saved_result = await db.execute(
            select(SavedLook.id).where(
                and_(
                    SavedLook.look_id == look.id,
                    SavedLook.user_id == current_user.id,
                    SavedLook.save_type == "favorite",
                )
            )
        )
        favorited = saved_result.scalar_one_or_none() is not None

    return {
        "id": str(look.id),
        "name": look.name,
        "caption": look.caption or look.description,
        "description": look.description,
        "product_ids": [str(pid) for pid in (look.product_ids or [])],
        "product_layout": look.product_layout or [],
        "media_items": _look_media_items(look),
        "image_url": look.image_url,
        "image_urls": look.image_urls or [],
        "style": look.style,
        "mood": look.mood,
        "style_values": _look_multi_value_payload(look, "style_values"),
        "mood_values": _look_multi_value_payload(look, "mood_values"),
        "style_dna": look.style_dna,
        "radical": look.radical,
        "style_dna_values": _look_multi_value_payload(look, "style_dna_values"),
        "radical_values": _look_multi_value_payload(look, "radical_values"),
        "source_provider": look.source_provider,
        "source_media_id": look.source_media_id,
        "source_permalink": look.source_permalink,
        "is_published": bool(look.is_published),
        "is_new": bool(look.is_new),
        "published_at": look.published_at.isoformat() if look.published_at else None,
        "like_count": look.like_count or 0,
        "favorite_count": look.favorite_count or 0,
        "liked_by_me": liked,
        "favorited_by_me": favorited,
        "products": [_product_payload(product) for product in products],
    }


async def _instagram_media_to_feed_item(media: dict, ig_service: InstagramService) -> dict:
    media_type = media.get("media_type")
    media_items: List[dict] = []

    if media_type == "CAROUSEL_ALBUM":
        try:
            details = await ig_service._make_request(
                str(media.get("id")),
                params={"fields": "children{media_type,media_url,thumbnail_url,permalink}"},
            )
            children = (details.get("children") or {}).get("data") or []
            for child in children:
                item_type = "video" if child.get("media_type") == "VIDEO" else "image"
                media_items.append(
                    {
                        "type": item_type,
                        "url": child.get("media_url"),
                        "thumbnail_url": child.get("thumbnail_url"),
                        "source": "instagram",
                    }
                )
        except Exception as e:
            logger.warning("Не удалось получить элементы карусели Instagram %s: %s", media.get("id"), e)

    if not media_items and media.get("media_url"):
        media_items.append(
            {
                "type": "video" if media_type == "VIDEO" else "image",
                "url": media.get("media_url"),
                "thumbnail_url": media.get("thumbnail_url"),
                "source": "instagram",
            }
        )

    return {
        "instagram_media_id": media.get("id"),
        "media_type": media_type,
        "caption": media.get("caption", ""),
        "timestamp": media.get("timestamp"),
        "permalink": media.get("permalink"),
        "media_items": media_items,
    }


@router.get("/feed", response_model=List[dict])
async def get_looks_feed(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    include_drafts: bool = Query(False),
    is_new: Optional[bool] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    query = select(Look)
    if not include_drafts:
        query = query.where(Look.is_published == True)
    if is_new is not None:
        query = query.where(Look.is_new == is_new)
    query = query.order_by(desc(Look.published_at), desc(Look.created_at)).offset(skip).limit(limit)
    result = await db.execute(query)
    looks = list(result.scalars().all())
    return [await _serialize_feed_look(db, look, current_user) for look in looks]


@router.get("/product/{product_id}", response_model=List[dict])
async def get_looks_for_product(
    product_id: UUID,
    limit: int = Query(10, ge=1, le=30),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Look)
        .where(
            or_(
                Look.is_published == True,
                Look.status == "approved",
                Look.approval_status == "approved",
            )
        )
        .order_by(desc(Look.published_at), desc(Look.created_at))
    )
    result = await db.execute(query)
    product_id_str = str(product_id)
    looks = [
        look
        for look in result.scalars().all()
        if product_id_str in {str(pid) for pid in (look.product_ids or [])}
    ][:limit]
    return [await _serialize_feed_look(db, look, current_user) for look in looks]


@router.post("/feed/{look_id}/like", response_model=dict)
async def toggle_look_like(
    look_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    look = (await db.execute(select(Look).where(Look.id == look_id))).scalar_one_or_none()
    if not look:
        raise HTTPException(status_code=404, detail="Образ не найден")

    existing = (
        await db.execute(
            select(LookReaction).where(
                and_(
                    LookReaction.look_id == look_id,
                    LookReaction.user_id == current_user.id,
                    LookReaction.reaction_type == "like",
                )
            )
        )
    ).scalar_one_or_none()

    if existing:
        await db.delete(existing)
        liked = False
    else:
        db.add(LookReaction(user_id=current_user.id, look_id=look_id, reaction_type="like"))
        liked = True

    await db.flush()
    count_result = await db.execute(
        select(func.count(LookReaction.id)).where(
            and_(LookReaction.look_id == look_id, LookReaction.reaction_type == "like")
        )
    )
    look.like_count = int(count_result.scalar() or 0)
    await db.commit()
    return {"liked": liked, "like_count": look.like_count}


@router.post("/feed/{look_id}/favorite", response_model=dict)
async def toggle_look_favorite(
    look_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    look = (await db.execute(select(Look).where(Look.id == look_id))).scalar_one_or_none()
    if not look:
        raise HTTPException(status_code=404, detail="Образ не найден")

    existing = (
        await db.execute(
            select(SavedLook).where(
                and_(
                    SavedLook.look_id == look_id,
                    SavedLook.user_id == current_user.id,
                    SavedLook.save_type == "favorite",
                )
            )
        )
    ).scalar_one_or_none()

    if existing:
        await db.delete(existing)
        favorited = False
    else:
        db.add(SavedLook(user_id=current_user.id, look_id=look_id, save_type="favorite"))
        favorited = True

    await db.flush()
    count_result = await db.execute(
        select(func.count(SavedLook.id)).where(and_(SavedLook.look_id == look_id, SavedLook.save_type == "favorite"))
    )
    look.favorite_count = int(count_result.scalar() or 0)
    await db.commit()
    return {"favorited": favorited, "favorite_count": look.favorite_count}


@router.patch(
    "/feed/{look_id}/publish",
    response_model=dict,
)
async def publish_look(
    look_id: UUID,
    request: LookPublishRequest,
    db: AsyncSession = Depends(get_db),
):
    look = (await db.execute(select(Look).where(Look.id == look_id))).scalar_one_or_none()
    if not look:
        raise HTTPException(status_code=404, detail="Образ не найден")

    look.is_published = request.is_published
    if request.is_published and not look.published_at:
        look.published_at = datetime.utcnow()
    await db.commit()
    await db.refresh(look)
    return await _serialize_feed_look(db, look)


@router.get(
    "/instagram/preview",
    response_model=List[dict],
    dependencies=[Depends(require_any_role(["admin", "content_manager", "ai_marketer"]))],
)
async def preview_instagram_media(limit: int = Query(12, ge=1, le=50)):
    async with InstagramService() as ig_service:
        media_list = await ig_service.get_media_list(limit=limit)
        return [await _instagram_media_to_feed_item(media, ig_service) for media in media_list]


@router.post(
    "/instagram/import",
    response_model=dict,
    dependencies=[Depends(require_any_role(["admin", "content_manager", "ai_marketer"]))],
)
async def import_instagram_media(request: LookImportRequest, db: AsyncSession = Depends(get_db)):
    existing = (
        await db.execute(
            select(Look).where(
                and_(Look.source_provider == "instagram", Look.source_media_id == request.instagram_media_id)
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Этот Instagram-пост уже импортирован")

    async with InstagramService() as ig_service:
        media = await ig_service._make_request(
            request.instagram_media_id,
            params={"fields": "id,media_type,media_url,thumbnail_url,caption,timestamp,permalink"},
        )
        item = await _instagram_media_to_feed_item(media, ig_service)

    caption = item.get("caption") or ""
    product_ids = [str(pid) for pid in request.product_ids]
    look = Look(
        name=request.name or (caption[:80].strip() if caption else "Instagram образ"),
        product_ids=product_ids,
        product_layout=request.product_layout or [{"product_id": pid, "position": idx + 1} for idx, pid in enumerate(product_ids)],
        description=caption,
        caption=caption,
        image_url=(item.get("media_items") or [{}])[0].get("url"),
        image_urls=[{"url": m.get("url"), "source": "instagram"} for m in item.get("media_items", []) if m.get("url")],
        media_items=item.get("media_items", []),
        source_provider="instagram",
        source_media_id=request.instagram_media_id,
        source_permalink=item.get("permalink"),
        status="approved" if request.publish else "draft",
        approval_status="approved" if request.publish else "pending",
        is_published=request.publish,
        published_at=datetime.utcnow() if request.publish else None,
    )
    db.add(look)
    await db.commit()
    await db.refresh(look)
    return await _serialize_feed_look(db, look)


@router.get("/manual/options", response_model=dict)
async def get_manual_look_options(db: AsyncSession = Depends(get_db)):
    return {
        "styles": await _get_setting_list(
            db, "manual_look_style_options", MANUAL_LOOK_OPTION_DEFAULTS["manual_look_style_options"]
        ),
        "moods": await _get_setting_list(
            db, "manual_look_mood_options", MANUAL_LOOK_OPTION_DEFAULTS["manual_look_mood_options"]
        ),
        "style_dna": await _get_setting_list(
            db, "manual_look_style_dna_options", MANUAL_LOOK_OPTION_DEFAULTS["manual_look_style_dna_options"]
        ),
        "radicals": await _get_setting_list(
            db, "manual_look_radical_options", MANUAL_LOOK_OPTION_DEFAULTS["manual_look_radical_options"]
        ),
    }


@router.post("/manual/generate-copy", response_model=dict)
async def generate_manual_look_copy(request: ManualLookCopyRequest, db: AsyncSession = Depends(get_db)):
    products = await _load_products_by_ids(db, request.product_ids or [])
    if not products:
        raise HTTPException(status_code=400, detail="Для ИИ-генерации добавьте хотя бы один товар")

    system_prompt = await _get_active_prompt_text(
        db,
        MANUAL_LOOK_COPY_AGENT_TYPE,
        MANUAL_LOOK_COPY_FALLBACK_PROMPT,
    )

    style_values = _normalize_multi_values(request.style_values, request.style)
    mood_values = _normalize_multi_values(request.mood_values, request.mood)
    style_dna_values = _normalize_multi_values(request.style_dna_values, request.style_dna)
    radical_values = _normalize_multi_values(request.radical_values, request.radical)

    product_blocks = "\n\n".join(_product_text_for_manual_look(product) for product in products[:8])
    prompt = f"""Собери название и описание ручного образа GLAME.

Формат образа: {"Реальная съемка" if request.source_provider == "real_shoot" else "Для выбранной модели"}
Стиль: {", ".join(style_values) if style_values else "не указан"}
Настроение: {", ".join(mood_values) if mood_values else "не указано"}
Стилевой ДНК: {", ".join(style_dna_values) if style_dna_values else "не указан"}
Радикал: {", ".join(radical_values) if radical_values else "не указан"}

Черновик названия: {request.current_name or "отсутствует"}
Черновик описания: {request.current_description or "отсутствует"}

Товары, участвующие в образе:
{product_blocks}

Сгенерируй JSON с полями:
{{
  "name": "короткое название образа",
  "description": "описание образа"
}}
"""

    result = await llm_service.generate_structured(
        prompt=prompt,
        system_prompt=system_prompt,
        response_format={"name": "Название образа", "description": "Описание образа"},
        temperature=0.7,
        max_tokens=900,
    )

    generated_name = str(result.get("name") or "").strip()
    generated_description = str(result.get("description") or "").strip()
    if not generated_name and not generated_description:
        raise HTTPException(status_code=500, detail="ИИ не вернул название и описание образа")

    await _append_setting_list_values(
        db, "manual_look_style_options", style_values, MANUAL_LOOK_OPTION_DEFAULTS["manual_look_style_options"]
    )
    await _append_setting_list_values(
        db, "manual_look_mood_options", mood_values, MANUAL_LOOK_OPTION_DEFAULTS["manual_look_mood_options"]
    )
    await _append_setting_list_values(
        db, "manual_look_style_dna_options", style_dna_values, MANUAL_LOOK_OPTION_DEFAULTS["manual_look_style_dna_options"]
    )
    await _append_setting_list_values(
        db, "manual_look_radical_options", radical_values, MANUAL_LOOK_OPTION_DEFAULTS["manual_look_radical_options"]
    )
    await db.commit()

    return {
        "name": generated_name,
        "description": generated_description,
    }


@router.post("/manual", response_model=dict)
async def create_manual_look(
    description: Optional[str] = Form(None),
    name: Optional[str] = Form(None),
    digital_model: Optional[str] = Form(None),
    source_provider: str = Form("manual"),
    style: Optional[str] = Form(None),
    mood: Optional[str] = Form(None),
    style_dna: Optional[str] = Form(None),
    radical: Optional[str] = Form(None),
    style_values_json: str = Form("[]"),
    mood_values_json: str = Form("[]"),
    style_dna_values_json: str = Form("[]"),
    radical_values_json: str = Form("[]"),
    is_new: bool = Form(False),
    main_image_ref: Optional[str] = Form(None),
    ordered_image_refs_json: str = Form("[]"),
    product_links_json: str = Form("[]"),
    photos: Optional[List[UploadFile]] = File(None),
    video: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
):
    clean_description = (description or "").strip()

    provider = (source_provider or "manual").strip().lower()
    if provider not in {"manual", "real_shoot"}:
        raise HTTPException(status_code=400, detail="Некорректный тип ручного образа")

    try:
        raw_links = json.loads(product_links_json or "[]")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Не удалось разобрать связи с товарами: {exc}") from exc

    if not isinstance(raw_links, list):
        raise HTTPException(status_code=400, detail="Связи с товарами должны быть переданы списком")

    def _parse_values_json(raw_value: str, field_name: str) -> List[str]:
        try:
            parsed = json.loads(raw_value or "[]")
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Не удалось разобрать список '{field_name}'") from exc
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
        raise HTTPException(status_code=400, detail=f"Список '{field_name}' должен быть массивом")

    style_values = _normalize_multi_values(_parse_values_json(style_values_json, "style_values"), style)
    mood_values = _normalize_multi_values(_parse_values_json(mood_values_json, "mood_values"), mood)
    style_dna_values = _normalize_multi_values(_parse_values_json(style_dna_values_json, "style_dna_values"), style_dna)
    radical_values = _normalize_multi_values(_parse_values_json(radical_values_json, "radical_values"), radical)
    ordered_image_refs = _parse_values_json(ordered_image_refs_json, "ordered_image_refs")

    validated_model: Optional[str] = None
    if provider != "real_shoot" and digital_model:
        available_models = _discover_digital_models()
        available_model_ids = {m["id"] for m in available_models}
        available_model_by_norm = {
            (_sanitize_model_name(m["id"]) or ""): m["id"] for m in available_models
        }
        selected_norm = _sanitize_model_name(digital_model) or ""
        validated_model = digital_model if digital_model in available_model_ids else available_model_by_norm.get(selected_norm)
        if not validated_model:
            raise HTTPException(status_code=400, detail=f"Цифровая модель '{digital_model}' не найдена")

    ordered_product_ids: List[str] = []
    product_links: List[dict] = []
    seen_product_ids: set[str] = set()
    for index, item in enumerate(raw_links):
        if not isinstance(item, dict):
            continue
        product_id = str(item.get("product_id") or "").strip()
        if not product_id:
            continue
        if product_id not in seen_product_ids:
            seen_product_ids.add(product_id)
            ordered_product_ids.append(product_id)
        selected_image_urls = [
            str(url).strip()
            for url in (item.get("selected_image_urls") or [])
            if str(url).strip()
        ]
        product_links.append(
            {
                "product_id": product_id,
                "article": str(item.get("article") or "").strip() or None,
                "position": int(item.get("position") or (index + 1)),
                "selected_image_urls": selected_image_urls,
            }
        )

    products_by_id: dict[str, Product] = {}
    if ordered_product_ids:
        product_uuids: List[UUID] = []
        for product_id in ordered_product_ids:
            try:
                product_uuids.append(UUID(product_id))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=f"Некорректный product_id: {product_id}") from exc

        products_result = await db.execute(select(Product).where(Product.id.in_(product_uuids)))
        products = list(products_result.scalars().all())
        products_by_id = {str(product.id): product for product in products}
        missing_ids = [product_id for product_id in ordered_product_ids if product_id not in products_by_id]
        if missing_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Некоторые товары не найдены: {', '.join(missing_ids[:5])}",
            )

    uploaded_photo_urls: List[str] = []
    for file in photos or []:
        uploaded_photo_urls.append(
            await _save_manual_look_upload(
                file=file,
                folder="manual",
                allowed_types=LOOK_MANUAL_IMAGE_TYPES,
                max_bytes=LOOK_MANUAL_IMAGE_MAX_BYTES,
            )
        )

    selected_gallery_urls: List[str] = []
    seen_gallery_urls: set[str] = set()
    product_layout: List[dict] = []
    for item in product_links:
        product = products_by_id.get(item["product_id"])
        gallery_urls = []
        for url in item["selected_image_urls"]:
            if url not in seen_gallery_urls:
                seen_gallery_urls.add(url)
                selected_gallery_urls.append(url)
            gallery_urls.append(url)
        product_layout.append(
            {
                "product_id": item["product_id"],
                "position": item["position"],
                "article": item["article"] or getattr(product, "article", None) or getattr(product, "external_code", None),
                "product_name": product.name if product else None,
                "selected_image_urls": gallery_urls,
                "source": "manual_link",
            }
        )

    all_image_urls = uploaded_photo_urls + selected_gallery_urls
    if not all_image_urls:
        raise HTTPException(
            status_code=400,
            detail="Добавьте хотя бы одно фото образа: загрузите файл или выберите фото из галереи товара",
        )

    video_url: Optional[str] = None
    if video and getattr(video, "filename", None):
        video_url = await _save_manual_look_upload(
            file=video,
            folder="manual",
            allowed_types=LOOK_MANUAL_VIDEO_TYPES,
            max_bytes=LOOK_MANUAL_VIDEO_MAX_BYTES,
        )

    preferred_main_image_url: Optional[str] = None
    if main_image_ref:
        if str(main_image_ref).startswith("new_upload:"):
            try:
                upload_idx = int(str(main_image_ref).split(":", 1)[1])
                if 0 <= upload_idx < len(uploaded_photo_urls):
                    preferred_main_image_url = uploaded_photo_urls[upload_idx]
            except (TypeError, ValueError):
                preferred_main_image_url = None
        else:
            preferred_main_image_url = str(main_image_ref).strip() or None

    ordered_image_urls: List[str] = []
    if ordered_image_refs:
        ref_to_url = {f"new_upload:{idx}": url for idx, url in enumerate(uploaded_photo_urls)}
        for ref in ordered_image_refs:
            clean_ref = str(ref or "").strip()
            if not clean_ref:
                continue
            mapped_url = ref_to_url.get(clean_ref, clean_ref)
            if mapped_url not in ordered_image_urls:
                ordered_image_urls.append(mapped_url)

    default_name = "Реальная съемка" if provider == "real_shoot" else "Ручной образ"
    look_name = (name or "").strip() or (clean_description[:80].strip() if clean_description else default_name) or default_name

    generation_metadata = {
        "creation_mode": provider,
        "manual_created": True,
        "manual_product_links_count": len(product_layout),
    }
    if validated_model:
        generation_metadata["digital_model"] = validated_model

    await _append_setting_list_values(
        db, "manual_look_style_options", style_values, MANUAL_LOOK_OPTION_DEFAULTS["manual_look_style_options"]
    )
    await _append_setting_list_values(
        db, "manual_look_mood_options", mood_values, MANUAL_LOOK_OPTION_DEFAULTS["manual_look_mood_options"]
    )
    await _append_setting_list_values(
        db, "manual_look_style_dna_options", style_dna_values, MANUAL_LOOK_OPTION_DEFAULTS["manual_look_style_dna_options"]
    )
    await _append_setting_list_values(
        db, "manual_look_radical_options", radical_values, MANUAL_LOOK_OPTION_DEFAULTS["manual_look_radical_options"]
    )

    look = Look(
        name=look_name,
        product_ids=ordered_product_ids,
        style=_primary_multi_value(style_values, style),
        mood=_primary_multi_value(mood_values, mood),
        style_values=style_values,
        mood_values=mood_values,
        style_dna=_primary_multi_value(style_dna_values, style_dna),
        radical=_primary_multi_value(radical_values, radical),
        style_dna_values=style_dna_values,
        radical_values=radical_values,
        description=clean_description,
        caption=clean_description,
        product_layout=product_layout,
        source_provider=provider,
        status="draft",
        approval_status="pending",
        is_new=is_new,
        generation_metadata=generation_metadata,
    )
    _sync_look_media_items(
        look,
        non_gallery_image_items=[
            {"type": "image", "url": url, "source": "manual_upload"} for url in uploaded_photo_urls
        ],
        video_items=[{"type": "video", "url": video_url, "source": "manual_upload"}] if video_url else [],
        preferred_main_image_url=preferred_main_image_url,
        ordered_image_urls=ordered_image_urls,
    )

    db.add(look)
    await db.commit()
    await db.refresh(look)
    return await _serialize_feed_look(db, look)


@router.get("", response_model=List[LookResponse])
@router.get("/", response_model=List[LookResponse])
async def get_looks(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    style: Optional[str] = None,
    mood: Optional[str] = None,
    is_new: Optional[bool] = Query(None),
    digital_model: Optional[str] = Query(None, description="ID цифровой модели для фильтрации портфолио"),
    db: AsyncSession = Depends(get_db)
):
    query = select(Look)
    
    if style:
        query = query.where(Look.style == style)
    if mood:
        query = query.where(Look.mood == mood)
    if is_new is not None:
        query = query.where(Look.is_new == is_new)
    
    if not digital_model:
        query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    looks = list(result.scalars().all())

    if digital_model:
        digital_model_norm = _sanitize_model_name(digital_model)
        filtered = []
        for look in looks:
            if digital_model_norm == REAL_SHOOT_MODEL_ID:
                if (look.source_provider or "").strip().lower() == REAL_SHOOT_MODEL_ID:
                    filtered.append(look)
                continue
            metadata = look.generation_metadata or {}
            model_value = metadata.get("digital_model")
            if _sanitize_model_name(model_value) == digital_model_norm:
                filtered.append(look)
        looks = filtered[skip : skip + limit]
    
    # Конвертируем UUID в строки для ответа
    looks_list = []
    for look in looks:
        # Определяем основное изображение из image_urls или используем image_url
        image_url = None
        if look.image_urls and len(look.image_urls) > 0:
            current_idx = look.current_image_index if look.current_image_index is not None else 0
            if current_idx < len(look.image_urls):
                image_data = look.image_urls[current_idx]
                if isinstance(image_data, dict):
                    image_url = image_data.get("url")
                else:
                    image_url = image_data
        elif look.image_url:
            image_url = look.image_url
        
        # Исправляем опечатку в image_url (lcimages -> look_images)
        if image_url and "/static/lcimages/" in image_url:
            image_url = image_url.replace("/static/lcimages/", "/static/look_images/")
        
        try_on_image_url = look.try_on_image_url
        if try_on_image_url and "/static/lcimages/" in try_on_image_url:
            try_on_image_url = try_on_image_url.replace("/static/lcimages/", "/static/look_images/")
        
        look_dict = {
            "id": str(look.id),
            "name": look.name,
            "product_ids": [str(pid) for pid in (look.product_ids or [])],
            "style": look.style,
            "mood": look.mood,
            "style_values": _look_multi_value_payload(look, "style_values"),
            "mood_values": _look_multi_value_payload(look, "mood_values"),
            "style_dna": look.style_dna,
            "radical": look.radical,
            "style_dna_values": _look_multi_value_payload(look, "style_dna_values"),
            "radical_values": _look_multi_value_payload(look, "radical_values"),
            "description": look.description,
            "image_url": image_url,
            "image_urls": look.image_urls or [],
            "current_image_index": look.current_image_index,
            "status": look.status,
            "approval_status": look.approval_status,
            "try_on_image_url": try_on_image_url,
            "generation_metadata": look.generation_metadata or {},
            "caption": look.caption,
            "media_items": _look_media_items(look),
            "product_layout": look.product_layout or [],
            "source_provider": look.source_provider,
            "source_media_id": look.source_media_id,
            "source_permalink": look.source_permalink,
            "is_published": bool(look.is_published),
            "is_new": bool(look.is_new),
            "published_at": look.published_at.isoformat() if look.published_at else None,
            "like_count": look.like_count or 0,
            "favorite_count": look.favorite_count or 0,
        }
        looks_list.append(look_dict)
    
    return looks_list


@router.get("/models", response_model=List[DigitalModelInfo])
async def get_digital_models(db: AsyncSession = Depends(get_db)):
    """Список цифровых моделей (ядро + статистика портфолио)"""
    models = _discover_digital_models()

    looks_result = await db.execute(select(Look))
    looks = list(looks_result.scalars().all())
    content_items_result = await db.execute(select(ContentItem))
    content_items = list(content_items_result.scalars().all())

    items: List[dict] = []
    for model in models:
        model_id = model["id"]
        portfolio_images = _collect_portfolio_images_for_model(
            model_id=model_id,
            looks=looks,
            content_items=content_items,
        )
        items.append(
            {
                **model,
                "portfolio_images_count": len(portfolio_images),
                "portfolio_images": portfolio_images,
            }
        )

    real_shoot_portfolio = _collect_real_shoot_portfolio_images(looks)
    real_shoot_looks_count = sum(
        1 for look in looks if (look.source_provider or "").strip().lower() == REAL_SHOOT_MODEL_ID
    )
    if real_shoot_portfolio or real_shoot_looks_count > 0:
        items.append(
            {
                "id": REAL_SHOOT_MODEL_ID,
                "name": REAL_SHOOT_MODEL_NAME,
                "source_images": [],
                "source_images_count": 0,
                "portfolio_images_count": len(real_shoot_portfolio),
                "portfolio_images": real_shoot_portfolio,
            }
        )
    return items


@router.delete("/models/{model_id}/portfolio-image", response_model=dict)
async def delete_portfolio_image(
    model_id: str,
    image_url: str = Query(..., description="URL изображения из портфолио"),
    db: AsyncSession = Depends(get_db),
):
    """
    Удаляет изображение из портфолио модели:
    - удаляет файл из static (если существует),
    - удаляет ссылки на это изображение из looks (image_url/image_urls/try_on_image_url),
    - удаляет ссылки из content_items.generated.media.items для выбранной модели.
    """
    model_norm = _sanitize_model_name(model_id)
    if not model_norm:
        raise HTTPException(status_code=400, detail="Некорректный model_id")

    target_url = _normalize_portfolio_url(image_url)
    if not target_url:
        raise HTTPException(status_code=400, detail="Некорректный image_url")

    looks_result = await db.execute(select(Look))
    looks = list(looks_result.scalars().all())
    content_items_result = await db.execute(select(ContentItem))
    content_items = list(content_items_result.scalars().all())

    looks_updated = 0
    look_refs_removed = 0
    content_items_updated = 0
    content_refs_removed = 0
    is_real_shoot_model = model_norm == REAL_SHOOT_MODEL_ID

    # 1) Чистим ссылки в looks по модели
    for look in looks:
        metadata = look.generation_metadata or {}
        look_model = _sanitize_model_name(metadata.get("digital_model"))
        look_provider = (look.source_provider or "").strip().lower()
        if is_real_shoot_model:
            if look_provider != REAL_SHOOT_MODEL_ID:
                continue
        elif look_model != model_norm:
            continue

        changed = False

        if _portfolio_urls_equal(look.image_url, target_url):
            look.image_url = None
            changed = True
            look_refs_removed += 1

        if _portfolio_urls_equal(look.try_on_image_url, target_url):
            look.try_on_image_url = None
            changed = True
            look_refs_removed += 1

        if isinstance(look.image_urls, list):
            new_image_urls: List[Any] = []
            removed_in_list = 0
            for image_data in look.image_urls:
                candidate_url = image_data.get("url") if isinstance(image_data, dict) else str(image_data)
                if _portfolio_urls_equal(candidate_url, target_url):
                    removed_in_list += 1
                    continue
                new_image_urls.append(image_data)
            if removed_in_list > 0:
                look.image_urls = new_image_urls
                look_refs_removed += removed_in_list
                changed = True

                if look.current_image_index is not None:
                    if len(new_image_urls) == 0:
                        look.current_image_index = None
                    elif look.current_image_index >= len(new_image_urls):
                        look.current_image_index = len(new_image_urls) - 1

                if look.current_image_index is not None and len(new_image_urls) > 0:
                    current_image = new_image_urls[look.current_image_index]
                    look.image_url = current_image.get("url") if isinstance(current_image, dict) else str(current_image)

        if changed:
            looks_updated += 1

    # 2) Чистим ссылки в content_items по модели
    for item in content_items:
        spec = item.spec if isinstance(item.spec, dict) else {}
        media_task = spec.get("media_task") if isinstance(spec.get("media_task"), dict) else {}
        profile = _sanitize_model_name(
            media_task.get("model_id")
            or media_task.get("model_profile")
            or media_task.get("persona_type")
            or item.persona
        )
        if profile != model_norm:
            continue

        generated = item.generated if isinstance(item.generated, dict) else {}
        media = generated.get("media") if isinstance(generated.get("media"), dict) else {}
        media_items = media.get("items") if isinstance(media.get("items"), list) else []
        if not media_items:
            continue

        new_media_items = []
        removed = 0
        for media_item in media_items:
            item_url = media_item.get("url") if isinstance(media_item, dict) else None
            if _portfolio_urls_equal(item_url, target_url):
                removed += 1
                continue
            new_media_items.append(media_item)

        if removed > 0:
            media["items"] = new_media_items
            generated["media"] = media
            item.generated = generated
            content_items_updated += 1
            content_refs_removed += removed

    # 3) Удаляем файл из static
    file_deleted = False
    deleted_path = None
    target_path = _resolve_static_path_from_url(target_url)
    if target_path and target_path.exists() and target_path.is_file():
        target_path.unlink()
        file_deleted = True
        deleted_path = str(target_path)

    if looks_updated == 0 and content_items_updated == 0 and not file_deleted:
        raise HTTPException(status_code=404, detail="Изображение не найдено в портфолио модели")

    await db.commit()

    return {
        "success": True,
        "model_id": model_norm,
        "image_url": target_url,
        "looks_updated": looks_updated,
        "look_refs_removed": look_refs_removed,
        "content_items_updated": content_items_updated,
        "content_refs_removed": content_refs_removed,
        "file_deleted": file_deleted,
        "deleted_path": deleted_path,
    }


@router.post("/models", response_model=dict)
async def create_digital_model(
    name: str = Form(..., description="Имя модели на латинице (будет использовано как ID папки)"),
):
    """
    Создает новую цифровую модель:
    - Валидирует имя (только латиница, цифры, подчеркивания, дефисы)
    - Создает папку в static/models/{name}
    """
    # Валидация имени - только латинские буквы, цифры, подчеркивания, дефисы
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*$', name):
        raise HTTPException(
            status_code=400,
            detail="Имя модели должно начинаться с латинской буквы и содержать только латинские буквы, цифры, подчеркивания и дефисы"
        )
    
    model_id = name.lower()
    
    # Находим корневую директорию static/models
    models_root = _first_existing_static_subdir("models")
    if not models_root:
        # Если директории нет, создаем её в первом доступном static root
        for root in _static_roots():
            models_root = root / "models"
            models_root.mkdir(parents=True, exist_ok=True)
            break
        if not models_root:
            raise HTTPException(status_code=500, detail="Не удалось найти или создать директорию static/models")
    
    # Проверяем, не существует ли уже модель с таким именем
    model_dir = models_root / model_id
    if model_dir.exists():
        raise HTTPException(status_code=409, detail=f"Модель '{model_id}' уже существует")
    
    # Создаем папку модели
    try:
        model_dir.mkdir(parents=True, exist_ok=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Не удалось создать папку модели: {str(e)}")
    
    return {
        "success": True,
        "model_id": model_id,
        "name": model_id.replace("_", " ").title(),
        "path": str(model_dir),
        "message": f"Модель '{model_id}' успешно создана. Теперь вы можете загрузить исходные фотографии."
    }


@router.delete("/models/{model_id}", response_model=dict)
async def delete_digital_model(
    model_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Удаляет цифровую модель полностью:
    - Удаляет папку с исходными фото из static/models/{model_id}
    - Удаляет сгенерированные образы этой модели из look_images/models/{model_id}
    - Не удаляет записи из БД (looks и content_items остаются, но без привязки к модели)
    """
    model_norm = _sanitize_model_name(model_id)
    if not model_norm:
        raise HTTPException(status_code=400, detail="Некорректный model_id")
    
    deleted_paths = []
    errors = []
    
    # 1. Удаляем папку с исходными фото
    models_root = _first_existing_static_subdir("models")
    if models_root:
        model_dir = models_root / model_norm
        if model_dir.exists() and model_dir.is_dir():
            try:
                import shutil
                shutil.rmtree(model_dir)
                deleted_paths.append(str(model_dir))
            except Exception as e:
                errors.append(f"Не удалось удалить папку исходных фото: {str(e)}")
    
    # 2. Удаляем сгенерированные образы модели
    for look_model_root in _iter_existing_static_subdirs(f"look_images/models/{model_norm}"):
        if look_model_root.exists() and look_model_root.is_dir():
            try:
                import shutil
                shutil.rmtree(look_model_root)
                deleted_paths.append(str(look_model_root))
            except Exception as e:
                errors.append(f"Не удалось удалить папку сгенерированных образов: {str(e)}")
    
    if not deleted_paths and errors:
        raise HTTPException(status_code=500, detail="; ".join(errors))
    
    return {
        "success": True,
        "model_id": model_norm,
        "deleted_paths": deleted_paths,
        "errors": errors if errors else None,
        "message": f"Модель '{model_norm}' успешно удалена" if not errors else f"Модель '{model_norm}' удалена с ошибками"
    }


@router.post("/models/{model_id}/source-images", response_model=dict)
async def upload_model_source_images(
    model_id: str,
    files: List[UploadFile] = File(..., description="Исходные фотографии модели (JPG, PNG, WebP)"),
):
    """
    Загружает исходные фотографии для цифровой модели в static/models/{model_id}
    """
    model_norm = _sanitize_model_name(model_id)
    if not model_norm:
        raise HTTPException(status_code=400, detail="Некорректный model_id")
    
    # Находим директорию модели
    models_root = _first_existing_static_subdir("models")
    if not models_root:
        raise HTTPException(status_code=404, detail="Директория static/models не найдена")
    
    model_dir = models_root / model_norm
    if not model_dir.exists() or not model_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Модель '{model_norm}' не найдена")
    
    allowed_exts = {".jpg", ".jpeg", ".png", ".webp"}
    uploaded_files = []
    errors = []
    
    for file in files:
        # Проверяем расширение файла
        file_ext = Path(file.filename or "").suffix.lower()
        if file_ext not in allowed_exts:
            errors.append(f"Файл '{file.filename}': неподдерживаемый формат (требуется JPG, PNG или WebP)")
            continue
        
        # Создаем безопасное имя файла
        safe_filename = re.sub(r'[^a-zA-Z0-9._-]', '_', file.filename or "image.jpg")
        
        # Если файл с таким именем уже существует, добавляем счетчик
        target_path = model_dir / safe_filename
        counter = 1
        while target_path.exists():
            stem = Path(safe_filename).stem
            ext = Path(safe_filename).suffix
            target_path = model_dir / f"{stem}_{counter}{ext}"
            counter += 1
        
        try:
            content = await file.read()
            with open(target_path, "wb") as f:
                f.write(content)
            uploaded_files.append({
                "original_name": file.filename,
                "saved_name": target_path.name,
                "path": f"/static/models/{model_norm}/{target_path.name}"
            })
        except Exception as e:
            errors.append(f"Файл '{file.filename}': ошибка загрузки - {str(e)}")
    
    return {
        "success": len(uploaded_files) > 0,
        "model_id": model_norm,
        "uploaded_count": len(uploaded_files),
        "uploaded_files": uploaded_files,
        "errors": errors if errors else None,
        "message": f"Загружено {len(uploaded_files)} файлов" + (f" (с ошибками: {len(errors)})" if errors else "")
    }


@router.delete("/models/{model_id}/source-images/{filename}", response_model=dict)
async def delete_model_source_image(
    model_id: str,
    filename: str,
):
    """
    Удаляет исходное фото модели из static/models/{model_id}
    """
    model_norm = _sanitize_model_name(model_id)
    if not model_norm:
        raise HTTPException(status_code=400, detail="Некорректный model_id")
    
    # Безопасная обработка имени файла
    safe_filename = Path(filename).name  # Убираем пути
    
    # Находим директорию модели
    models_root = _first_existing_static_subdir("models")
    if not models_root:
        raise HTTPException(status_code=404, detail="Директория static/models не найдена")
    
    model_dir = models_root / model_norm
    if not model_dir.exists() or not model_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Модель '{model_norm}' не найдена")
    
    target_file = model_dir / safe_filename
    
    # Проверяем, что файл действительно находится в директории модели (защита от path traversal)
    try:
        resolved_file = target_file.resolve()
        resolved_model_dir = model_dir.resolve()
        if not str(resolved_file).startswith(str(resolved_model_dir)):
            raise HTTPException(status_code=400, detail="Некорректное имя файла")
    except Exception:
        raise HTTPException(status_code=400, detail="Некорректное имя файла")
    
    if not target_file.exists() or not target_file.is_file():
        raise HTTPException(status_code=404, detail=f"Файл '{safe_filename}' не найден")
    
    try:
        target_file.unlink()
        return {
            "success": True,
            "model_id": model_norm,
            "filename": safe_filename,
            "message": f"Файл '{safe_filename}' успешно удален"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Не удалось удалить файл: {str(e)}")


@router.get("/{look_id}", response_model=dict)
async def get_look(look_id: UUID, db: AsyncSession = Depends(get_db)):
    """Получение образа с продуктами"""
    try:
        result = await db.execute(select(Look).where(Look.id == look_id))
        look = result.scalar_one_or_none()
        if not look:
            raise HTTPException(status_code=404, detail="Look not found")

        await _ensure_look_has_catalog_products(db, look, require_image_refs=True)
        
        products = await _load_products_by_ids(db, look.product_ids or [])
        
        # Определяем основное изображение из image_urls или используем image_url
        image_url = None
        if look.image_urls and len(look.image_urls) > 0:
            current_idx = look.current_image_index if look.current_image_index is not None else 0
            if current_idx < len(look.image_urls):
                image_data = look.image_urls[current_idx]
                if isinstance(image_data, dict):
                    image_url = image_data.get("url")
                else:
                    image_url = image_data
        elif look.image_url:
            image_url = look.image_url
        
        # Исправляем опечатку в image_url (lcimages -> look_images)
        if image_url and "/static/lcimages/" in image_url:
            image_url = image_url.replace("/static/lcimages/", "/static/look_images/")
        
        try_on_image_url = look.try_on_image_url
        if try_on_image_url and "/static/lcimages/" in try_on_image_url:
            try_on_image_url = try_on_image_url.replace("/static/lcimages/", "/static/look_images/")
        
        return {
            "id": str(look.id),
            "name": look.name,
            "product_ids": [str(pid) for pid in (look.product_ids or [])],
            "style": look.style,
            "mood": look.mood,
            "style_values": _look_multi_value_payload(look, "style_values"),
            "mood_values": _look_multi_value_payload(look, "mood_values"),
            "style_dna": look.style_dna,
            "radical": look.radical,
            "style_dna_values": _look_multi_value_payload(look, "style_dna_values"),
            "radical_values": _look_multi_value_payload(look, "radical_values"),
            "description": look.description,
            "image_url": image_url,
            "image_urls": look.image_urls or [],
            "current_image_index": look.current_image_index,
            "status": look.status,
            "approval_status": look.approval_status,
            "try_on_image_url": try_on_image_url,
            "generation_metadata": look.generation_metadata or {},
            "product_layout": look.product_layout or [],
            "source_provider": look.source_provider,
            "is_new": bool(look.is_new),
            "media_items": _look_media_items(look),
            "products": [_product_payload(p) for p in products]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Ошибка при получении образа")
        raise HTTPException(status_code=500, detail=f"Ошибка при получении образа: {str(e)}")


@router.post("/generate", response_model=dict)
async def generate_look(request: LookGenerateRequest):
    """Генерация образа на основе запроса"""
    import time
    start_time = time.time()
    
    try:
        user_id = UUID(request.user_id) if request.user_id else None
        session_id = UUID(request.session_id) if request.session_id else None
        
        logger.info(f"Начало генерации образа для user_id={user_id}, generate_image={request.generate_image}")
        
        async with AsyncSessionLocal() as db:
            agent = StylistAgent(db)
            available_models = _discover_digital_models()
            available_model_ids = {m["id"] for m in available_models}
            available_model_by_norm = {
                (_sanitize_model_name(m["id"]) or ""): m["id"] for m in available_models
            }

            selected_model = request.digital_model
            if selected_model:
                selected_norm = _sanitize_model_name(selected_model) or ""
                if selected_model not in available_model_ids:
                    # Принимаем model_id в любом регистре и в нормализованном виде
                    mapped = available_model_by_norm.get(selected_norm)
                    if not mapped:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Цифровая модель '{selected_model}' не найдена в static/models",
                        )
                    selected_model = mapped
            if not selected_model and available_models:
                selected_model = available_models[0]["id"]
            
            result = await agent.generate_look_for_user(
                user_id=user_id,
                session_id=session_id,
                style=request.style,
                mood=request.mood,
                persona=request.persona,
                user_request=request.user_request,
                generate_image=request.generate_image,
                use_default_model=request.use_default_model,
                digital_model=selected_model,
            )
            
            elapsed_time = time.time() - start_time
            logger.info(f"Генерация образа завершена за {elapsed_time:.2f} секунд. Look ID: {result.get('id')}")
            
            return result
    except HTTPException:
        raise
    except asyncio.TimeoutError:
        elapsed_time = time.time() - start_time
        logger.warning(f"Таймаут при генерации образа после {elapsed_time:.2f} секунд")
        raise HTTPException(
            status_code=504,
            detail="Генерация образа занимает больше времени, чем ожидалось. Образ может быть создан в фоновом режиме. Проверьте список образов через несколько минут."
        )
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.exception(f"Ошибка при генерации образа после {elapsed_time:.2f} секунд: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка при генерации образа: {str(e)}")


@router.post("/{look_id}/try-on", response_model=dict)
async def try_on_look(
    look_id: UUID,
    photo: UploadFile = File(...),
    user_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """Примерка образа на фото пользователя"""
    try:
        user_uuid = UUID(user_id) if user_id else None
        
        # Читаем фото как бинарные данные
        photo_data = await photo.read()
        
        # Используем StylistAgent для примерки
        agent = StylistAgent(db)
        
        try_on_result = await agent.try_on_look(
            look_id=look_id,
            user_photo_data=photo_data,
            user_id=user_uuid,
            filename=photo.filename
        )
        
        # Убеждаемся, что все данные сериализуемы в JSON
        from app.api.look_tryon import _make_serializable
        serializable_result = _make_serializable(try_on_result)
        
        return serializable_result
    except UnicodeDecodeError as e:
        logger.exception("Ошибка кодировки при примерке образа")
        raise HTTPException(
            status_code=400,
            detail=f"Ошибка обработки изображения: файл поврежден или имеет неверный формат"
        )
    except Exception as e:
        logger.exception("Ошибка при примерке образа")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при примерке образа: {str(e)}"
        )


@router.put("/{look_id}", response_model=dict)
async def update_look(
    look_id: UUID,
    request: LookUpdateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Обновление образа"""
    try:
        result = await db.execute(select(Look).where(Look.id == look_id))
        look = result.scalar_one_or_none()
        
        if not look:
            raise HTTPException(status_code=404, detail="Look not found")
        
        # Обновляем поля, если они указаны
        if request.name is not None:
            look.name = request.name
        if request.style is not None:
            look.style = request.style
        if request.mood is not None:
            look.mood = request.mood
        if request.style_values is not None:
            normalized = _normalize_multi_values(request.style_values, request.style)
            look.style_values = normalized
            look.style = _primary_multi_value(normalized, request.style)
        if request.mood_values is not None:
            normalized = _normalize_multi_values(request.mood_values, request.mood)
            look.mood_values = normalized
            look.mood = _primary_multi_value(normalized, request.mood)
        if request.style_dna is not None:
            look.style_dna = request.style_dna
        if request.radical is not None:
            look.radical = request.radical
        if request.style_dna_values is not None:
            normalized = _normalize_multi_values(request.style_dna_values, request.style_dna)
            look.style_dna_values = normalized
            look.style_dna = _primary_multi_value(normalized, request.style_dna)
        if request.radical_values is not None:
            normalized = _normalize_multi_values(request.radical_values, request.radical)
            look.radical_values = normalized
            look.radical = _primary_multi_value(normalized, request.radical)
        if request.description is not None:
            look.description = request.description
        if request.product_ids is not None:
            look.product_ids = request.product_ids
        if request.product_layout is not None:
            look.product_layout = request.product_layout
            _sync_look_media_items(look)
        if request.is_new is not None:
            look.is_new = request.is_new
        
        await _append_setting_list_values(
            db, "manual_look_style_options", _look_multi_value_payload(look, "style_values"), MANUAL_LOOK_OPTION_DEFAULTS["manual_look_style_options"]
        )
        await _append_setting_list_values(
            db, "manual_look_mood_options", _look_multi_value_payload(look, "mood_values"), MANUAL_LOOK_OPTION_DEFAULTS["manual_look_mood_options"]
        )
        await _append_setting_list_values(
            db, "manual_look_style_dna_options", _look_multi_value_payload(look, "style_dna_values"), MANUAL_LOOK_OPTION_DEFAULTS["manual_look_style_dna_options"]
        )
        await _append_setting_list_values(
            db, "manual_look_radical_options", _look_multi_value_payload(look, "radical_values"), MANUAL_LOOK_OPTION_DEFAULTS["manual_look_radical_options"]
        )

        # Перегенерация изображения, если запрошена
        if request.regenerate_image:
            try:
                from app.services.image_generation_service import image_generation_service
                # Устанавливаем сессию БД для сервиса
                image_generation_service.set_db_session(db)
                
                image_url = await image_generation_service.generate_look_image_from_look(
                    look_id=look_id,
                    use_default_model=request.use_default_model
                )
                if image_url:
                    look.image_url = image_url
                else:
                    logger.warning(f"Image generation returned None for look {look_id}")
            except Exception as e:
                logger.exception(f"Error regenerating image for look {look_id}: {e}")
                # Не прерываем обновление образа, если генерация изображения не удалась
                # Просто логируем ошибку
        
        await db.commit()
        await db.refresh(look)
        
        products = await _load_products_by_ids(db, look.product_ids or [])
        
        # Исправляем возможную опечатку в URL
        image_url = look.image_url
        if image_url and "/static/lcimages/" in image_url:
            image_url = image_url.replace("/static/lcimages/", "/static/look_images/")
        
        try_on_image_url = look.try_on_image_url
        if try_on_image_url and "/static/lcimages/" in try_on_image_url:
            try_on_image_url = try_on_image_url.replace("/static/lcimages/", "/static/look_images/")
        
        return {
            "id": str(look.id),
            "name": look.name,
            "product_ids": [str(pid) for pid in (look.product_ids or [])],
            "style": look.style,
            "mood": look.mood,
            "style_values": _look_multi_value_payload(look, "style_values"),
            "mood_values": _look_multi_value_payload(look, "mood_values"),
            "style_dna": look.style_dna,
            "radical": look.radical,
            "style_dna_values": _look_multi_value_payload(look, "style_dna_values"),
            "radical_values": _look_multi_value_payload(look, "radical_values"),
            "description": look.description,
            "image_url": image_url,
            "image_urls": look.image_urls or [],
            "current_image_index": look.current_image_index,
            "status": look.status,
            "approval_status": look.approval_status,
            "try_on_image_url": try_on_image_url,
            "generation_metadata": look.generation_metadata or {},
            "product_layout": look.product_layout or [],
            "source_provider": look.source_provider,
            "is_new": bool(look.is_new),
            "media_items": _look_media_items(look),
            "products": [_product_payload(p) for p in products]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Ошибка при обновлении образа")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при обновлении образа: {str(e)}")


@router.post("/{look_id}/manual-media", response_model=dict)
async def update_manual_look_media(
    look_id: UUID,
    keep_image_urls_json: str = Form("[]"),
    main_image_ref: Optional[str] = Form(None),
    ordered_image_refs_json: str = Form("[]"),
    remove_video: bool = Form(False),
    photos: Optional[List[UploadFile]] = File(None),
    video: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await db.execute(select(Look).where(Look.id == look_id))
        look = result.scalar_one_or_none()
        if not look:
            raise HTTPException(status_code=404, detail="Образ не найден")
        if (look.source_provider or "").strip().lower() not in {"manual", "real_shoot"}:
            raise HTTPException(status_code=400, detail="Редактирование медиа доступно только для ручных образов")

        try:
            keep_image_urls_raw = json.loads(keep_image_urls_json or "[]")
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Не удалось разобрать keep_image_urls") from exc
        if not isinstance(keep_image_urls_raw, list):
            raise HTTPException(status_code=400, detail="keep_image_urls должен быть массивом")
        keep_image_urls = [str(item).strip() for item in keep_image_urls_raw if str(item).strip()]
        keep_image_url_set = set(keep_image_urls)
        try:
            ordered_image_refs_raw = json.loads(ordered_image_refs_json or "[]")
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Не удалось разобрать ordered_image_refs") from exc
        if not isinstance(ordered_image_refs_raw, list):
            raise HTTPException(status_code=400, detail="ordered_image_refs должен быть массивом")
        ordered_image_refs = [str(item).strip() for item in ordered_image_refs_raw if str(item).strip()]

        current_image_items = _normalize_look_image_items(look.image_urls or [])
        current_media_items = _look_media_items(look)

        preserved_non_gallery: List[dict] = []
        for item in current_image_items:
            source = str(item.get("source") or "").strip().lower()
            url = str(item.get("url") or "").strip()
            if source == "product_gallery":
                continue
            if url and url in keep_image_url_set:
                preserved_non_gallery.append(item)

        uploaded_photo_items: List[dict] = []
        for file in photos or []:
            uploaded_url = await _save_manual_look_upload(
                file=file,
                folder="manual",
                allowed_types=LOOK_MANUAL_IMAGE_TYPES,
                max_bytes=LOOK_MANUAL_IMAGE_MAX_BYTES,
            )
            uploaded_photo_items.append({"type": "image", "url": uploaded_url, "source": "manual_upload"})

        existing_video_items: List[dict] = []
        for raw_item in current_media_items:
            if not isinstance(raw_item, dict):
                continue
            if str(raw_item.get("type") or "").strip().lower() != "video":
                continue
            url = str(raw_item.get("url") or "").strip()
            if not url:
                continue
            item = dict(raw_item)
            item["url"] = url
            item["type"] = "video"
            existing_video_items.append(item)

        next_video_items: List[dict] = [] if remove_video else existing_video_items
        if video and getattr(video, "filename", None):
            uploaded_video_url = await _save_manual_look_upload(
                file=video,
                folder="manual",
                allowed_types=LOOK_MANUAL_VIDEO_TYPES,
                max_bytes=LOOK_MANUAL_VIDEO_MAX_BYTES,
            )
            next_video_items = [{"type": "video", "url": uploaded_video_url, "source": "manual_upload"}]

        preferred_main_image_url: Optional[str] = None
        ordered_image_urls: List[str] = []
        if main_image_ref:
            if str(main_image_ref).startswith("new_upload:"):
                try:
                    upload_idx = int(str(main_image_ref).split(":", 1)[1])
                    if 0 <= upload_idx < len(uploaded_photo_items):
                        preferred_main_image_url = uploaded_photo_items[upload_idx]["url"]
                except (TypeError, ValueError):
                    preferred_main_image_url = None
            else:
                preferred_main_image_url = str(main_image_ref).strip() or None

        if ordered_image_refs:
            ref_to_url = {f"new_upload:{idx}": item["url"] for idx, item in enumerate(uploaded_photo_items)}
            for ref in ordered_image_refs:
                mapped_url = ref_to_url.get(ref, ref)
                clean_url = str(mapped_url or "").strip()
                if clean_url and clean_url not in ordered_image_urls:
                    ordered_image_urls.append(clean_url)

        _sync_look_media_items(
            look,
            non_gallery_image_items=preserved_non_gallery + uploaded_photo_items,
            video_items=next_video_items,
            preferred_main_image_url=preferred_main_image_url,
            ordered_image_urls=ordered_image_urls,
        )

        await db.commit()
        await db.refresh(look)
        products = await _load_products_by_ids(db, look.product_ids or [])
        image_url = look.image_url
        if image_url and "/static/lcimages/" in image_url:
            image_url = image_url.replace("/static/lcimages/", "/static/look_images/")
        try_on_image_url = look.try_on_image_url
        if try_on_image_url and "/static/lcimages/" in try_on_image_url:
            try_on_image_url = try_on_image_url.replace("/static/lcimages/", "/static/look_images/")

        return {
            "id": str(look.id),
            "name": look.name,
            "product_ids": [str(pid) for pid in (look.product_ids or [])],
            "style": look.style,
            "mood": look.mood,
            "style_values": _look_multi_value_payload(look, "style_values"),
            "mood_values": _look_multi_value_payload(look, "mood_values"),
            "style_dna": look.style_dna,
            "radical": look.radical,
            "style_dna_values": _look_multi_value_payload(look, "style_dna_values"),
            "radical_values": _look_multi_value_payload(look, "radical_values"),
            "description": look.description,
            "image_url": image_url,
            "image_urls": look.image_urls or [],
            "current_image_index": look.current_image_index,
            "status": look.status,
            "approval_status": look.approval_status,
            "try_on_image_url": try_on_image_url,
            "generation_metadata": look.generation_metadata or {},
            "product_layout": look.product_layout or [],
            "source_provider": look.source_provider,
            "is_new": bool(look.is_new),
            "media_items": _look_media_items(look),
            "products": [_product_payload(p) for p in products],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Ошибка при обновлении медиа ручного образа")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при обновлении медиа образа: {str(e)}")


@router.delete("/{look_id}", response_model=dict)
async def delete_look(look_id: UUID, db: AsyncSession = Depends(get_db)):
    """Удаление образа"""
    try:
        result = await db.execute(select(Look).where(Look.id == look_id))
        look = result.scalar_one_or_none()
        
        if not look:
            raise HTTPException(status_code=404, detail="Look not found")
        
        await db.delete(look)
        await db.commit()
        
        return {"success": True, "message": f"Look {look_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Ошибка при удалении образа")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при удалении образа: {str(e)}")


@router.delete("/", response_model=dict)
async def delete_test_looks(
    confirm: bool = Query(False, description="Подтверждение удаления всех тестовых образов"),
    db: AsyncSession = Depends(get_db)
):
    """Удаление всех тестовых образов"""
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Для удаления всех тестовых образов необходимо установить confirm=true"
        )
    
    try:
        # Удаляем тестовые образы по именам
        test_look_names = [
            "Романтичный вечер",
            "Повседневный стиль"
        ]
        
        result = await db.execute(
            select(Look).where(Look.name.in_(test_look_names))
        )
        test_looks = result.scalars().all()
        
        deleted_count = 0
        for look in test_looks:
            await db.delete(look)
            deleted_count += 1
        
        await db.commit()
        
        return {
            "success": True,
            "message": f"Удалено тестовых образов: {deleted_count}",
            "deleted_count": deleted_count
        }
    except Exception as e:
        logger.exception("Ошибка при удалении тестовых образов")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при удалении тестовых образов: {str(e)}")


@router.post("/{look_id}/generate-image", response_model=dict)
async def generate_look_image_endpoint(
    look_id: UUID,
    use_default_model: bool = Query(False),
    digital_model: Optional[str] = Query(None, description="ID цифровой модели"),
    db: AsyncSession = Depends(get_db)
):
    """Генерация изображения для существующего образа"""
    from app.services.image_generation_service import image_generation_service
    
    try:
        result = await db.execute(select(Look).where(Look.id == look_id))
        look = result.scalar_one_or_none()
        if not look:
            raise HTTPException(status_code=404, detail="Образ не найден")

        await _ensure_look_has_catalog_products(db, look, require_image_refs=True)

        image_url = await image_generation_service.generate_look_image_from_look(
            look_id=look_id,
            use_default_model=use_default_model,
            digital_model=digital_model,
        )
        
        if not image_url:
            raise HTTPException(status_code=404, detail="Образ не найден или не удалось сгенерировать изображение")
        
        # Обновляем образ с URL изображения
        if look:
            # Добавляем новое изображение в массив image_urls
            if look.image_urls is None:
                look.image_urls = []
            
            # Создаем объект изображения с метаданными
            image_data = {
                "url": image_url,
                "generated_at": datetime.now().isoformat(),
                "use_default_model": use_default_model
            }
            
            look.image_urls.append(image_data)
            
            # Устанавливаем новое изображение как текущее
            look.current_image_index = len(look.image_urls) - 1
            
            # Обновляем image_url для обратной совместимости
            look.image_url = image_url
            
            await db.commit()
            await db.refresh(look)
        
        return {
            "look_id": str(look_id),
            "image_url": image_url,
            "image_urls": look.image_urls if look else [],
            "current_image_index": look.current_image_index if look else None,
            "use_default_model": use_default_model
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Ошибка при генерации изображения образа")
        raise HTTPException(status_code=500, detail=f"Ошибка при генерации изображения: {str(e)}")


@router.post("/{look_id}/approve", response_model=dict)
async def approve_look(
    look_id: UUID,
    user_id: Optional[str] = Query(None)
):
    """Одобрение сгенерированного образа"""
    try:
        user_uuid = UUID(user_id) if user_id else None
        
        async with AsyncSessionLocal() as db:
            agent = StylistAgent(db)
            
            result = await agent.approve_look(
                look_id=look_id,
                user_id=user_uuid
            )
            
            if not result:
                raise HTTPException(status_code=404, detail="Образ не найден")
            
            return {
                "look_id": str(look_id),
                "approval_status": result.approval_status,
                "status": result.status
            }
    except Exception as e:
        logger.exception("Ошибка при одобрении образа")
        raise HTTPException(status_code=500, detail=f"Ошибка при одобрении образа: {str(e)}")


@router.put("/{look_id}/set-main-image", response_model=dict)
async def set_main_image(
    look_id: UUID,
    image_index: int = Query(..., ge=0, description="Индекс изображения в массиве image_urls"),
    db: AsyncSession = Depends(get_db)
):
    """Установка основного изображения образа"""
    try:
        result = await db.execute(select(Look).where(Look.id == look_id))
        look = result.scalar_one_or_none()
        
        if not look:
            raise HTTPException(status_code=404, detail="Look not found")
        
        if not look.image_urls or len(look.image_urls) == 0:
            raise HTTPException(status_code=400, detail="У образа нет изображений")
        
        if image_index >= len(look.image_urls):
            raise HTTPException(status_code=400, detail=f"Индекс {image_index} выходит за пределы массива изображений")
        
        look.current_image_index = image_index
        
        # Обновляем image_url для обратной совместимости
        image_data = look.image_urls[image_index]
        if isinstance(image_data, dict):
            look.image_url = image_data.get("url")
        else:
            look.image_url = image_data
        
        await db.commit()
        await db.refresh(look)
        
        return {
            "success": True,
            "look_id": str(look_id),
            "current_image_index": look.current_image_index,
            "image_url": look.image_url
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Ошибка при установке основного изображения")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при установке основного изображения: {str(e)}")


@router.delete("/{look_id}/image/{image_index}", response_model=dict)
async def delete_look_image(
    look_id: UUID,
    image_index: int,
    db: AsyncSession = Depends(get_db)
):
    """Удаление изображения из образа"""
    try:
        result = await db.execute(select(Look).where(Look.id == look_id))
        look = result.scalar_one_or_none()
        
        if not look:
            raise HTTPException(status_code=404, detail="Look not found")
        
        if not look.image_urls or len(look.image_urls) == 0:
            raise HTTPException(status_code=400, detail="У образа нет изображений")
        
        if image_index >= len(look.image_urls):
            raise HTTPException(status_code=400, detail=f"Индекс {image_index} выходит за пределы массива изображений")
        
        # Удаляем изображение
        look.image_urls.pop(image_index)
        
        # Обновляем current_image_index
        if look.current_image_index is not None:
            if look.current_image_index >= len(look.image_urls):
                # Если удалили текущее или последующее, устанавливаем последнее
                look.current_image_index = len(look.image_urls) - 1 if len(look.image_urls) > 0 else None
            elif look.current_image_index > image_index:
                # Если удалили изображение до текущего, уменьшаем индекс
                look.current_image_index -= 1
        
        # Обновляем image_url для обратной совместимости
        if look.image_urls and len(look.image_urls) > 0 and look.current_image_index is not None:
            image_data = look.image_urls[look.current_image_index]
            if isinstance(image_data, dict):
                look.image_url = image_data.get("url")
            else:
                look.image_url = image_data
        else:
            look.image_url = None
            look.current_image_index = None
        
        await db.commit()
        await db.refresh(look)
        
        return {
            "success": True,
            "look_id": str(look_id),
            "remaining_images": len(look.image_urls),
            "current_image_index": look.current_image_index
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Ошибка при удалении изображения")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при удалении изображения: {str(e)}")
