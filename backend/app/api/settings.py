from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.database.connection import get_db
from app.models.app_setting import AppSetting
import os
import time
import httpx
from typing import Any, Dict, List, Optional, TypedDict
import asyncio


router = APIRouter()


class ModelSettingsResponse(BaseModel):
    default_model: str
    source: str  # db | env | default


class ImageGenerationModelSettingsResponse(BaseModel):
    image_generation_model: str
    source: str  # db | env | default


class ModelSettingsUpdateRequest(BaseModel):
    default_model: str


class ImageGenerationModelSettingsUpdateRequest(BaseModel):
    image_generation_model: str


class OpenRouterModelPricing(TypedDict, total=False):
    prompt: str
    completion: str


class OpenRouterModel(TypedDict, total=False):
    id: str
    name: str
    context_length: int
    pricing: OpenRouterModelPricing


class OpenRouterModelsResponse(BaseModel):
    models: List[Dict[str, Any]]
    cached: bool = False
    fetched_at: float


# simple in-memory cache (per process)
_models_cache: Optional[List[Dict[str, Any]]] = None
_models_cache_ts: float = 0.0
_MODELS_CACHE_TTL_SEC = 60 * 60  # 1 hour


async def _ensure_app_settings_table(session: AsyncSession) -> None:
    """
    Dev-friendly safety net: if migrations haven't been applied yet, create app_settings table on the fly.
    This unblocks Settings UI on fresh DBs. Alembic migration still exists for proper environments.
    """
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


@router.get("/model", response_model=ModelSettingsResponse)
async def get_model_settings():
    """
    Возвращает текущую модель LLM (OpenRouter model id), используемую по умолчанию.
    """
    # Пытаемся прочитать из БД, но не блокируем UI, если БД/миграции/коннект сейчас нестабильны.
    try:
        from app.database.connection import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            try:
                result = await session.execute(select(AppSetting).where(AppSetting.key == "default_model"))
            except Exception as e:
                # Если таблицы нет (миграции не применены) — создаём и пробуем снова
                msg = str(e).lower()
                if "app_settings" in msg and ("does not exist" in msg or "undefinedtable" in msg):
                    await _ensure_app_settings_table(session)
                    result = await session.execute(select(AppSetting).where(AppSetting.key == "default_model"))
                else:
                    raise

            setting = result.scalar_one_or_none()
            if setting and setting.value:
                return ModelSettingsResponse(default_model=str(setting.value), source="db")
    except (Exception, asyncio.CancelledError):
        # например: таблица еще не создана, DB не поднята, отмена задач при reload и т.п.
        pass

    env_model = os.getenv("DEFAULT_MODEL")
    if env_model:
        return ModelSettingsResponse(default_model=env_model, source="env")

    return ModelSettingsResponse(default_model="anthropic/claude-3.5-sonnet", source="default")


@router.put("/model", response_model=ModelSettingsResponse)
async def set_model_settings(request: ModelSettingsUpdateRequest, db: AsyncSession = Depends(get_db)):
    """
    Устанавливает DEFAULT_MODEL в БД (настройка применяется без правки .env).
    """
    model = (request.default_model or "").strip()
    if not model or "/" not in model:
        raise HTTPException(
            status_code=400,
            detail="default_model должен быть строкой вида 'provider/model', например 'openai/gpt-4o-mini'.",
        )

    try:
        # safety net: create table if missing (unconditionally, cheap + idempotent)
        await _ensure_app_settings_table(db)

        result = await db.execute(select(AppSetting).where(AppSetting.key == "default_model"))
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = model
        else:
            setting = AppSetting(key="default_model", value=model)
            db.add(setting)

        await db.commit()
        return ModelSettingsResponse(default_model=model, source="db")
    except Exception as e:
        # чаще всего: таблица app_settings ещё не создана (не применили миграции)
        raise HTTPException(
            status_code=500,
            detail=(
                f"Не удалось сохранить настройку в БД: {str(e)}. "
                "Скорее всего, миграции ещё не применены (таблица app_settings отсутствует). "
                "Запустите alembic upgrade head и перезапустите backend."
            ),
        )


@router.get("/openrouter/models", response_model=OpenRouterModelsResponse)
async def list_openrouter_models(force_refresh: bool = False):
    """
    Прокси к OpenRouter `GET /api/v1/models`.

    Важно: ключ хранится на backend (OPENROUTER_API_KEY), фронт его не видит.
    """
    global _models_cache, _models_cache_ts

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="OPENROUTER_API_KEY не установлен на backend. Добавьте ключ и перезапустите backend.",
        )

    now = time.time()
    if (not force_refresh) and _models_cache and (now - _models_cache_ts) < _MODELS_CACHE_TTL_SEC:
        return OpenRouterModelsResponse(models=_models_cache, cached=True, fetched_at=_models_cache_ts)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://glame.ai",
        "X-Title": "GLAME AI Platform",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get("https://openrouter.ai/api/v1/models", headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        detail = (e.response.text or "")[:500]
        raise HTTPException(status_code=502, detail=f"OpenRouter error: HTTP {e.response.status_code}. {detail}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenRouter models fetch failed: {str(e)}")

    raw_models: List[Dict[str, Any]] = list((data or {}).get("data") or [])
    
    # normalize / shrink payload for frontend
    normalized: List[Dict[str, Any]] = []
    for m in raw_models:
        pricing = m.get("pricing") or {}
        normalized.append(
            {
                "id": m.get("id"),
                "name": m.get("name"),
                "context_length": m.get("context_length"),
                "type": m.get("type"),  # Сохраняем тип для фильтрации
                "pricing": {
                    "prompt": pricing.get("prompt"),
                    "completion": pricing.get("completion"),
                },
            }
        )

    _models_cache = normalized
    _models_cache_ts = now
    return OpenRouterModelsResponse(models=normalized, cached=False, fetched_at=now)


@router.get("/openrouter/image-models", response_model=OpenRouterModelsResponse)
async def list_openrouter_image_models(force_refresh: bool = False):
    """
    Получение списка моделей для генерации изображений из OpenRouter.
    Фильтрует только модели, которые поддерживают генерацию изображений.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    global _models_cache, _models_cache_ts
    
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="OPENROUTER_API_KEY не установлен на backend. Добавьте ключ и перезапустите backend.",
        )
    
    now = time.time()
    # Для моделей изображений всегда делаем свежий запрос или используем кэш только если он недавний
    # Но фильтруем из кэша только если он есть
    use_cache = (not force_refresh) and _models_cache and (now - _models_cache_ts) < _MODELS_CACHE_TTL_SEC
    
    if use_cache:
        # Фильтруем из кэша
        image_models = _filter_image_generation_models(_models_cache)
        logger.info(f"Returning {len(image_models)} image models from cache")
        return OpenRouterModelsResponse(models=image_models, cached=True, fetched_at=_models_cache_ts)
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://glame.ai",
        "X-Title": "GLAME AI Platform",
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get("https://openrouter.ai/api/v1/models", headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        detail = (e.response.text or "")[:500]
        logger.error(f"OpenRouter API error: {e.response.status_code} - {detail}")
        raise HTTPException(status_code=502, detail=f"OpenRouter error: HTTP {e.response.status_code}. {detail}")
    except Exception as e:
        logger.error(f"OpenRouter models fetch failed: {str(e)}")
        raise HTTPException(status_code=502, detail=f"OpenRouter models fetch failed: {str(e)}")
    
    raw_models: List[Dict[str, Any]] = list((data or {}).get("data") or [])
    logger.info(f"Received {len(raw_models)} total models from OpenRouter")
    
    # Фильтруем модели для генерации изображений
    image_models_raw = _filter_image_generation_models_raw(raw_models)
    logger.info(f"Filtered to {len(image_models_raw)} image generation models")
    
    if not image_models_raw:
        logger.warning("No image generation models found! This might indicate a filtering issue.")
        # Возвращаем пустой список, но не ошибку - пользователь может ввести модель вручную
    
    # normalize / shrink payload for frontend
    normalized: List[Dict[str, Any]] = []
    for m in image_models_raw:
        pricing = m.get("pricing") or {}
        normalized.append(
            {
                "id": m.get("id"),
                "name": m.get("name"),
                "context_length": m.get("context_length"),
                "type": m.get("type"),  # Сохраняем тип для отладки
                "pricing": {
                    "prompt": pricing.get("prompt"),
                    "completion": pricing.get("completion"),
                },
            }
        )
    
    logger.info(f"Normalized {len(normalized)} image generation models")
    
    # Сортируем: сначала популярные провайдеры (Black Forest Labs, Google, OpenAI), потом по имени
    def sort_key(model: Dict[str, Any]) -> tuple:
        id_str = str(model.get("id", "")).lower()
        name_str = str(model.get("name", "")).lower()
        
        # Приоритеты провайдеров
        if "black-forest" in id_str or "flux" in id_str:
            priority = 0
        elif "google" in id_str or "nano" in id_str:
            priority = 1
        elif "openai" in id_str or "dall" in id_str:
            priority = 2
        else:
            priority = 3
        
        return (priority, name_str)
    
    normalized.sort(key=sort_key)
    
    return OpenRouterModelsResponse(models=normalized, cached=False, fetched_at=now)


def _filter_image_generation_models_raw(raw_models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Фильтрует модели для генерации изображений из сырого списка OpenRouter.
    
    Критерии:
    - Модели с типом "image" или "image-generation"
    - Модели с названиями, содержащими ключевые слова: flux, dall-e, nano, image, generation
    - Модели от известных провайдеров генерации изображений
    """
    import logging
    logger = logging.getLogger(__name__)
    
    image_keywords = [
        "flux", "dall", "nano", "image", "generation", "stable-diffusion",
        "midjourney", "imagen", "cogview", "wombo", "artbreeder", "banana",
        "imagen-3", "imagen-2", "kandinsky", "leonardo", "playground"
    ]
    
    image_providers = [
        "black-forest-labs", "google", "openai", "stability-ai",
        "replicate", "fal", "together", "anyscale", "deepinfra"
    ]
    
    # Исключаем текстовые модели
    text_model_keywords = ["gpt", "claude", "llama", "gemini-text", "chat", "completion", "text", "sonnet", "opus"]
    
    filtered = []
    sample_models = []  # Для отладки
    
    for model in raw_models:
        model_id = str(model.get("id", "")).lower()
        model_name = str(model.get("name", "")).lower()
        model_type = str(model.get("type", "")).lower()
        
        # Сохраняем несколько примеров для отладки
        if len(sample_models) < 5:
            sample_models.append(f"{model_id} (type: {model_type})")
        
        # Проверяем тип модели
        if model_type in ["image", "image-generation", "image_generation", "image_generation_model"]:
            filtered.append(model)
            logger.debug(f"Added model by type: {model_id}")
            continue
        
        # Исключаем явно текстовые модели
        is_text_model = any(text_kw in model_id or text_kw in model_name for text_kw in text_model_keywords)
        if is_text_model:
            # Но пропускаем если это явно модель для изображений
            if "image" not in model_id and "image" not in model_name:
                continue
        
        # Проверяем по ключевым словам в ID или названии
        if any(keyword in model_id or keyword in model_name for keyword in image_keywords):
            filtered.append(model)
            logger.debug(f"Added model by keyword: {model_id}")
            continue
        
        # Проверяем по провайдеру (более мягкая проверка)
        provider_match = any(provider in model_id for provider in image_providers)
        if provider_match:
            # Для провайдеров генерации изображений проверяем, что это не текстовая модель
            is_text = any(text_kw in model_id for text_kw in ["gpt", "claude", "llama", "gemini-text", "chat", "sonnet", "opus"])
            if not is_text:
                filtered.append(model)
                logger.debug(f"Added model by provider: {model_id}")
                continue
    
    logger.info(f"Filtered {len(filtered)} image generation models from {len(raw_models)} total models")
    if len(filtered) == 0:
        logger.warning(f"No image models found! Sample models from API: {sample_models[:10]}")
        # Если ничего не найдено, попробуем более мягкую фильтрацию - ищем по известным ID моделей
        known_image_models = [
            "black-forest-labs/flux",
            "google/nano",
            "openai/dall-e",
            "stability-ai/stable-diffusion"
        ]
        for model in raw_models:
            model_id = str(model.get("id", "")).lower()
            if any(known in model_id for known in known_image_models):
                if model not in filtered:
                    filtered.append(model)
                    logger.info(f"Added known image model: {model_id}")
    
    return filtered


def _filter_image_generation_models(normalized_models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Фильтрует нормализованные модели для генерации изображений"""
    import logging
    logger = logging.getLogger(__name__)
    
    image_keywords = [
        "flux", "dall", "nano", "image", "generation", "stable-diffusion",
        "banana", "imagen", "kandinsky", "leonardo", "playground"
    ]
    
    text_model_keywords = ["gpt", "claude", "llama", "gemini-text", "chat", "completion", "text", "sonnet", "opus"]
    
    filtered = []
    for model in normalized_models:
        model_id = str(model.get("id", "")).lower()
        model_name = str(model.get("name", "")).lower()
        model_type = str(model.get("type", "")).lower()
        
        # Проверяем тип модели
        if model_type in ["image", "image-generation", "image_generation", "image_generation_model"]:
            filtered.append(model)
            continue
        
        # Исключаем текстовые модели
        is_text = any(text_kw in model_id or text_kw in model_name for text_kw in text_model_keywords)
        if is_text and "image" not in model_id and "image" not in model_name:
            continue
        
        # Проверяем по ключевым словам
        if any(keyword in model_id or keyword in model_name for keyword in image_keywords):
            filtered.append(model)
            continue
        
        # Проверяем провайдеров
        image_providers = ["black-forest-labs", "google/nano", "openai/dall"]
        if any(provider in model_id for provider in image_providers):
            if not any(text_kw in model_id for text_kw in ["gpt", "claude", "llama", "gemini-text", "chat"]):
                filtered.append(model)
    
    logger.info(f"Filtered {len(filtered)} image models from {len(normalized_models)} normalized models")
    
    # Сортируем
    def sort_key(model: Dict[str, Any]) -> tuple:
        id_str = str(model.get("id", "")).lower()
        name_str = str(model.get("name", "")).lower()
        
        if "black-forest" in id_str or "flux" in id_str:
            priority = 0
        elif "google" in id_str or "nano" in id_str:
            priority = 1
        elif "openai" in id_str or "dall" in id_str:
            priority = 2
        else:
            priority = 3
        
        return (priority, name_str)
    
    filtered.sort(key=sort_key)
    return filtered


@router.get("/image-generation-model", response_model=ImageGenerationModelSettingsResponse)
async def get_image_generation_model_settings():
    """Возвращает текущую модель для генерации изображений"""
    try:
        from app.database.connection import AsyncSessionLocal
        
        async with AsyncSessionLocal() as session:
            try:
                result = await session.execute(
                    select(AppSetting).where(AppSetting.key == "image_generation_model")
                )
            except Exception as e:
                msg = str(e).lower()
                if "app_settings" in msg and ("does not exist" in msg or "undefinedtable" in msg):
                    await _ensure_app_settings_table(session)
                    result = await session.execute(
                        select(AppSetting).where(AppSetting.key == "image_generation_model")
                    )
                else:
                    raise
            
            setting = result.scalar_one_or_none()
            if setting and setting.value:
                return ImageGenerationModelSettingsResponse(
                    image_generation_model=str(setting.value), source="db"
                )
    except (Exception, asyncio.CancelledError):
        pass
    
    env_model = os.getenv("IMAGE_GENERATION_MODEL")
    if env_model:
        return ImageGenerationModelSettingsResponse(image_generation_model=env_model, source="env")
    
    return ImageGenerationModelSettingsResponse(
        image_generation_model="black-forest-labs/flux-pro", source="default"
    )


@router.put("/image-generation-model", response_model=ImageGenerationModelSettingsResponse)
async def set_image_generation_model_settings(
    request: ImageGenerationModelSettingsUpdateRequest, db: AsyncSession = Depends(get_db)
):
    """Устанавливает модель для генерации изображений в БД"""
    model = (request.image_generation_model or "").strip()
    if not model or "/" not in model:
        raise HTTPException(
            status_code=400,
            detail="image_generation_model должен быть строкой вида 'provider/model', например 'black-forest-labs/flux-pro'.",
        )
    
    try:
        await _ensure_app_settings_table(db)
        
        result = await db.execute(
            select(AppSetting).where(AppSetting.key == "image_generation_model")
        )
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = model
        else:
            setting = AppSetting(key="image_generation_model", value=model)
            db.add(setting)
        
        await db.commit()
        return ImageGenerationModelSettingsResponse(image_generation_model=model, source="db")
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Не удалось сохранить настройку в БД: {str(e)}. "
                "Скорее всего, миграции ещё не применены (таблица app_settings отсутствует). "
                "Запустите alembic upgrade head и перезапустите backend."
            ),
        )

