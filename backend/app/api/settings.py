from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
import json
from app.database.connection import get_db
from app.models.app_setting import AppSetting
from app.models.user import User
from app.api.dependencies import require_admin
from app.services.gift_certificate_email_service import (
    EMAIL_SERVER_SETTING_KEY,
    GiftCertificateEmailService,
    load_smtp_settings,
    public_smtp_settings,
)
from app.services.image_optimization import run_image_optimization
from app.services.ai_core_runtime import SUPPORTED_AI_CORE_RUNTIMES, ai_core_runtime_from_env, get_ai_core_runtime
from app.services.hermes_agent_runtime import HermesAgentRuntime, hermes_runtime_config_from_env
import os
import time
import httpx
from typing import Any, Dict, List, Optional, TypedDict
import asyncio
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path


router = APIRouter()


class ModelSettingsResponse(BaseModel):
    default_model: str
    source: str  # db | env | default


class AiCoreSettingsResponse(BaseModel):
    ai_core_runtime: str
    source: str  # db | env | default
    options: List[str]


class AiRuntimeInfoResponse(BaseModel):
    ai_core_runtime: str
    source: str
    agent_id: str
    model: str
    profile: Optional[str] = None
    label: str


class ImageGenerationModelSettingsResponse(BaseModel):
    image_generation_model: str
    source: str  # db | env | default


class ModelSettingsUpdateRequest(BaseModel):
    default_model: str


class AiCoreSettingsUpdateRequest(BaseModel):
    ai_core_runtime: str


class ImageGenerationModelSettingsUpdateRequest(BaseModel):
    image_generation_model: str


class AiStylistSettingsResponse(BaseModel):
    enabled: bool
    source: str  # db | default


class AiStylistSettingsUpdateRequest(BaseModel):
    enabled: bool


class EmailServerSettingsResponse(BaseModel):
    host: str
    port: int
    username: str = ""
    from_email: str
    from_name: str
    use_ssl: bool
    use_starttls: bool
    password_set: bool
    source: str


class EmailServerSettingsUpdateRequest(BaseModel):
    host: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)
    username: Optional[str] = None
    password: Optional[str] = None
    from_email: str = Field(min_length=3)
    from_name: str = "GLAME Jewelry"
    use_ssl: bool = False
    use_starttls: bool = True


class EmailServerTestRequest(BaseModel):
    to_email: str = Field(min_length=3)


class EmailServerTestResponse(BaseModel):
    ok: bool
    message: str


class ImageOptimizationStatusResponse(BaseModel):
    status: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    scanned_files: int = 0
    eligible_files: int = 0
    optimized_files: int = 0
    skipped_small_files: int = 0
    failed_files: int = 0
    scanned_bytes: int = 0
    optimized_original_bytes: int = 0
    optimized_result_bytes: int = 0
    saved_bytes: int = 0
    changed_extensions: int = 0
    db_rows_updated: int = 0
    min_original_bytes: int = 150 * 1024
    format: str = "keep"
    quality: int = 82
    max_side: int = 1800
    dirs: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    message: Optional[str] = None


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

class OpenRouterKeyInfo(BaseModel):
    data: Dict[str, Any]

class OpenRouterUsagePoint(BaseModel):
    date: str
    total_cost: float
    requests: int

class OpenRouterUsageResponse(BaseModel):
    days: int
    by_day: List[OpenRouterUsagePoint]
    by_model: List[Dict[str, Any]]
    by_purpose: List[Dict[str, Any]] = []


class OpenRouterCreditsInfo(BaseModel):
    total_credits: float
    total_usage: float
    remaining_credits: float
    cached: bool = False
    fetched_at: float


# simple in-memory cache (per process)
_models_cache: Optional[List[Dict[str, Any]]] = None
_models_cache_ts: float = 0.0
_MODELS_CACHE_TTL_SEC = 60 * 60  # 1 hour

_credits_cache: Optional[OpenRouterCreditsInfo] = None
_credits_cache_ts: float = 0.0
_CREDITS_CACHE_TTL_SEC = 60.0
_stats_cache: Dict[str, Dict[str, Any]] = {}
_stats_cache_ts: Dict[str, float] = {}
_STATS_CACHE_TTL_SEC = 60.0
_STATS_CACHE_TTL_SEC_TODAY = 10.0

_image_optimization_lock = asyncio.Lock()
_image_optimization_task: Optional[asyncio.Task[Any]] = None


def _default_image_optimization_state() -> Dict[str, Any]:
    return {
        "status": "idle",
        "started_at": None,
        "finished_at": None,
        "scanned_files": 0,
        "eligible_files": 0,
        "optimized_files": 0,
        "skipped_small_files": 0,
        "failed_files": 0,
        "scanned_bytes": 0,
        "optimized_original_bytes": 0,
        "optimized_result_bytes": 0,
        "saved_bytes": 0,
        "changed_extensions": 0,
        "db_rows_updated": 0,
        "min_original_bytes": 150 * 1024,
        "format": "keep",
        "quality": int(os.getenv("IMAGE_OPTIMIZE_QUALITY", "82")),
        "max_side": int(os.getenv("IMAGE_OPTIMIZE_MAX_SIDE", "1800")),
        "dirs": [],
        "errors": [],
        "message": None,
    }


_image_optimization_state: Dict[str, Any] = _default_image_optimization_state()


async def _run_image_optimization_job(started_at: str) -> None:
    global _image_optimization_task, _image_optimization_state

    repo_root = Path(__file__).resolve().parents[3]
    quality = int(os.getenv("IMAGE_OPTIMIZE_QUALITY", "82"))
    max_side = int(os.getenv("IMAGE_OPTIMIZE_MAX_SIDE", "1800"))

    try:
        summary, _details = await asyncio.to_thread(
            run_image_optimization,
            root=repo_root,
            fmt="keep",
            quality=quality,
            max_side=max_side,
            min_saving_pct=5.0,
            min_saving_bytes=20 * 1024,
            min_original_bytes=150 * 1024,
        )
        async with _image_optimization_lock:
            _image_optimization_state = {
                **summary.to_dict(),
                "status": "completed",
                "started_at": started_at,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "message": (
                    f"Оптимизация завершена: обработано {summary.optimized_files} файлов, "
                    f"освобождено {round(summary.saved_bytes / 1024 / 1024, 2)} MB."
                ),
            }
    except Exception as exc:
        logging.getLogger(__name__).exception("Image optimization failed")
        async with _image_optimization_lock:
            _image_optimization_state = {
                **_default_image_optimization_state(),
                "status": "failed",
                "started_at": started_at,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "message": f"Оптимизация завершилась с ошибкой: {exc}",
                "errors": [str(exc)],
            }
    finally:
        async with _image_optimization_lock:
            _image_optimization_task = None

def _aggregate_by_model_from_local_log(day_iso: str) -> Dict[str, float]:
    """
    day_iso: 'YYYY-MM-DD' по МСК
    Читает локальный журнал OPENROUTER_COST_LOG_PATH (jsonl) и суммирует cost по моделям за указанный день (МСК).
    """
    log_path = os.getenv("OPENROUTER_COST_LOG_PATH", "/tmp/openrouter_costs.jsonl")
    if not os.path.exists(log_path):
        return {}
    try:
        from zoneinfo import ZoneInfo
        msk = ZoneInfo("Europe/Moscow")
        # Границы дня в МСК -> UTC timestamp
        day_dt = datetime.fromisoformat(day_iso)
        start_msk = datetime(day_dt.year, day_dt.month, day_dt.day, 0, 0, 0, tzinfo=msk)
        end_msk = start_msk + timedelta(days=1)
        start_utc_ts = start_msk.astimezone(timezone.utc).timestamp()
        end_utc_ts = end_msk.astimezone(timezone.utc).timestamp()
        by_model: Dict[str, float] = {}
        import json
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                ts = rec.get("ts")
                if ts is None:
                    # поддержка записей с created_at (ISO)
                    created_at = rec.get("created_at")
                    if created_at:
                        try:
                            # created_at может быть с TZ; приводим к epoch
                            tdt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
                            ts = tdt.timestamp()
                        except Exception:
                            continue
                    else:
                        continue
                try:
                    ts = float(ts)
                except Exception:
                    continue
                if ts < start_utc_ts or ts >= end_utc_ts:
                    continue
                model = str(rec.get("model") or "unknown")
                cost = rec.get("cost")
                try:
                    cost = float(cost or 0.0)
                except Exception:
                    cost = 0.0
                if cost <= 0:
                    continue
                by_model[model] = by_model.get(model, 0.0) + cost
        # округление
        for k in list(by_model.keys()):
            by_model[k] = round(by_model[k], 6)
        return by_model
    except Exception:
        return {}


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
              value TEXT NOT NULL,
              updated_at TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
    )
    await session.execute(text("ALTER TABLE app_settings ALTER COLUMN value TYPE TEXT"))
    await session.commit()


async def _get_app_setting_json(db: AsyncSession, key: str) -> dict[str, Any]:
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    setting = result.scalar_one_or_none()
    if not setting or not setting.value:
        return {}
    try:
        payload = json.loads(str(setting.value))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


async def _set_app_setting_json(db: AsyncSession, key: str, value: dict[str, Any]) -> None:
    await _ensure_app_settings_table(db)
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    setting = result.scalar_one_or_none()
    encoded = json.dumps(value, ensure_ascii=False)
    if setting:
        setting.value = encoded
    else:
        db.add(AppSetting(key=key, value=encoded))
    await db.commit()


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

    return ModelSettingsResponse(default_model="openrouter/auto", source="default")


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


@router.get("/ai-core", response_model=AiCoreSettingsResponse)
async def get_ai_core_settings():
    """Returns the AI core used by BaseAgent conversations/generation."""

    try:
        from app.database.connection import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            await _ensure_app_settings_table(session)
            result = await session.execute(select(AppSetting).where(AppSetting.key == "ai_core_runtime"))
            setting = result.scalar_one_or_none()
            if setting and str(setting.value).strip().lower() in SUPPORTED_AI_CORE_RUNTIMES:
                return AiCoreSettingsResponse(
                    ai_core_runtime=str(setting.value).strip().lower(),
                    source="db",
                    options=sorted(SUPPORTED_AI_CORE_RUNTIMES),
                )
    except Exception:
        pass

    env_runtime = ai_core_runtime_from_env()
    source = "env" if os.getenv("GLAME_AI_CORE") or os.getenv("GLAME_AGENT_RUNTIME") else "default"
    return AiCoreSettingsResponse(
        ai_core_runtime=env_runtime.value,
        source=source,
        options=sorted(SUPPORTED_AI_CORE_RUNTIMES),
    )


@router.put("/ai-core", response_model=AiCoreSettingsResponse)
async def set_ai_core_settings(request: AiCoreSettingsUpdateRequest, db: AsyncSession = Depends(get_db)):
    """Persists the AI core switch: openrouter, hermes, or local."""

    runtime = str(request.ai_core_runtime or "").strip().lower()
    if runtime not in SUPPORTED_AI_CORE_RUNTIMES:
        raise HTTPException(
            status_code=400,
            detail=f"ai_core_runtime должен быть одним из: {', '.join(sorted(SUPPORTED_AI_CORE_RUNTIMES))}.",
        )

    await _ensure_app_settings_table(db)
    result = await db.execute(select(AppSetting).where(AppSetting.key == "ai_core_runtime"))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = runtime
    else:
        db.add(AppSetting(key="ai_core_runtime", value=runtime))
    await db.commit()
    return AiCoreSettingsResponse(
        ai_core_runtime=runtime,
        source="db",
        options=sorted(SUPPORTED_AI_CORE_RUNTIMES),
    )


def _parse_hermes_profile_model(output: str) -> str:
    for line in (output or "").splitlines():
        if line.strip().lower().startswith("model:"):
            return line.split(":", 1)[1].strip()
    return ""


@router.get("/ai-runtime/{agent_id}", response_model=AiRuntimeInfoResponse)
async def get_ai_runtime_info(agent_id: str):
    """Runtime label for chat headers: Hermes profile/model, OpenRouter model, or local model."""

    runtime, source = await get_ai_core_runtime()
    if runtime.value == "hermes":
        hermes = HermesAgentRuntime(hermes_runtime_config_from_env())
        profile = hermes.profile_for_agent(agent_id)
        model = "unknown"
        try:
            raw = await hermes.executor(
                [hermes.config.binary, "profile", "show", profile],
                min(hermes.config.timeout_seconds, 15),
            )
            if int(raw.get("exit_code", 1)) == 0:
                parsed = _parse_hermes_profile_model(str(raw.get("stdout", "")))
                if parsed:
                    model = parsed
        except Exception:
            pass
        return AiRuntimeInfoResponse(
            ai_core_runtime="hermes",
            source=source,
            agent_id=agent_id,
            profile=profile,
            model=model,
            label=f"Hermes: {model} · {profile}",
        )

    if runtime.value == "local":
        model = os.getenv("LOCAL_LLM_MODEL", "llama3.1")
        return AiRuntimeInfoResponse(
            ai_core_runtime="local",
            source=source,
            agent_id=agent_id,
            model=model,
            label=f"Local: {model}",
        )

    model = os.getenv("DEFAULT_MODEL") or "openrouter/auto"
    try:
        from app.database.connection import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            result = await session.execute(select(AppSetting).where(AppSetting.key == "default_model"))
            setting = result.scalar_one_or_none()
            if setting and setting.value:
                model = str(setting.value)
    except Exception:
        pass
    return AiRuntimeInfoResponse(
        ai_core_runtime="openrouter",
        source=source,
        agent_id=agent_id,
        model=model,
        label=f"OpenRouter: {model}",
    )


@router.get("/ai-stylist", response_model=AiStylistSettingsResponse)
async def get_ai_stylist_settings(db: AsyncSession = Depends(get_db)):
    """Флаг работы AI стилиста в чате покупателя."""
    await _ensure_app_settings_table(db)
    result = await db.execute(select(AppSetting).where(AppSetting.key == "ai_stylist_enabled"))
    setting = result.scalar_one_or_none()
    if not setting:
        return AiStylistSettingsResponse(enabled=True, source="default")
    enabled = str(setting.value).strip().lower() in {"1", "true", "yes", "on", "enabled"}
    return AiStylistSettingsResponse(enabled=enabled, source="db")


@router.put("/ai-stylist", response_model=AiStylistSettingsResponse)
async def set_ai_stylist_settings(
    request: AiStylistSettingsUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Включает/выключает автоответы AI стилиста."""
    await _ensure_app_settings_table(db)
    value = "true" if request.enabled else "false"
    result = await db.execute(select(AppSetting).where(AppSetting.key == "ai_stylist_enabled"))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = value
    else:
        db.add(AppSetting(key="ai_stylist_enabled", value=value))
    await db.commit()
    return AiStylistSettingsResponse(enabled=request.enabled, source="db")


@router.get("/email-server", response_model=EmailServerSettingsResponse)
async def get_email_server_settings(
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    settings, source = await load_smtp_settings(db)
    return EmailServerSettingsResponse(**public_smtp_settings(settings, source=source))


@router.put("/email-server", response_model=EmailServerSettingsResponse)
async def set_email_server_settings(
    request: EmailServerSettingsUpdateRequest,
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    existing = await _get_app_setting_json(db, EMAIL_SERVER_SETTING_KEY)
    password = (request.password or "").strip()
    if not password and isinstance(existing.get("password"), str):
        password = str(existing.get("password") or "")

    payload = {
        "host": request.host.strip(),
        "port": int(request.port),
        "username": (request.username or "").strip(),
        "password": password,
        "from_email": request.from_email.strip(),
        "from_name": (request.from_name or "GLAME Jewelry").strip(),
        "use_ssl": bool(request.use_ssl),
        "use_starttls": bool(request.use_starttls),
    }
    await _set_app_setting_json(db, EMAIL_SERVER_SETTING_KEY, payload)
    settings, source = await load_smtp_settings(db)
    return EmailServerSettingsResponse(**public_smtp_settings(settings, source=source))


@router.post("/email-server/test", response_model=EmailServerTestResponse)
async def test_email_server_settings(
    request: EmailServerTestRequest,
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    try:
        await GiftCertificateEmailService(db).send_test_email(request.to_email)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Не удалось отправить тестовое письмо: {exc}")
    return EmailServerTestResponse(ok=True, message="Тестовое письмо отправлено.")


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
    # logging imported at module level
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


@router.get("/openrouter/key", response_model=OpenRouterKeyInfo)
async def get_openrouter_key_info():
    """
    Возвращает информацию о текущем API ключе OpenRouter:
    лимиты, оставшиеся кредиты, агрегированное использование (день/неделя/месяц).
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    if not api_key:
        raise HTTPException(status_code=400, detail="OPENROUTER_API_KEY не установлен на backend.")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://glame.ai",
        "X-Title": "GLAME AI Platform",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{base_url}/key", headers=headers)
            resp.raise_for_status()
            data = resp.json()
            # Ответ спецификации уже содержит поле data
            return OpenRouterKeyInfo(data=data.get("data") or data)
    except httpx.HTTPStatusError as e:
        detail = (e.response.text or "")[:500]
        raise HTTPException(status_code=502, detail=f"OpenRouter /key error: HTTP {e.response.status_code}. {detail}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch OpenRouter key info: {str(e)}")


@router.get("/openrouter/credits", response_model=OpenRouterCreditsInfo)
async def get_openrouter_credits():
    management_key = os.getenv("OPENROUTER_MANAGEMENT_API_KEY")
    if not management_key:
        raise HTTPException(
            status_code=400,
            detail="OPENROUTER_MANAGEMENT_API_KEY не установлен на backend (management key обязателен для /credits).",
        )

    global _credits_cache, _credits_cache_ts
    now = time.time()
    if _credits_cache is not None and (now - _credits_cache_ts) < _CREDITS_CACHE_TTL_SEC:
        return OpenRouterCreditsInfo(
            total_credits=_credits_cache.total_credits,
            total_usage=_credits_cache.total_usage,
            remaining_credits=_credits_cache.remaining_credits,
            cached=True,
            fetched_at=_credits_cache.fetched_at,
        )

    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    headers = {
        "Authorization": f"Bearer {management_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{base_url}/credits", headers=headers)
            resp.raise_for_status()
            raw = resp.json()
    except httpx.HTTPStatusError as e:

        detail = (e.response.text or "")[:500]
        logging.getLogger(__name__).warning(
            f"OpenRouter /credits error: HTTP {e.response.status_code}. {detail}"
        )
        raise HTTPException(
            status_code=502,
            detail=f"OpenRouter /credits error: HTTP {e.response.status_code}. {detail}",
        )
    except Exception as e:

        logging.getLogger(__name__).warning(f"Failed to fetch OpenRouter credits: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to fetch OpenRouter credits: {str(e)}")

    payload = raw.get("data", raw)
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=502,
            detail="Некорректный ответ от OpenRouter /credits: поле data должно быть объектом.",
        )

    try:
        total_credits = float(payload.get("total_credits") or 0.0)
        total_usage = float(payload.get("total_usage") or 0.0)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=502,
            detail="Некорректные числовые значения total_credits/total_usage в ответе OpenRouter /credits.",
        )

    remaining = total_credits - total_usage
    info = OpenRouterCreditsInfo(
        total_credits=round(total_credits, 6),
        total_usage=round(total_usage, 6),
        remaining_credits=round(remaining, 6),
        cached=False,
        fetched_at=now,
    )
    _credits_cache = info
    _credits_cache_ts = now

    return info


@router.get("/openrouter/usage", response_model=OpenRouterUsageResponse)
async def get_openrouter_usage(days: int = 7):
    """
    Попытка получить детализацию расходов через OpenRouter /api/v1/activity (если доступно для ключа).
    Возвращает:
    - by_day: траты по дням
    - by_model: траты по моделям
    - by_purpose: пусто (может наполняться локальным логированием в будущем)
    """
    if days not in (7, 30):
        days = 7
    management_key = os.getenv("OPENROUTER_MANAGEMENT_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    if not management_key:
        raise HTTPException(
            status_code=400,
            detail="OPENROUTER_MANAGEMENT_API_KEY не установлен на backend (management key обязателен для /activity).",
        )
    headers = {
        "Authorization": f"Bearer {management_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://glame.ai",
        "X-Title": "GLAME AI Platform",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # /activity возвращает 30 последних дней; фильтруем по days на backend
            resp = await client.get(f"{base_url}/activity", headers=headers)
            resp.raise_for_status()
            data = resp.json() or {}
            rows = list(data.get("data") or [])
    except httpx.HTTPStatusError as e:
        # Если endpoint недоступен для ключа — возвращаем пустую детализацию
        if e.response.status_code in (401, 403, 404):
            return OpenRouterUsageResponse(days=days, by_day=[], by_model=[], by_purpose=[])
        detail = (e.response.text or "")[:500]
        raise HTTPException(status_code=502, detail=f"OpenRouter /activity error: HTTP {e.response.status_code}. {detail}")
    except Exception as e:
        return OpenRouterUsageResponse(days=days, by_day=[], by_model=[], by_purpose=[])

    # Агрегация
    from collections import defaultdict
    by_day_map: Dict[str, Dict[str, Any]] = {}
    by_model_map: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"model": "", "total_cost": 0.0, "requests": 0})

    # Берём только последние 'days' по дате
    # /activity дата в формате YYYY-MM-DD
    rows_sorted = sorted(rows, key=lambda r: r.get("date") or "")
    if days == 7:
        rows_sorted = rows_sorted[-7:]
    elif days == 30:
        rows_sorted = rows_sorted[-30:]

    for r in rows_sorted:
        date_str = str(r.get("date"))
        model = str(r.get("model") or r.get("model_permaslug") or "unknown")
        cost = float(r.get("usage") or 0.0)
        reqs = int(r.get("requests") or 0)
        # По дням
        if date_str not in by_day_map:
            by_day_map[date_str] = {"date": date_str, "total_cost": 0.0, "requests": 0}
        by_day_map[date_str]["total_cost"] += cost
        by_day_map[date_str]["requests"] += reqs
        # По моделям
        bm = by_model_map[model]
        bm["model"] = model
        bm["total_cost"] += cost
        bm["requests"] += reqs

    by_day = [
        OpenRouterUsagePoint(date=k, total_cost=round(v["total_cost"], 6), requests=v["requests"])
        for k, v in sorted(by_day_map.items())
    ]
    by_model = sorted(by_model_map.values(), key=lambda x: x["total_cost"], reverse=True)

    return OpenRouterUsageResponse(days=days, by_day=by_day, by_model=by_model, by_purpose=[])

def _is_openrouter_image_generation_model(model: Dict[str, Any]) -> bool:
    """Строго определяет модели, пригодные для генерации изображений.

    OpenRouter не всегда отдаёт отдельный тип/modality. Поэтому dropdown должен
    быть консервативным: лучше не показать спорную модель, чем дать администратору
    выбрать обычную текстовую Gemini/Gemma/Nemotron модель для image generation.
    """
    model_id = str(model.get("id", "")).lower()
    model_name = str(model.get("name", "")).lower()
    model_type = str(model.get("type", "")).lower()
    joined = f"{model_id} {model_name}"

    if model_type in {"image", "image-generation", "image_generation", "image_generation_model"}:
        return True

    explicit_image_patterns = [
        "image",
        "images",
        "imagen",
        "dall-e",
        "dalle",
        "flux",
        "stable-diffusion",
        "sdxl",
        "midjourney",
        "kandinsky",
        "leonardo",
        "playground",
    ]
    if any(pattern in joined for pattern in explicit_image_patterns):
        return True

    known_prefixes = (
        "black-forest-labs/flux",
        "openai/gpt-5-image",
        "openai/dall-e",
        "google/gemini-2.5-flash-image",
        "google/gemini-3.1-flash-image",
        "google/gemini-3-pro-image",
        "google/imagen",
        "stability-ai/stable-diffusion",
    )
    return any(model_id.startswith(prefix) for prefix in known_prefixes)


def _filter_image_generation_models_raw(raw_models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Фильтрует модели для генерации изображений из сырого списка OpenRouter.
    """
    logger = logging.getLogger(__name__)
    filtered = [model for model in raw_models if _is_openrouter_image_generation_model(model)]
    logger.info(f"Filtered {len(filtered)} image generation models from {len(raw_models)} total models")
    if not filtered:
        sample_models = [
            f"{str(model.get('id', '')).lower()} (type: {str(model.get('type', '')).lower()})"
            for model in raw_models[:10]
        ]
        logger.warning(f"No image models found! Sample models from API: {sample_models}")
    return filtered


def _filter_image_generation_models(normalized_models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Фильтрует нормализованные модели для генерации изображений"""
    logger = logging.getLogger(__name__)
    filtered = [model for model in normalized_models if _is_openrouter_image_generation_model(model)]
    logger.info(f"Filtered {len(filtered)} image models from {len(normalized_models)} normalized models")

    def sort_key(model: Dict[str, Any]) -> tuple:
        id_str = str(model.get("id", "")).lower()
        name_str = str(model.get("name", "")).lower()
        if "black-forest" in id_str or "flux" in id_str:
            priority = 0
        elif "google" in id_str or "nano" in id_str or "imagen" in id_str:
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


@router.get("/image-optimization/status", response_model=ImageOptimizationStatusResponse)
async def get_image_optimization_status(current_user: User = Depends(require_admin())):
    async with _image_optimization_lock:
        return ImageOptimizationStatusResponse(**_image_optimization_state)


@router.post("/image-optimization/run", response_model=ImageOptimizationStatusResponse)
async def start_image_optimization(current_user: User = Depends(require_admin())):
    global _image_optimization_task, _image_optimization_state

    async with _image_optimization_lock:
        if _image_optimization_task is not None and not _image_optimization_task.done():
            return ImageOptimizationStatusResponse(**_image_optimization_state)

        started_at = datetime.now(timezone.utc).isoformat()
        _image_optimization_state = {
            **_default_image_optimization_state(),
            "status": "running",
            "started_at": started_at,
            "message": "Оптимизация изображений запущена. Обновляйте статус, чтобы увидеть результат.",
        }
        _image_optimization_task = asyncio.create_task(_run_image_optimization_job(started_at))
        return ImageOptimizationStatusResponse(**_image_optimization_state)


class OpenRouterModelStat(BaseModel):
    model: str
    total_cost: float
    requests: int


class OpenRouterDayStat(BaseModel):
    date: str
    total_cost: float
    by_model: Dict[str, float]  # модель -> стоимость за день


class OpenRouterStatsResponse(BaseModel):
    avg_daily: float  # средние дневные траты ($/день)
    remaining_credits: float  # текущий остаток аккаунта ($)
    days_left: float  # примерное число дней (остаток делить на средний расход)
    by_model: List[OpenRouterModelStat]  # разбивка по моделям
    by_day: List[OpenRouterDayStat]  # данные по дням для гистограммы


def _period_dates(period: str) -> tuple[str, str]:
    now = datetime.now(timezone.utc).date()
    if period == "today":
        start = now
        end = now
    elif period == "yesterday":
        d = now - timedelta(days=1)
        start = d
        end = d
    elif period == "week":
        start = now - timedelta(days=now.weekday())
        end = now
    else:
        start = now.replace(day=1)
        end = now
    return (start.isoformat(), end.isoformat())


@router.get("/openrouter/stats", response_model=OpenRouterStatsResponse)
async def get_openrouter_stats(period: str = Query("month", pattern="^(today|yesterday|week|month)$")):
    """
    Возвращает статистику использования OpenRouter:
    - avg_daily: средние дневные траты ($/день) — из /auth/key
    - remaining_credits: текущий остаток ($) — из /credits (Management API) или limit_remaining из /auth/key
    - days_left: примерное число дней хватит средств
    - by_model: разбивка расходов по моделям
    - by_day: данные по дням для гистограммы
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    management_key = os.getenv("OPENROUTER_MANAGEMENT_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    
    if not api_key:
        raise HTTPException(status_code=400, detail="OPENROUTER_API_KEY не установлен на backend.")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://glame.ai",
        "X-Title": "GLAME AI Platform",
    }
    
    avg_daily = 0.0
    remaining_credits = 0.0
    limit_remaining = None  # может быть null для безлимитных ключей
    by_model: List[OpenRouterModelStat] = []
    by_day_map: Dict[str, Dict[str, Any]] = {}
    p_start, p_end = _period_dates(period)
    logging.getLogger(__name__).info(f"[openrouter.stats] period={period} start={p_start} end={p_end}")
    cache_key = f"stats:{p_start}:{p_end}"
    now_ts = time.time()
    ttl = _STATS_CACHE_TTL_SEC_TODAY if period == "today" else _STATS_CACHE_TTL_SEC
    if cache_key in _stats_cache and (now_ts - _stats_cache_ts.get(cache_key, 0.0)) < ttl:
        cached = _stats_cache[cache_key]
        return OpenRouterStatsResponse(
            avg_daily=cached["avg_daily"],
            remaining_credits=cached["remaining_credits"],
            days_left=cached["days_left"],
            by_model=[OpenRouterModelStat(**m) for m in cached["by_model"]],
            by_day=[OpenRouterDayStat(**d) for d in cached["by_day"]],
        )
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Получаем данные из /auth/key (информация о ключе)
            try:
                key_resp = await client.get(f"{base_url}/auth/key", headers=headers)
                key_resp.raise_for_status()
                key_data = key_resp.json()
                
                key_info = key_data.get("data", key_data)
                if key_info and isinstance(key_info, dict):
                    # Извлекаем limit_remaining (баланс ключа)
                    limit_remaining = key_info.get("limit_remaining")
                    if limit_remaining is not None:
                        remaining_credits = float(limit_remaining)
                    
                    # Извлекаем usage для расчета средних трат
                    usage_daily = key_info.get("usage_daily")
                    usage_weekly = key_info.get("usage_weekly")
                    usage_monthly = key_info.get("usage_monthly")
                    
                    # Вычисляем средние дневные траты
                    if isinstance(usage_daily, (int, float)) and usage_daily > 0:
                        avg_daily = float(usage_daily)
                    elif isinstance(usage_weekly, (int, float)) and usage_weekly > 0:
                        avg_daily = float(usage_weekly) / 7.0
                    elif isinstance(usage_monthly, (int, float)) and usage_monthly > 0:
                        avg_daily = float(usage_monthly) / 30.0
            except Exception as e:
                logging.getLogger(__name__).warning(f"Failed to fetch /auth/key: {e}")
            
            # Получаем разбивку по моделям из /activity (предпочитаем Management key, если он есть)
            try:
                activity_headers = headers
                if management_key:
                    activity_headers = {
                        "Authorization": f"Bearer {management_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://glame.ai",
                        "X-Title": "GLAME AI Platform",
                    }
                activity_resp = await client.get(f"{base_url}/activity", headers=activity_headers)
                activity_resp.raise_for_status()
                activity_data = activity_resp.json()
                rows = list(activity_data.get("data") or [])
                logging.getLogger(__name__).info(f"[openrouter.stats] fetched rows={len(rows)}")
                
                from collections import defaultdict
                by_model_map: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"model": "", "total_cost": 0.0, "requests": 0})
                
                kept = 0
                for r in rows:
                    model = str(r.get("model") or r.get("model_permaslug") or "unknown")
                    cost = float(r.get("usage") or 0.0)
                    reqs = int(r.get("requests") or 0)
                    date_str = str(r.get("date") or "")
                    if p_start and date_str and date_str < p_start:
                        continue
                    if p_end and date_str and date_str > p_end:
                        continue
                    kept += 1
                    
                    # Агрегируем по моделям
                    bm = by_model_map[model]
                    bm["model"] = model
                    bm["total_cost"] += cost
                    bm["requests"] += reqs
                    
                    # Агрегируем по дням для гистограммы
                    if date_str:
                        if date_str not in by_day_map:
                            by_day_map[date_str] = {"date": date_str, "total_cost": 0.0, "by_model": {}}
                        by_day_map[date_str]["total_cost"] += cost
                        if model not in by_day_map[date_str]["by_model"]:
                            by_day_map[date_str]["by_model"][model] = 0.0
                        by_day_map[date_str]["by_model"][model] += cost
                logging.getLogger(__name__).info(f"[openrouter.stats] kept rows after filter={kept}")
                
                by_model = [
                    OpenRouterModelStat(
                        model=v["model"],
                        total_cost=round(v["total_cost"], 6),
                        requests=v["requests"]
                    )
                    for v in sorted(by_model_map.values(), key=lambda x: x["total_cost"], reverse=True)
                ]
            except Exception as e:
                logging.getLogger(__name__).warning(f"Failed to fetch /activity: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch OpenRouter stats: {str(e)}")
    
    # Получаем остаток через Management API (если ключ установлен)
    # Остаток = total_credits - total_usage
    if management_key:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                mgmt_headers = {
                    "Authorization": f"Bearer {management_key}",
                    "Content-Type": "application/json",
                }
                credits_resp = await client.get("https://openrouter.ai/api/v1/credits", headers=mgmt_headers)
                credits_resp.raise_for_status()
                credits_data = credits_resp.json()
                
                credits_info = credits_data.get("data", credits_data)
                if isinstance(credits_info, dict):
                    total_credits = float(credits_info.get("total_credits") or 0.0)
                    total_usage = float(credits_info.get("total_usage") or 0.0)
                    remaining_credits = total_credits - total_usage
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to fetch /credits: {e}")
    
    # Считаем сколько дней хватит
    days_left = 0.0
    if avg_daily > 0 and remaining_credits > 0:
        days_left = round(remaining_credits / avg_daily, 1)
    
    # Если сегодня пусто (частый случай из‑за UTC агрегатов), заполним из локального лога; если лога нет — fallback /auth/key
    if period == "today":
        day_key = p_end  # YYYY-MM-DD (UTC); для лога используем МСК, ниже пересчитаем
        # Пробуем собрать по моделям из локального лога (МСК)
        try:
            from zoneinfo import ZoneInfo
            msk_today = datetime.now(ZoneInfo("Europe/Moscow")).date().isoformat()
            local_by_model = _aggregate_by_model_from_local_log(msk_today)
        except Exception:
            local_by_model = {}
        if local_by_model:
            total_local = round(sum(local_by_model.values()), 6)
            by_day_map[day_key] = {"date": day_key, "total_cost": total_local, "by_model": local_by_model}
            # И заполняем общий by_model для периода today
            by_model = [
                OpenRouterModelStat(model=m, total_cost=round(c, 6), requests=0)
                for m, c in sorted(local_by_model.items(), key=lambda x: x[1], reverse=True)
            ]
        elif not by_day_map:
            # Локальный лог пуст — используем usage_daily без разбивки
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    key_resp = await client.get(f"{base_url}/auth/key", headers=headers)
                    key_resp.raise_for_status()
                    key_data = key_resp.json()
                    key_info = key_data.get("data", key_data) or {}
                    usage_daily = float(key_info.get("usage_daily") or 0.0)
                    if usage_daily > 0:
                        by_day_map[day_key] = {"date": day_key, "total_cost": usage_daily, "by_model": {}}
            except Exception as e:
                logging.getLogger(__name__).warning(f"Fallback usage_daily failed: {e}")

    # Формируем данные по дням для гистограммы
    by_day = [
        OpenRouterDayStat(
            date=k,
            total_cost=round(v["total_cost"], 6),
            by_model={model: round(cost, 6) for model, cost in v["by_model"].items()}
        )
        for k, v in sorted(by_day_map.items())
    ]
    
    response = OpenRouterStatsResponse(
        avg_daily=round(avg_daily, 4),
        remaining_credits=round(remaining_credits, 4),
        days_left=days_left,
        by_model=by_model,
        by_day=by_day
    )
    _stats_cache[cache_key] = {
        "avg_daily": response.avg_daily,
        "remaining_credits": response.remaining_credits,
        "days_left": response.days_left,
        "by_model": [m.dict() for m in response.by_model],
        "by_day": [d.dict() for d in response.by_day],
    }
    _stats_cache_ts[cache_key] = now_ts
    return response


class OpenRouterActivityItem(BaseModel):
    id: Optional[str] = None
    created_at: Optional[str] = None
    model: Optional[str] = None
    cost: float = 0.0
    tokens_prompt: Optional[int] = None
    tokens_completion: Optional[int] = None
    provider_name: Optional[str] = None
    external_user: Optional[str] = None
    upstream_id: Optional[str] = None
    api_type: Optional[str] = None


class OpenRouterActivityResponse(BaseModel):
    items: List[OpenRouterActivityItem]
    total_cost: float
    total_requests: int


@router.get("/openrouter/activity", response_model=OpenRouterActivityResponse)
async def get_openrouter_activity(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    date: Optional[str] = None,
    save: bool = False,
):
    management_key = os.getenv("OPENROUTER_MANAGEMENT_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    if not management_key:
        raise HTTPException(
            status_code=400,
            detail="OPENROUTER_MANAGEMENT_API_KEY не установлен на backend (management key обязателен для /activity).",
        )

    params: Optional[Dict[str, Any]] = None
    if date:
        d = date.strip()
        if len(d) != 10:
            raise HTTPException(status_code=400, detail="Параметр date должен быть в формате YYYY-MM-DD.")
        params = {"date": d}

    headers = {
        "Authorization": f"Bearer {management_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://glame.ai",
        "X-Title": "GLAME AI Platform",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{base_url}/activity", headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json() or {}
            rows = list(data.get("data") or [])
    except httpx.HTTPStatusError as e:
        detail = (e.response.text or "")[:500]
        raise HTTPException(status_code=502, detail=f"OpenRouter /activity error: HTTP {e.response.status_code}. {detail}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch OpenRouter activity: {str(e)}")

    def _date_key(s: Any) -> str:
        if not s:
            return ""
        try:
            return str(s)[:10]
        except Exception:
            return ""

    s_key = (start_date or "").strip()
    e_key = (end_date or "").strip()

    items: List[OpenRouterActivityItem] = []
    total_cost = 0.0
    total_requests = 0

    punt = []
    for r in rows:
        created_at = str(r.get("created_at") or r.get("date") or "")
        dkey = _date_key(created_at)
        if s_key and dkey and dkey < s_key:
            continue
        if e_key and dkey and dkey > e_key:
            continue
        cost = float(r.get("usage") or r.get("total_cost") or 0.0)
        total_cost += cost
        total_requests += 1
        items.append(
            OpenRouterActivityItem(
                id=str(r.get("id") or r.get("generation_id") or ""),
                created_at=created_at,
                model=str(r.get("model") or r.get("model_permaslug") or "unknown"),
                cost=round(cost, 6),
                tokens_prompt=int(r.get("tokens_prompt") or r.get("native_tokens_prompt") or 0) if r.get("tokens_prompt") is not None or r.get("native_tokens_prompt") is not None else None,
                tokens_completion=int(r.get("tokens_completion") or r.get("native_tokens_completion") or 0) if r.get("tokens_completion") is not None or r.get("native_tokens_completion") is not None else None,
                provider_name=str(r.get("provider_name") or "") or None,
                external_user=str(r.get("external_user") or "") or None,
                upstream_id=str(r.get("upstream_id") or "") or None,
                api_type=str(r.get("api_type") or "") or None,
            )
        )
    if save and items:
        try:
            log_path = os.getenv("OPENROUTER_COST_LOG_PATH", "/tmp/openrouter_costs.jsonl")
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            import json, time as _t
            with open(log_path, "a", encoding="utf-8") as f:
                for it in items:
                    rec = it.dict()
                    rec["_saved_at"] = _t.time()
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass
    return OpenRouterActivityResponse(items=items, total_cost=round(total_cost, 6), total_requests=total_requests)


class OpenRouterGenerationResponse(BaseModel):
    data: Dict[str, Any]


@router.get("/openrouter/generation", response_model=OpenRouterGenerationResponse)
async def get_openrouter_generation(id: str = Query(..., min_length=3)):
    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    if not api_key:
        raise HTTPException(status_code=400, detail="OPENROUTER_API_KEY не установлен на backend.")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://glame.ai",
        "X-Title": "GLAME AI Platform",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{base_url}/generation", params={"id": id}, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            payload = data.get("data", data)
            if not isinstance(payload, dict):
                payload = {"data": payload}
            return OpenRouterGenerationResponse(data=payload)
    except httpx.HTTPStatusError as e:
        detail = (e.response.text or "")[:500]
        raise HTTPException(status_code=502, detail=f"OpenRouter /generation error: HTTP {e.response.status_code}. {detail}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch OpenRouter generation: {str(e)}")


class OpenRouterTodaySummary(BaseModel):
    date: str
    total_cost: float
    by_model: Dict[str, float]


@router.get("/openrouter/today", response_model=OpenRouterTodaySummary)
async def get_openrouter_today():
    today = datetime.utcnow().date().isoformat()
    try:
        act = await get_openrouter_activity(start_date=today, end_date=today, save=False)
        by_model: Dict[str, float] = {}
        for it in act.items:
            key = it.model or "unknown"
            by_model[key] = round(by_model.get(key, 0.0) + (it.cost or 0.0), 6)
        total = round(sum(by_model.values()), 6)
        if total > 0:
            return OpenRouterTodaySummary(date=today, total_cost=total, by_model=by_model)
    except Exception as e:
        logging.getLogger(__name__).warning(f"today activity failed: {e}")
    # Попытка собрать по моделям из локального лога (МСК)
    try:
        from zoneinfo import ZoneInfo
        msk_today = datetime.now(ZoneInfo("Europe/Moscow")).date().isoformat()
        local_by_model = _aggregate_by_model_from_local_log(msk_today)
        if local_by_model:
            total_local = round(sum(local_by_model.values()), 6)
            return OpenRouterTodaySummary(date=today, total_cost=total_local, by_model=local_by_model)
    except Exception:
        pass
    # Fallback на /auth/key usage_daily
    api_key = os.getenv("OPENROUTER_API_KEY")
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    if not api_key:
        return OpenRouterTodaySummary(date=today, total_cost=0.0, by_model={})
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://glame.ai",
        "X-Title": "GLAME AI Platform",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            key_resp = await client.get(f"{base_url}/auth/key", headers=headers)
            key_resp.raise_for_status()
            key_data = key_resp.json()
            key_info = key_data.get("data", key_data) or {}
            usage_daily = float(key_info.get("usage_daily") or 0.0)
            return OpenRouterTodaySummary(date=today, total_cost=round(usage_daily, 6), by_model={})
    except Exception as e:
        logging.getLogger(__name__).warning(f"today usage_daily fallback failed: {e}")
        return OpenRouterTodaySummary(date=today, total_cost=0.0, by_model={})
