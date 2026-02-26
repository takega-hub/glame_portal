from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List, Optional, Any
from uuid import UUID
from datetime import datetime
import logging
import asyncio
import time
import re
from pathlib import Path
from urllib.parse import unquote

from app.database.connection import get_db, AsyncSessionLocal
from app.models.look import Look
from app.models.content_item import ContentItem
from app.models.product import Product
from app.agents.stylist_agent import StylistAgent

logger = logging.getLogger(__name__)

router = APIRouter()


class LookResponse(BaseModel):
    id: str
    name: str
    product_ids: List[str]
    style: str | None = None
    mood: str | None = None
    description: str | None = None
    image_url: str | None = None


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


def _discover_digital_models() -> List[dict]:
    models_root = Path("static/models")
    if not models_root.exists():
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
    look_model_dir = Path("static/look_images/models") / model_norm
    if look_model_dir.exists():
        for file_path in sorted(look_model_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if file_path.is_file() and file_path.suffix.lower() in exts:
                add_url(f"/static/look_images/models/{model_norm}/{file_path.name}")

    look_images_dir = Path("static/look_images")
    if look_images_dir.exists():
        for file_path in sorted(look_images_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not file_path.is_file() or file_path.suffix.lower() not in exts:
                continue
            stem_norm = _sanitize_model_name(file_path.stem) or ""
            if model_norm and model_norm in stem_norm:
                add_url(f"/static/look_images/{file_path.name}")

    content_images_dir = Path("static/content_post_images")
    if content_images_dir.exists():
        for file_path in sorted(content_images_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not file_path.is_file() or file_path.suffix.lower() not in exts:
                continue
            stem_norm = _sanitize_model_name(file_path.stem) or ""
            if model_norm and model_norm in stem_norm:
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
    base = Path("static").resolve()
    target = (base / rel_path).resolve()
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
    description: Optional[str] = None
    product_ids: Optional[List[str]] = None
    regenerate_image: bool = False
    use_default_model: bool = False


@router.get("/", response_model=List[LookResponse])
async def get_looks(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    style: Optional[str] = None,
    mood: Optional[str] = None,
    digital_model: Optional[str] = Query(None, description="ID цифровой модели для фильтрации портфолио"),
    db: AsyncSession = Depends(get_db)
):
    query = select(Look)
    
    if style:
        query = query.where(Look.style == style)
    if mood:
        query = query.where(Look.mood == mood)
    
    if not digital_model:
        query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    looks = list(result.scalars().all())

    if digital_model:
        digital_model_norm = _sanitize_model_name(digital_model)
        filtered = []
        for look in looks:
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
            "description": look.description,
            "image_url": image_url,
            "image_urls": look.image_urls or [],
            "current_image_index": look.current_image_index,
            "status": look.status,
            "approval_status": look.approval_status,
            "try_on_image_url": try_on_image_url,
            "generation_metadata": look.generation_metadata or {},
        }
        looks_list.append(look_dict)
    
    return looks_list


@router.get("/models", response_model=List[DigitalModelInfo])
async def get_digital_models(db: AsyncSession = Depends(get_db)):
    """Список цифровых моделей (ядро + статистика портфолио)"""
    models = _discover_digital_models()
    if not models:
        return []

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

    # 1) Чистим ссылки в looks по модели
    for look in looks:
        metadata = look.generation_metadata or {}
        look_model = _sanitize_model_name(metadata.get("digital_model"))
        if look_model != model_norm:
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


@router.get("/{look_id}", response_model=dict)
async def get_look(look_id: UUID, db: AsyncSession = Depends(get_db)):
    """Получение образа с продуктами"""
    try:
        result = await db.execute(select(Look).where(Look.id == look_id))
        look = result.scalar_one_or_none()
        if not look:
            raise HTTPException(status_code=404, detail="Look not found")

        await _ensure_look_has_catalog_products(db, look, require_image_refs=True)
        
        # Получаем продукты для образа
        from app.agents.stylist_agent import StylistAgent
        stylist_agent = StylistAgent(db)
        products = await stylist_agent.recommendation_service.get_look_products(look.id)
        
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
            "description": look.description,
            "image_url": image_url,
            "image_urls": look.image_urls or [],
            "current_image_index": look.current_image_index,
            "status": look.status,
            "approval_status": look.approval_status,
            "try_on_image_url": try_on_image_url,
            "generation_metadata": look.generation_metadata or {},
            "products": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "brand": p.brand,
                    "price": p.price,
                    "images": p.images if p.images is not None else [],
                    "category": p.category,
                    "tags": p.tags if p.tags is not None else []
                }
                for p in products
            ]
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
        if request.description is not None:
            look.description = request.description
        if request.product_ids is not None:
            look.product_ids = request.product_ids
        
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
        
        # Получаем продукты для ответа
        try:
            stylist_agent = StylistAgent(db)
            products = await stylist_agent.recommendation_service.get_look_products(look.id)
        except Exception as e:
            logger.warning(f"Error loading products for look {look_id}: {e}")
            products = []
        
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
            "description": look.description,
            "image_url": image_url,
            "status": look.status,
            "approval_status": look.approval_status,
            "try_on_image_url": try_on_image_url,
            "generation_metadata": look.generation_metadata or {},
            "products": [
                {
                    "id": str(p.id),
                    "name": p.name or "",
                    "brand": p.brand or None,
                    "price": float(p.price) if p.price else 0.0,
                    "images": p.images if p.images is not None else [],
                    "category": p.category or None,
                    "tags": p.tags if p.tags is not None else []
                }
                for p in products
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Ошибка при обновлении образа")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка при обновлении образа: {str(e)}")


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
