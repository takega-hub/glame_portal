from fastapi import APIRouter, Depends, HTTPException, Query, Body, UploadFile, File, Form
from fastapi.responses import PlainTextResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional, List, Any, Dict
from datetime import datetime, timezone as dt_timezone, timedelta
from app.database.connection import get_db
from app.agents.content_agent import ContentAgent
from app.models.content_plan import ContentPlan
from app.models.content_item import ContentItem
from app.models.content_publication import ContentPublication
from app.models.product import Product
from app.models.user import User
from app.api.auth import get_current_user, get_current_user_optional
from uuid import UUID
import logging
import anyio

logger = logging.getLogger(__name__)
from app.services.yandex_calendar_service import list_calendars as yandex_list_calendars
from app.services.yandex_calendar_service import upsert_event_by_uid as yandex_upsert_event_by_uid
from app.services.yandex_calendar_service import get_config_from_env as yandex_get_config_from_env
from app.services.jewelry_photo_service import (
    JewelryPhotoService,
    JewelryPhotoServiceError,
    ModelDoesNotSupportImageError,
)

router = APIRouter()


class ContentGenerateRequest(BaseModel):
    persona: Optional[str] = None
    cjm_stage: Optional[str] = None
    channel: str = "website_main"
    goal: Optional[str] = None


class ContentResponse(BaseModel):
    content: str
    persona: Optional[str] = None
    cjm_stage: Optional[str] = None


@router.post("/generate", response_model=ContentResponse)
async def generate_content(request: ContentGenerateRequest, db: AsyncSession = Depends(get_db)):
    """Генерация контента через AI Content Agent"""
    try:
        agent = ContentAgent(db)
        result = await agent.process(
            persona=request.persona,
            cjm_stage=request.cjm_stage,
            channel=request.channel,
            goal=request.goal
        )
        return ContentResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating content: {str(e)}")


def _parse_iso_datetime(value: str) -> datetime:
    """
    Парсинг ISO даты/времени.
    - Если пришла только дата (YYYY-MM-DD) → считаем 00:00:00Z.
    - Если пришло без tzinfo → считаем UTC.
    """
    try:
        value = value.strip()
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        if len(value) == 10 and value[4] == "-" and value[7] == "-":
            dt = datetime.fromisoformat(value + "T00:00:00")
        else:
            dt = datetime.fromisoformat(value)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid datetime format: {value}. {e}")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt_timezone.utc)
    return dt


class ContentPlanGenerateRequest(BaseModel):
    campaign_id: Optional[str] = None  # ID маркетинговой кампании для привязки
    name: Optional[str] = None
    start_date: str
    end_date: str
    timezone: str = "Europe/Moscow"
    channels: List[str]
    frequency_rules: Optional[Dict[str, Any]] = None
    persona: Optional[str] = None
    goal: Optional[str] = None
    campaign_context: Optional[str] = None
    save: bool = True


class ContentPlanItemDTO(BaseModel):
    id: str
    plan_id: str
    scheduled_at: datetime
    timezone: str
    channel: str
    content_type: str
    topic: Optional[str] = None
    hook: Optional[str] = None
    cta: Optional[str] = None
    persona: Optional[str] = None
    cjm_stage: Optional[str] = None
    goal: Optional[str] = None
    spec: dict | None = None
    generated: dict | None = None
    generated_text: Optional[str] = None
    status: str
    published_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ContentItemCreateRequest(BaseModel):
    """Модель для создания нового слота."""
    scheduled_at: str  # ISO datetime string
    timezone: str = "Europe/Moscow"
    channel: str
    content_type: str = "post"
    topic: Optional[str] = None
    hook: Optional[str] = None
    cta: Optional[str] = None
    persona: Optional[str] = None
    cjm_stage: Optional[str] = None
    goal: Optional[str] = None
    spec: Optional[Dict[str, Any]] = None
    status: str = "planned"


class ContentItemUpdateRequest(BaseModel):
    """Модель для обновления слота. Все поля опциональны."""
    scheduled_at: Optional[str] = None
    timezone: Optional[str] = None
    channel: Optional[str] = None
    content_type: Optional[str] = None
    topic: Optional[str] = None
    hook: Optional[str] = None
    cta: Optional[str] = None
    persona: Optional[str] = None
    cjm_stage: Optional[str] = None
    goal: Optional[str] = None
    spec: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


class BulkUpdateStatusRequest(BaseModel):
    """Модель для массового изменения статуса слотов."""
    item_ids: List[str]  # Список UUID слотов
    status: str  # Новый статус


class BulkDeleteRequest(BaseModel):
    """Модель для массового удаления слотов."""
    item_ids: List[str]  # Список UUID слотов


class BulkGenerateRequest(BaseModel):
    """Модель для массовой генерации контента."""
    item_ids: List[str]  # Список UUID слотов
    feedback: Optional[str] = None  # Опциональная обратная связь для всех слотов


class ContentPlanDTO(BaseModel):
    id: str
    name: Optional[str] = None
    status: str
    start_date: datetime
    end_date: datetime
    timezone: str
    inputs: dict | None = None

    class Config:
        from_attributes = True


class ContentPlanUpdateRequest(BaseModel):
    """Модель для обновления контент-плана. Все поля опциональны."""
    name: Optional[str] = None
    status: Optional[str] = None  # draft, active, completed, archived
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    timezone: Optional[str] = None


class ContentPlanGenerateResponse(BaseModel):
    plan: dict
    items: list
    plan_id: Optional[str] = None


# ВАЖНО: Специфичные роуты должны быть определены ПЕРЕД параметризованными
# Порядок имеет значение для FastAPI маршрутизации

@router.post("/plans/generate", response_model=ContentPlanGenerateResponse)
async def generate_content_plan(
    request: ContentPlanGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Генерирует календарный контент-план (месяц/полгода/год — зависит от дат) и сохраняет в БД.
    ВАЖНО: Этот роут должен быть определен ПЕРЕД /plans/{plan_id}, чтобы FastAPI правильно обрабатывал путь.
    """
    import logging
    import traceback
    logger = logging.getLogger(__name__)
    logger.info("POST /plans/generate endpoint called")
    
    try:
        logger.info(f"Generating content plan: start={request.start_date}, end={request.end_date}, channels={request.channels}")
    except Exception:
        pass
    
    try:
        agent = ContentAgent(db)
        logger.info("ContentAgent created, calling generate_calendar_plan...")
        
        structured = await agent.generate_calendar_plan(
            start_date=request.start_date,
            end_date=request.end_date,
            timezone=request.timezone,
            channels=request.channels,
            frequency_rules=request.frequency_rules,
            persona=request.persona,
            goal=request.goal,
            campaign_context=request.campaign_context,
        )
        logger.info(f"Plan generated successfully, items count: {len(structured.get('items', []))}")
    except ValueError as e:
        # Специальная обработка для ошибок конфигурации (например, отсутствие API ключа)
        error_msg = str(e)
        logger.error(f"Configuration error generating calendar plan: {error_msg}")
        raise HTTPException(
            status_code=400,
            detail=f"Ошибка конфигурации: {error_msg}. Проверьте, что OPENROUTER_API_KEY установлен в переменных окружения."
        )
    except Exception as e:
        error_msg = str(e)
        error_type = type(e).__name__
        logger.error(f"Error generating calendar plan ({error_type}): {error_msg}")
        logger.error(traceback.format_exc())
        
        # Более понятные сообщения для пользователя
        if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
            user_msg = "Таймаут при генерации плана. Попробуйте уменьшить период или количество каналов."
        elif "api" in error_msg.lower() or "key" in error_msg.lower():
            user_msg = f"Ошибка API: {error_msg}. Проверьте, что OPENROUTER_API_KEY установлен и валиден."
        elif "json" in error_msg.lower() or "parse" in error_msg.lower():
            user_msg = f"Ошибка парсинга ответа от AI: {error_msg}. Попробуйте снова."
        else:
            user_msg = f"Ошибка генерации контент-плана: {error_msg}"
        
        raise HTTPException(
            status_code=500,
            detail=user_msg
        )

    if not request.save:
        return ContentPlanGenerateResponse(plan=structured.get("plan", {}), items=structured.get("items", []), plan_id=None)

    try:
        logger.info("Saving plan to database...")
        start_dt = _parse_iso_datetime(request.start_date)
        end_dt = _parse_iso_datetime(request.end_date)

        plan = ContentPlan(
            name=request.name or structured.get("plan", {}).get("title"),
            status="draft",
            start_date=start_dt,
            end_date=end_dt,
            timezone=request.timezone,
            inputs={
                "channels": request.channels,
                "frequency_rules": request.frequency_rules,
                "persona": request.persona,
                "goal": request.goal,
                "campaign_context": request.campaign_context,
                "llm_plan": structured.get("plan", {}),
            },
        )
        db.add(plan)
        await db.flush()  # получить plan.id до commit
        logger.info(f"Plan saved with ID: {plan.id}")

        items = []
        for raw in structured.get("items", []) or []:
            try:
                scheduled_at = _parse_iso_datetime(str(raw.get("scheduled_at")))
            except Exception as e:
                # если LLM вернул мусор — пропускаем слот, но не валим весь план
                logger.warning(f"Skipping invalid item: {raw.get('scheduled_at')}, error: {e}")
                continue

            item = ContentItem(
                plan_id=plan.id,
                scheduled_at=scheduled_at,
                timezone=request.timezone,
                channel=str(raw.get("channel") or request.channels[0]),
                content_type=str(raw.get("content_type") or "post"),
                topic=raw.get("topic"),
                hook=raw.get("hook"),
                cta=raw.get("cta"),
                persona=raw.get("persona") or request.persona,
                cjm_stage=raw.get("cjm_stage"),
                goal=raw.get("goal") or request.goal,
                spec=raw.get("spec") or {},
                status="planned",
            )
            db.add(item)
            items.append(item)

        await db.commit()
        logger.info(f"Plan saved successfully with {len(items)} items")

        return ContentPlanGenerateResponse(
            plan=structured.get("plan", {}),
            items=structured.get("items", []),
            plan_id=str(plan.id),
        )
    except Exception as e:
        await db.rollback()
        error_msg = str(e)
        logger.error(f"Error saving plan to database: {error_msg}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка сохранения плана в БД: {error_msg}. Проверьте логи backend."
        )


@router.get("/plans", response_model=List[ContentPlanDTO])
async def list_content_plans(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = None,
    search: Optional[str] = None,  # Поиск по названию
    start_date_from: Optional[str] = None,  # Фильтр: планы с start_date >= этой даты
    start_date_to: Optional[str] = None,  # Фильтр: планы с start_date <= этой даты
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Список сохранённых контент‑планов (для UI) с фильтрами."""
    from sqlalchemy import or_, func
    
    q = select(ContentPlan)
    
    # Фильтр по статусу
    if status:
        q = q.where(ContentPlan.status == status)
    
    # Поиск по названию (case-insensitive, частичное совпадение)
    if search:
        search_pattern = f"%{search}%"
        q = q.where(ContentPlan.name.ilike(search_pattern))
    
    # Фильтр по дате начала (от)
    if start_date_from:
        try:
            date_from = _parse_iso_datetime(start_date_from)
            q = q.where(ContentPlan.start_date >= date_from)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid start_date_from format: {e}")
    
    # Фильтр по дате начала (до)
    if start_date_to:
        try:
            date_to = _parse_iso_datetime(start_date_to)
            q = q.where(ContentPlan.start_date <= date_to)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid start_date_to format: {e}")
    
    # Фильтр по пользователю (если авторизован)
    if current_user:
        q = q.where(ContentPlan.user_id == current_user.id)
    else:
        # Если не авторизован, показываем только планы без user_id (общие планы)
        q = q.where(ContentPlan.user_id.is_(None))
    
    q = q.order_by(ContentPlan.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(q)
    plans = result.scalars().all()
    # Конвертируем UUID в строку для каждого плана
    return [
        ContentPlanDTO(
            id=str(plan.id),
            name=plan.name,
            status=plan.status,
            start_date=plan.start_date,
            end_date=plan.end_date,
            timezone=plan.timezone,
            inputs=plan.inputs,
        )
        for plan in plans
    ]


@router.get("/plans/{plan_id}", response_model=ContentPlanDTO)
async def get_content_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Получение конкретного контент-плана по ID."""
    result = await db.execute(select(ContentPlan).where(ContentPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Content plan not found")
    # Конвертируем UUID в строку для Pydantic
    return ContentPlanDTO(
        id=str(plan.id),
        name=plan.name,
        status=plan.status,
        start_date=plan.start_date,
        end_date=plan.end_date,
        timezone=plan.timezone,
        inputs=plan.inputs,
    )


@router.put("/plans/{plan_id}", response_model=ContentPlanDTO)
async def update_content_plan(
    plan_id: UUID,
    request: ContentPlanUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Обновление контент-плана (название, даты, статус, timezone)."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Проверяем существование плана
        result = await db.execute(select(ContentPlan).where(ContentPlan.id == plan_id))
        plan = result.scalar_one_or_none()
        if not plan:
            raise HTTPException(status_code=404, detail="Content plan not found")
        
        # Проверка прав доступа (мультитенантность)
        if current_user and plan.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        if not current_user and plan.user_id is not None:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Обновляем поля, если они переданы
        if request.name is not None:
            plan.name = request.name
        if request.status is not None:
            # Валидация статуса
            valid_statuses = ["draft", "active", "completed", "archived"]
            if request.status not in valid_statuses:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
                )
            plan.status = request.status
        if request.timezone is not None:
            plan.timezone = request.timezone
        if request.start_date is not None:
            plan.start_date = _parse_iso_datetime(request.start_date)
        if request.end_date is not None:
            plan.end_date = _parse_iso_datetime(request.end_date)
            # Проверяем, что end_date >= start_date
            if plan.start_date and plan.end_date < plan.start_date:
                raise HTTPException(
                    status_code=400,
                    detail="end_date must be greater than or equal to start_date"
                )
        
        # Обновляем updated_at вручную
        plan.updated_at = datetime.now(dt_timezone.utc)
        
        await db.commit()
        await db.refresh(plan)
        
        logger.info(f"Content plan {plan_id} updated successfully")
        
        return ContentPlanDTO(
            id=str(plan.id),
            name=plan.name,
            status=plan.status,
            start_date=plan.start_date,
            end_date=plan.end_date,
            timezone=plan.timezone,
            inputs=plan.inputs,
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Ошибка при обновлении плана: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при обновлении плана: {str(e)}")


@router.delete("/plans/{plan_id}")
async def delete_content_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Удаление контент-плана и всех связанных элементов."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Проверяем существование плана
        result = await db.execute(select(ContentPlan).where(ContentPlan.id == plan_id))
        plan = result.scalar_one_or_none()
        if not plan:
            raise HTTPException(status_code=404, detail="Content plan not found")
        
        # Удаляем связанные items (они удалятся каскадно, если настроено CASCADE)
        # Но лучше удалить явно для контроля
        items_result = await db.execute(select(ContentItem).where(ContentItem.plan_id == plan_id))
        items = items_result.scalars().all()
        
        # Удаляем связанные publications через items
        for item in items:
            publications_result = await db.execute(
                select(ContentPublication).where(ContentPublication.item_id == item.id)
            )
            publications = publications_result.scalars().all()
            for pub in publications:
                await db.delete(pub)
        
        # Удаляем items
        for item in items:
            await db.delete(item)
        
        # Удаляем план
        await db.delete(plan)
        await db.commit()
        
        logger.info(f"Content plan {plan_id} deleted successfully")
        return {"message": "Content plan deleted successfully", "plan_id": str(plan_id)}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Ошибка при удалении плана: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при удалении плана: {str(e)}")


@router.get("/plans/{plan_id}/items", response_model=List[ContentPlanItemDTO])
async def get_content_plan_items(
    plan_id: UUID,
    channel: Optional[str] = Query(None, description="Фильтр по каналу"),
    status: Optional[str] = Query(None, description="Фильтр по статусу"),
    search: Optional[str] = Query(None, description="Поиск по теме (topic)"),
    scheduled_from: Optional[str] = Query(None, description="Фильтр: слоты с scheduled_at >= этой даты (ISO)"),
    scheduled_to: Optional[str] = Query(None, description="Фильтр: слоты с scheduled_at <= этой даты (ISO)"),
    db: AsyncSession = Depends(get_db)
):
    """Получение слотов (items) контент-плана по ID плана с фильтрами."""
    import logging
    from sqlalchemy import or_
    logger = logging.getLogger(__name__)
    
    logger.info(f"GET /plans/{plan_id}/items - starting request with filters: channel={channel}, status={status}, search={search}")
    
    try:
        # Проверяем, что план существует
        try:
            plan_result = await db.execute(select(ContentPlan).where(ContentPlan.id == plan_id))
            plan = plan_result.scalar_one_or_none()
            if not plan:
                raise HTTPException(status_code=404, detail=f"Content plan {plan_id} not found")
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error getting content plan: {error_msg}", exc_info=True)
            # Проверяем, не связана ли ошибка с отсутствием таблицы или колонки
            if "does not exist" in error_msg.lower() or "relation" in error_msg.lower() or "column" in error_msg.lower():
                logger.error(f"Database schema issue: {error_msg}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Проблема со схемой БД: {error_msg}. Возможно, нужно применить миграции: alembic upgrade head"
                )
            raise
        
        # Загружаем слоты плана с фильтрами
        try:
            q = select(ContentItem).where(ContentItem.plan_id == plan_id)
            
            # Фильтр по каналу
            if channel:
                q = q.where(ContentItem.channel == channel)
            
            # Фильтр по статусу
            if status:
                q = q.where(ContentItem.status == status)
            
            # Поиск по теме (case-insensitive, частичное совпадение)
            if search:
                search_pattern = f"%{search}%"
                q = q.where(ContentItem.topic.ilike(search_pattern))
            
            # Фильтр по дате (от)
            if scheduled_from:
                try:
                    date_from = _parse_iso_datetime(scheduled_from)
                    q = q.where(ContentItem.scheduled_at >= date_from)
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"Invalid scheduled_from format: {e}")
            
            # Фильтр по дате (до)
            if scheduled_to:
                try:
                    date_to = _parse_iso_datetime(scheduled_to)
                    q = q.where(ContentItem.scheduled_at <= date_to)
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"Invalid scheduled_to format: {e}")
            
            result = await db.execute(q.order_by(ContentItem.scheduled_at.asc()))
            items = result.scalars().all()
            logger.info(f"Found {len(items)} items for plan {plan_id}")
            
            # Конвертируем UUID в строки для каждого слота
            items_dto = []
            for item in items:
                try:
                    # Создаем словарь с данными, конвертируя UUID в строки
                    # Обрабатываем spec и generated - они должны быть dict или None
                    spec_value = item.spec
                    if spec_value is not None and not isinstance(spec_value, dict):
                        logger.warning(f"Item {item.id} has non-dict spec: {type(spec_value)}, converting to dict")
                        spec_value = {} if spec_value else None
                    
                    generated_value = item.generated
                    if generated_value is not None and not isinstance(generated_value, dict):
                        logger.warning(f"Item {item.id} has non-dict generated: {type(generated_value)}, converting to dict")
                        generated_value = {} if generated_value else None
                    
                    item_dict = {
                        "id": str(item.id),
                        "plan_id": str(item.plan_id),
                        "scheduled_at": item.scheduled_at,
                        "timezone": item.timezone,
                        "channel": item.channel,
                        "content_type": item.content_type,
                        "topic": item.topic,
                        "hook": item.hook,
                        "cta": item.cta,
                        "persona": item.persona,
                        "cjm_stage": item.cjm_stage,
                        "goal": item.goal,
                        "spec": spec_value,
                        "generated": generated_value,
                        "generated_text": item.generated_text,
                        "status": item.status,
                        "published_at": item.published_at,
                    }
                    # Используем model_validate для создания DTO
                    dto = ContentPlanItemDTO.model_validate(item_dict)
                    items_dto.append(dto)
                except Exception as item_error:
                    logger.error(f"Error converting item {item.id} to DTO: {item_error}", exc_info=True)
                    logger.error(f"Item data: id={item.id}, plan_id={item.plan_id}, status={item.status}")
                    # Продолжаем обработку остальных элементов
                    continue
            
            logger.info(f"Returning {len(items_dto)} items as DTOs (processed {len(items)} total)")
            return items_dto
        except Exception as e:
            error_msg = str(e)
            # Проверяем, не связана ли ошибка с отсутствием таблицы
            if "does not exist" in error_msg.lower() or "relation" in error_msg.lower() or "content_items" in error_msg.lower():
                logger.error(f"Table content_items does not exist: {error_msg}")
                raise HTTPException(
                    status_code=500,
                    detail="Таблица content_items не существует. Выполните: python backend/create_content_tables.py"
                )
            raise
            
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        error_type = type(e).__name__
        logger.error(f"Error loading plan items for plan {plan_id} ({error_type}): {error_msg}", exc_info=True)
        
        # Более понятные сообщения для пользователя
        if "does not exist" in error_msg.lower() or "relation" in error_msg.lower():
            user_msg = "Таблицы для контент-планов не созданы. Выполните: python backend/create_content_tables.py"
        elif "connection" in error_msg.lower() or "connect" in error_msg.lower():
            user_msg = "Не удалось подключиться к базе данных. Проверьте, что Docker контейнеры запущены."
        else:
            user_msg = f"Ошибка загрузки слотов плана: {error_msg}"
        
        raise HTTPException(
            status_code=500,
            detail=user_msg
        )


@router.post("/plans/{plan_id}/items", response_model=ContentPlanItemDTO)
async def create_content_item(
    plan_id: UUID,
    request: ContentItemCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Создание нового слота в контент-плане."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Проверяем существование плана
        plan_result = await db.execute(select(ContentPlan).where(ContentPlan.id == plan_id))
        plan = plan_result.scalar_one_or_none()
        if not plan:
            raise HTTPException(status_code=404, detail="Content plan not found")
        
        # Парсим scheduled_at
        scheduled_at = _parse_iso_datetime(request.scheduled_at)
        
        # Валидация статуса
        valid_statuses = ["planned", "draft", "ready", "approved", "scheduled", "published", "failed", "cancelled"]
        if request.status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            )
        
        # Создаем новый слот
        item = ContentItem(
            plan_id=plan_id,
            scheduled_at=scheduled_at,
            timezone=request.timezone,
            channel=request.channel,
            content_type=request.content_type,
            topic=request.topic,
            hook=request.hook,
            cta=request.cta,
            persona=request.persona,
            cjm_stage=request.cjm_stage,
            goal=request.goal,
            spec=request.spec or {},
            status=request.status,
        )
        
        db.add(item)
        await db.commit()
        await db.refresh(item)
        
        logger.info(f"Content item {item.id} created successfully for plan {plan_id}")
        
        # Конвертируем в DTO
        return ContentPlanItemDTO(
            id=str(item.id),
            plan_id=str(item.plan_id),
            scheduled_at=item.scheduled_at,
            timezone=item.timezone,
            channel=item.channel,
            content_type=item.content_type,
            topic=item.topic,
            hook=item.hook,
            cta=item.cta,
            persona=item.persona,
            cjm_stage=item.cjm_stage,
            goal=item.goal,
            spec=item.spec or {},
            generated=item.generated or {},
            generated_text=item.generated_text,
            status=item.status,
            published_at=item.published_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Ошибка при создании слота: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при создании слота: {str(e)}")


@router.put("/plans/{plan_id}/items/{item_id}", response_model=ContentPlanItemDTO)
async def update_content_item(
    plan_id: UUID,
    item_id: UUID,
    request: ContentItemUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Обновление слота контент-плана."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Проверяем существование плана
        plan_result = await db.execute(select(ContentPlan).where(ContentPlan.id == plan_id))
        plan = plan_result.scalar_one_or_none()
        if not plan:
            raise HTTPException(status_code=404, detail="Content plan not found")
        
        # Проверяем существование слота и принадлежность к плану
        item_result = await db.execute(
            select(ContentItem).where(
                ContentItem.id == item_id,
                ContentItem.plan_id == plan_id
            )
        )
        item = item_result.scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="Content item not found")
        
        # Обновляем поля, если они переданы
        if request.scheduled_at is not None:
            item.scheduled_at = _parse_iso_datetime(request.scheduled_at)
        if request.timezone is not None:
            item.timezone = request.timezone
        if request.channel is not None:
            item.channel = request.channel
        if request.content_type is not None:
            item.content_type = request.content_type
        if request.topic is not None:
            item.topic = request.topic
        if request.hook is not None:
            item.hook = request.hook
        if request.cta is not None:
            item.cta = request.cta
        if request.persona is not None:
            item.persona = request.persona
        if request.cjm_stage is not None:
            item.cjm_stage = request.cjm_stage
        if request.goal is not None:
            item.goal = request.goal
        if request.spec is not None:
            item.spec = request.spec
        if request.status is not None:
            # Валидация статуса
            valid_statuses = ["planned", "draft", "ready", "approved", "scheduled", "published", "failed", "cancelled"]
            if request.status not in valid_statuses:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
                )
            item.status = request.status
        
        # Обновляем updated_at
        item.updated_at = datetime.now(dt_timezone.utc)
        
        await db.commit()
        await db.refresh(item)
        
        logger.info(f"Content item {item_id} updated successfully")
        
        # Конвертируем в DTO
        return ContentPlanItemDTO(
            id=str(item.id),
            plan_id=str(item.plan_id),
            scheduled_at=item.scheduled_at,
            timezone=item.timezone,
            channel=item.channel,
            content_type=item.content_type,
            topic=item.topic,
            hook=item.hook,
            cta=item.cta,
            persona=item.persona,
            cjm_stage=item.cjm_stage,
            goal=item.goal,
            spec=item.spec or {},
            generated=item.generated or {},
            generated_text=item.generated_text,
            status=item.status,
            published_at=item.published_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Ошибка при обновлении слота: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при обновлении слота: {str(e)}")


@router.delete("/plans/{plan_id}/items/{item_id}")
async def delete_content_item(
    plan_id: UUID,
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Удаление слота контент-плана."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Проверяем существование плана
        plan_result = await db.execute(select(ContentPlan).where(ContentPlan.id == plan_id))
        plan = plan_result.scalar_one_or_none()
        if not plan:
            raise HTTPException(status_code=404, detail="Content plan not found")
        
        # Проверяем существование слота и принадлежность к плану
        item_result = await db.execute(
            select(ContentItem).where(
                ContentItem.id == item_id,
                ContentItem.plan_id == plan_id
            )
        )
        item = item_result.scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="Content item not found")
        
        # Удаляем связанные publications
        publications_result = await db.execute(
            select(ContentPublication).where(ContentPublication.item_id == item_id)
        )
        publications = publications_result.scalars().all()
        for pub in publications:
            await db.delete(pub)
        
        # Удаляем слот
        await db.delete(item)
        await db.commit()
        
        logger.info(f"Content item {item_id} deleted successfully")
        return {"message": "Content item deleted successfully", "item_id": str(item_id)}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Ошибка при удалении слота: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при удалении слота: {str(e)}")


@router.put("/plans/{plan_id}/items/bulk/status")
async def bulk_update_items_status(
    plan_id: UUID,
    request: BulkUpdateStatusRequest,
    db: AsyncSession = Depends(get_db)
):
    """Массовое изменение статуса слотов."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Проверяем существование плана
        plan_result = await db.execute(select(ContentPlan).where(ContentPlan.id == plan_id))
        plan = plan_result.scalar_one_or_none()
        if not plan:
            raise HTTPException(status_code=404, detail="Content plan not found")
        
        # Валидация статуса
        valid_statuses = ["planned", "draft", "ready", "approved", "scheduled", "published", "failed", "cancelled"]
        if request.status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            )
        
        # Конвертируем строки в UUID
        item_uuids = []
        for item_id_str in request.item_ids:
            try:
                item_uuids.append(UUID(item_id_str))
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid item_id format: {item_id_str}")
        
        # Загружаем слоты, принадлежащие плану
        items_result = await db.execute(
            select(ContentItem).where(
                ContentItem.id.in_(item_uuids),
                ContentItem.plan_id == plan_id
            )
        )
        items = items_result.scalars().all()
        
        if len(items) != len(item_uuids):
            found_ids = {str(item.id) for item in items}
            missing_ids = [str(uid) for uid in item_uuids if str(uid) not in found_ids]
            logger.warning(f"Some items not found: {missing_ids}")
        
        # Обновляем статус для всех найденных слотов
        updated_count = 0
        for item in items:
            item.status = request.status
            item.updated_at = datetime.now(dt_timezone.utc)
            updated_count += 1
        
        await db.commit()
        
        logger.info(f"Bulk updated {updated_count} items status to {request.status} for plan {plan_id}")
        
        return {
            "message": f"Updated {updated_count} items",
            "updated_count": updated_count,
            "status": request.status
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Ошибка при массовом обновлении статуса: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при массовом обновлении статуса: {str(e)}")


@router.post("/plans/{plan_id}/items/bulk/delete")
async def bulk_delete_items(
    plan_id: UUID,
    request: BulkDeleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Массовое удаление слотов."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Проверяем существование плана
        plan_result = await db.execute(select(ContentPlan).where(ContentPlan.id == plan_id))
        plan = plan_result.scalar_one_or_none()
        if not plan:
            raise HTTPException(status_code=404, detail="Content plan not found")
        
        # Конвертируем строки в UUID
        item_uuids = []
        for item_id_str in request.item_ids:
            try:
                item_uuids.append(UUID(item_id_str))
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid item_id format: {item_id_str}")
        
        # Загружаем слоты, принадлежащие плану
        items_result = await db.execute(
            select(ContentItem).where(
                ContentItem.id.in_(item_uuids),
                ContentItem.plan_id == plan_id
            )
        )
        items = items_result.scalars().all()
        
        # Удаляем связанные publications
        deleted_count = 0
        for item in items:
            publications_result = await db.execute(
                select(ContentPublication).where(ContentPublication.item_id == item.id)
            )
            publications = publications_result.scalars().all()
            for pub in publications:
                await db.delete(pub)
            
            # Удаляем слот
            await db.delete(item)
            deleted_count += 1
        
        await db.commit()
        
        logger.info(f"Bulk deleted {deleted_count} items for plan {plan_id}")
        
        return {
            "message": f"Deleted {deleted_count} items",
            "deleted_count": deleted_count
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Ошибка при массовом удалении: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при массовом удалении: {str(e)}")


@router.post("/plans/{plan_id}/items/bulk/generate")
async def bulk_generate_content(
    plan_id: UUID,
    request: BulkGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Массовая генерация контента для слотов."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Проверяем существование плана
        plan_result = await db.execute(select(ContentPlan).where(ContentPlan.id == plan_id))
        plan = plan_result.scalar_one_or_none()
        if not plan:
            raise HTTPException(status_code=404, detail="Content plan not found")
        
        # Конвертируем строки в UUID
        item_uuids = []
        for item_id_str in request.item_ids:
            try:
                item_uuids.append(UUID(item_id_str))
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid item_id format: {item_id_str}")
        
        # Загружаем слоты, принадлежащие плану
        items_result = await db.execute(
            select(ContentItem).where(
                ContentItem.id.in_(item_uuids),
                ContentItem.plan_id == plan_id
            )
        )
        items = items_result.scalars().all()
        
        if not items:
            raise HTTPException(status_code=404, detail="No items found")
        
        # Генерируем контент для каждого слота
        agent = ContentAgent(db)
        generated_count = 0
        failed_count = 0
        errors = []
        
        for item in items:
            try:
                # Подготавливаем spec с feedback, если есть
                spec = item.spec or {}
                if isinstance(spec, dict):
                    spec = spec.copy()
                else:
                    spec = {}
                
                if request.feedback:
                    spec["user_feedback"] = request.feedback
                
                # Генерируем контент для слота
                generated = await agent.generate_item_content(
                    channel=item.channel,
                    content_type=item.content_type,
                    topic=item.topic,
                    hook=item.hook,
                    cta=item.cta,
                    persona=item.persona,
                    cjm_stage=item.cjm_stage,
                    goal=item.goal,
                    spec=spec,
                )
                
                # Сохраняем сгенерированный контент
                generated_dict = generated if isinstance(generated, dict) else {"raw_response": str(generated)}
                item.generated = generated_dict
                # Извлекаем текст из generated
                item.generated_text = (
                    generated_dict.get("generated_text") or 
                    generated_dict.get("text") or 
                    generated_dict.get("content") or
                    str(generated_dict)
                )
                item.status = "ready"
                item.updated_at = datetime.now(dt_timezone.utc)
                
                generated_count += 1
            except Exception as e:
                failed_count += 1
                error_msg = str(e)
                errors.append({"item_id": str(item.id), "error": error_msg})
                logger.error(f"Error generating content for item {item.id}: {error_msg}", exc_info=True)
        
        await db.commit()
        
        logger.info(f"Bulk generated content for {generated_count} items, {failed_count} failed for plan {plan_id}")
        
        return {
            "message": f"Generated content for {generated_count} items",
            "generated_count": generated_count,
            "failed_count": failed_count,
            "errors": errors if errors else None
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Ошибка при массовой генерации контента: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при массовой генерации контента: {str(e)}")


@router.get("/calendar", response_model=List[ContentPlanItemDTO])
async def get_calendar_items(
    start: str = Query(..., description="ISO datetime/date"),
    end: str = Query(..., description="ISO datetime/date"),
    channel: Optional[str] = None,
    status: Optional[str] = None,
    plan_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
):
    start_dt = _parse_iso_datetime(start)
    end_dt = _parse_iso_datetime(end)

    q = select(ContentItem).where(ContentItem.scheduled_at >= start_dt, ContentItem.scheduled_at <= end_dt)
    if channel:
        q = q.where(ContentItem.channel == channel)
    if status:
        q = q.where(ContentItem.status == status)
    if plan_id:
        q = q.where(ContentItem.plan_id == plan_id)

    q = q.order_by(ContentItem.scheduled_at.asc())
    result = await db.execute(q)
    return list(result.scalars().all())


class GenerateItemContentRequest(BaseModel):
    feedback: Optional[str] = None  # Пожелания пользователя для переделки


class GenerateItemContentResponse(BaseModel):
    item_id: str
    generated: dict
    preview: bool = True  # Флаг, что это превью (не сохранено)


class ApplyGeneratedContentRequest(BaseModel):
    generated: dict  # Сгенерированный контент для применения


class ApplyGeneratedContentResponse(BaseModel):
    item_id: str
    status: str
    message: str


@router.post("/items/{item_id}/generate", response_model=GenerateItemContentResponse)
async def generate_content_for_item(
    item_id: UUID,
    request: GenerateItemContentRequest = Body(GenerateItemContentRequest()),
    db: AsyncSession = Depends(get_db)
):
    """
    Генерация контента для слота без сохранения в БД.
    Результат возвращается для предпросмотра пользователем.
    """
    import logging
    import traceback
    logger = logging.getLogger(__name__)
    
    try:
        result = await db.execute(select(ContentItem).where(ContentItem.id == item_id))
        item = result.scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="Content item not found")

        logger.info(f"Generating content for item {item_id}, channel: {item.channel}, type: {item.content_type}")

        agent = ContentAgent(db)
        
        # Если есть пожелания пользователя, добавляем их в spec
        spec = item.spec or {}
        if isinstance(spec, dict):
            spec = spec.copy()
        else:
            spec = {}
            
        if request and request.feedback:
            spec["user_feedback"] = request.feedback
            logger.info(f"Generating content for item {item_id} with user feedback: {request.feedback[:100]}...")
        
        logger.info(f"Calling generate_item_content with spec: {spec}")
        generated = await agent.generate_item_content(
            channel=item.channel,
            content_type=item.content_type,
            topic=item.topic,
            hook=item.hook,
            cta=item.cta,
            persona=item.persona,
            cjm_stage=item.cjm_stage,
            goal=item.goal,
            spec=spec,
        )

        logger.info(f"Content generated successfully for item {item_id}")

        # НЕ сохраняем в БД, только возвращаем результат для предпросмотра
        generated_dict = generated if isinstance(generated, dict) else {"raw_response": str(generated)}
        
        return GenerateItemContentResponse(
            item_id=str(item.id),
            generated=generated_dict,
            preview=True
        )
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        error_type = type(e).__name__
        logger.error(f"Error generating content for item {item_id} ({error_type}): {error_msg}")
        logger.error(traceback.format_exc())
        
        # Более понятные сообщения для пользователя
        if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
            user_msg = "Таймаут при генерации контента. Попробуйте снова."
        elif "api" in error_msg.lower() or "key" in error_msg.lower():
            user_msg = f"Ошибка API: {error_msg}. Проверьте, что OPENROUTER_API_KEY установлен и валиден."
        elif "json" in error_msg.lower() or "parse" in error_msg.lower():
            user_msg = f"Ошибка парсинга ответа от AI: {error_msg}. Попробуйте снова."
        else:
            user_msg = f"Ошибка генерации контента: {error_msg}"
        
        raise HTTPException(
            status_code=500,
            detail=user_msg
        )


@router.post("/items/{item_id}/apply", response_model=ApplyGeneratedContentResponse)
async def apply_generated_content(
    item_id: UUID,
    request: ApplyGeneratedContentRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Применение сгенерированного контента к слоту (сохранение в БД).
    """
    import logging
    logger = logging.getLogger(__name__)
    
    result = await db.execute(select(ContentItem).where(ContentItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Content item not found")

    # Сохраняем сгенерированный контент
    item.generated = request.generated
    item.generated_text = request.generated.get("text") if isinstance(request.generated, dict) else None
    item.status = "draft" if item.status == "planned" else item.status

    await db.commit()
    await db.refresh(item)
    
    logger.info(f"Applied generated content to item {item_id}")
    
    return ApplyGeneratedContentResponse(
        item_id=str(item.id),
        status=item.status,
        message="Контент успешно применен"
    )


class PublishItemRequest(BaseModel):
    provider: str = "glame"
    payload: Optional[dict] = None


class PublishItemResponse(BaseModel):
    item_id: str
    publication_id: str
    status: str


@router.post("/items/{item_id}/publish", response_model=PublishItemResponse)
async def publish_item(item_id: UUID, request: PublishItemRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ContentItem).where(ContentItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Content item not found")

    publication = ContentPublication(
        item_id=item.id,
        provider=request.provider,
        status="success",
        request_payload=request.payload or {},
        response_payload={"note": "stub publisher: marked as published in DB"},
        external_id=None,
    )
    db.add(publication)

    item.status = "published"
    item.published_at = datetime.now(tz=dt_timezone.utc)
    item.publication_metadata = {
        **(item.publication_metadata or {}),
        "provider": request.provider,
        "publication_id": None,
    }

    await db.commit()
    await db.refresh(publication)

    return PublishItemResponse(item_id=str(item.id), publication_id=str(publication.id), status=item.status)


@router.get("/yandex/calendars")
async def yandex_calendars():
    """
    Список доступных календарей Яндекс (CalDAV), используя переменные окружения.

    Требуется:
    - YANDEX_CALDAV_USERNAME
    - YANDEX_CALDAV_PASSWORD (лучше пароль приложения)
    Опционально:
    - YANDEX_CALDAV_URL (по умолчанию https://caldav.yandex.ru)
    """
    try:
        calendars = await anyio.to_thread.run_sync(yandex_list_calendars)
        return {"calendars": calendars}
    except ValueError as e:
        # ValueError содержит детальные инструкции для пользователя
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        error_msg = str(e)
        # Если это ошибка авторизации, даем более понятное сообщение
        if "Unauthorized" in error_msg or "401" in error_msg or "AuthorizationError" in error_msg:
            raise HTTPException(
                status_code=401,
                detail=(
                    "Yandex CalDAV authorization failed. "
                    "Please check:\n"
                    "1. YANDEX_CALDAV_USERNAME is correct (usually your Yandex email)\n"
                    "2. YANDEX_CALDAV_PASSWORD is a Yandex App Password (not your regular password if 2FA is enabled)\n"
                    "   To create App Password: https://id.yandex.ru/security/app-passwords\n"
                    "3. No extra spaces in .env file values\n"
                    "4. Backend was restarted after changing .env"
                )
            )
        raise HTTPException(status_code=500, detail=f"Yandex CalDAV error: {error_msg}")


class YandexSyncRequest(BaseModel):
    calendar_url: Optional[str] = None
    calendar_name: Optional[str] = None
    duration_minutes: int = 60


@router.post("/plans/{plan_id}/sync/yandex")
async def sync_plan_to_yandex(plan_id: UUID, request: YandexSyncRequest, db: AsyncSession = Depends(get_db)):
    """
    Выгрузка контент-плана в Яндекс.Календарь (CalDAV).

    События создаются/обновляются по UID вида: <content_item_id>@glame.ai
    """
    plan_result = await db.execute(select(ContentPlan).where(ContentPlan.id == plan_id))
    plan = plan_result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Content plan not found")

    items_result = await db.execute(select(ContentItem).where(ContentItem.plan_id == plan_id))
    items = list(items_result.scalars().all())

    def _sync_one(item: ContentItem):
        uid = f"{item.id}@glame.ai"
        dtstart = item.scheduled_at
        if dtstart is None:
            raise ValueError("Item has no scheduled_at")
        
        # Убеждаемся, что dtstart имеет правильный timezone для vobject
        # Это важно, так как PostgreSQL может возвращать datetime с timezone.utc
        from dateutil.tz import gettz
        if dtstart.tzinfo is None:
            dtstart = dtstart.replace(tzinfo=gettz("UTC"))
        elif dtstart.tzinfo == dt_timezone.utc or (hasattr(dtstart.tzinfo, 'utcoffset') and dtstart.tzinfo.utcoffset(dtstart) == timedelta(0)):
            # Конвертируем стандартный UTC в dateutil UTC для совместимости с vobject
            dtstart = dtstart.replace(tzinfo=gettz("UTC"))

        summary = f"[{item.channel}] {item.topic or item.content_type}"
        description_parts = [
            f"GLAME Content Plan: {plan.name or plan.id}",
            f"Channel: {item.channel}",
            f"Type: {item.content_type}",
            f"Status: {item.status}",
        ]
        if item.hook:
            description_parts.append(f"Hook: {item.hook}")
        if item.cta:
            description_parts.append(f"CTA: {item.cta}")
        if item.generated_text:
            description_parts.append("")
            description_parts.append("Generated:")
            description_parts.append(item.generated_text)
        description = "\n".join(description_parts)

        # override calendar selection via env-like config: we pass None and let service read env,
        # but allow overriding calendar_url/name for this request by temporarily patching env? Not safe.
        # For MVP: if provided, set env for the current process call only via direct cfg object.
        cfg = yandex_get_config_from_env()
        if request.calendar_url:
            cfg.calendar_url = request.calendar_url
        if request.calendar_name:
            cfg.calendar_name = request.calendar_name

        return yandex_upsert_event_by_uid(
            cfg=cfg,
            uid=uid,
            dtstart=dtstart,
            duration_minutes=request.duration_minutes,
            summary=summary,
            description=description,
        )

    results = []
    created = 0
    updated = 0
    failed = 0

    for item in items:
        try:
            r = await anyio.to_thread.run_sync(_sync_one, item)
            results.append({"item_id": str(item.id), **r})
            if r.get("action") == "created":
                created += 1
            elif r.get("action") == "updated":
                updated += 1

            # сохраняем href в метаданные айтема (чтобы потом можно было отлаживать/удалять)
            meta = item.publication_metadata or {}
            meta["yandex_calendar"] = {
                "uid": f"{item.id}@glame.ai",
                "href": r.get("href"),
                "synced_at": datetime.now(tz=dt_timezone.utc).isoformat(),
            }
            item.publication_metadata = meta
        except Exception as e:
            failed += 1
            results.append({"item_id": str(item.id), "error": str(e)})

    await db.commit()

    return {"plan_id": str(plan_id), "created": created, "updated": updated, "failed": failed, "results": results}


def _ics_escape(text: str) -> str:
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


@router.get("/plans/{plan_id}/export/ics", response_class=PlainTextResponse)
async def export_plan_ics(plan_id: UUID, db: AsyncSession = Depends(get_db)):
    """Экспорт плана в iCalendar (.ics) для импорта в Google/Outlook/Apple Calendar."""
    plan_result = await db.execute(select(ContentPlan).where(ContentPlan.id == plan_id))
    plan = plan_result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Content plan not found")

    items_result = await db.execute(
        select(ContentItem).where(ContentItem.plan_id == plan_id).order_by(ContentItem.scheduled_at.asc())
    )
    items = list(items_result.scalars().all())

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//GLAME//Content Calendar//RU",
        "CALSCALE:GREGORIAN",
    ]

    for it in items:
        dtstart = it.scheduled_at
        if dtstart.tzinfo is None:
            dtstart = dtstart.replace(tzinfo=dt_timezone.utc)
        dtstart_utc = dtstart.astimezone(dt_timezone.utc)
        dtend_utc = dtstart_utc + timedelta(hours=1)

        summary = f"[{it.channel}] {it.topic or it.content_type}"
        description_parts = [
            f"Channel: {it.channel}",
            f"Type: {it.content_type}",
            f"Status: {it.status}",
        ]
        if it.hook:
            description_parts.append(f"Hook: {it.hook}")
        if it.cta:
            description_parts.append(f"CTA: {it.cta}")
        if it.generated_text:
            description_parts.append("")
            description_parts.append("Generated:")
            description_parts.append(it.generated_text)

        description = "\n".join(description_parts)

        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{it.id}@glame.ai",
                f"DTSTAMP:{datetime.now(tz=dt_timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
                f"DTSTART:{dtstart_utc.strftime('%Y%m%dT%H%M%SZ')}",
                f"DTEND:{dtend_utc.strftime('%Y%m%dT%H%M%SZ')}",
                f"SUMMARY:{_ics_escape(summary)}",
                f"DESCRIPTION:{_ics_escape(description)}",
                "END:VEVENT",
            ]
        )

    lines.append("END:VCALENDAR")
    ics = "\r\n".join(lines) + "\r\n"
    return PlainTextResponse(content=ics, media_type="text/calendar; charset=utf-8")


# ============================================================================
# Product Description Management (SEO-оптимизированные описания товаров)
# ============================================================================

class ProductDescriptionGenerateRequest(BaseModel):
    product_id: UUID
    rewrite_existing: bool = False
    seo_keywords: Optional[List[str]] = None
    target_length: Optional[str] = "medium"  # short, medium, long


class ProductDescriptionResponse(BaseModel):
    product_id: str
    product_name: str
    old_description: Optional[str] = None
    new_description: str
    length: int
    seo_keywords_used: List[str]
    rewritten: bool


class ProductWithoutDescriptionResponse(BaseModel):
    id: str
    name: str
    brand: Optional[str] = None
    category: Optional[str] = None
    price: int
    tags: List[str] = []
    has_description: bool
    description_length: int = 0
    external_code: Optional[str] = None  # Артикул из каталога


# ============================================================================
# Product Search Endpoint - должен быть ПЕРВЫМ среди product роутов
# ============================================================================
@router.get("/products/search", response_model=List[ProductWithoutDescriptionResponse])
async def search_product_by_code_or_name(
    query: str = Query(..., min_length=1, description="Поисковый запрос (артикул или название)"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """
    Поиск товара по артикулу или названию для переписывания описания.
    Возвращает товары независимо от наличия описания.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"SEARCH ENDPOINT CALLED: query='{query}', limit={limit}")
        search_term = f"%{query.strip()}%"
        
        # Поиск по названию и артикулу
        from sqlalchemy import or_, and_
        search_filters = [
            Product.name.ilike(search_term),
        ]
        # Добавляем поиск по артикулу только если поле не NULL
        search_filters.append(
            and_(
                Product.external_code.isnot(None),
                Product.external_code.ilike(search_term)
            )
        )
        
        query_filter = select(Product).where(
            Product.is_active == True
        ).where(
            or_(*search_filters)
        )
        
        query_filter = query_filter.limit(limit)
        result = await db.execute(query_filter)
        products = result.scalars().all()
        
        logger.info(f"Found {len(products)} products for search query: '{query}'")
        
        response_data = [
            ProductWithoutDescriptionResponse(
                id=str(p.id),
                name=p.name,
                brand=p.brand,
                category=p.category,
                price=p.price,
                tags=p.tags or [],
                has_description=p.description is not None,
                description_length=len(p.description) if p.description else 0,
                external_code=p.external_code,
            )
            for p in products
        ]
        
        logger.info(f"SEARCH ENDPOINT RETURNING: {len(response_data)} products")
        return response_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при поиске товара: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при поиске товара: {str(e)}")


@router.get("/products/without-description", response_model=List[ProductWithoutDescriptionResponse])
async def get_products_without_description(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    min_length: int = Query(50, ge=0, description="Минимальная длина описания для считания 'хорошим'"),
    db: AsyncSession = Depends(get_db),
):
    """
    Поиск товаров без описания или с описанием короче min_length символов.
    Используется для автоматического поиска карточек, которым нужны описания.
    """
    try:
        # Находим товары без описания или с коротким описанием
        query = select(Product).where(
            Product.is_active == True
        ).where(
            (Product.description.is_(None)) | 
            (func.length(Product.description) < min_length)
        )
        
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        products = result.scalars().all()
        
        return [
            ProductWithoutDescriptionResponse(
                id=str(p.id),
                name=p.name,
                brand=p.brand,
                category=p.category,
                price=p.price,
                tags=p.tags or [],
                has_description=p.description is not None,
                description_length=len(p.description) if p.description else 0,
                external_code=p.external_code,
            )
            for p in products
        ]
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Ошибка при поиске товаров без описания: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при поиске товаров: {str(e)}")


@router.post("/products/generate-description", response_model=ProductDescriptionResponse)
async def generate_product_description(
    request: ProductDescriptionGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Генерация или переписывание SEO-оптимизированного описания товара.
    Возвращает предпросмотр без сохранения в БД.
    
    Описание будет:
    - SEO-оптимизированным (ключевые слова, структура)
    - AI-оптимизированным (для поисковых систем с AI)
    - Читаемым для человека (естественный язык)
    
    Для сохранения используйте POST /products/{product_id}/apply-description
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Получаем товар
        result = await db.execute(select(Product).where(Product.id == request.product_id))
        product = result.scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        
        old_description = product.description
        
        # Генерируем описание через ContentAgent
        agent = ContentAgent(db)
        logger.info(f"Generating description for product: {product.name} (ID: {request.product_id})")
        
        result_data = await agent.generate_product_description(
            product=product,
            rewrite_existing=request.rewrite_existing,
            seo_keywords=request.seo_keywords,
            target_length=request.target_length or "medium",
        )
        
        # НЕ сохраняем описание в БД, только возвращаем предпросмотр
        logger.info(f"Description generated (preview) for product: {product.name}")
        
        return ProductDescriptionResponse(
            product_id=str(product.id),
            product_name=product.name,
            old_description=old_description,
            new_description=result_data["description"],
            length=result_data["length"],
            seo_keywords_used=result_data["seo_keywords_used"],
            rewritten=result_data["rewritten"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при генерации описания товара: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при генерации описания: {str(e)}"
        )


class ApplyProductDescriptionRequest(BaseModel):
    description: str


class ApplyProductDescriptionResponse(BaseModel):
    product_id: str
    product_name: str
    message: str


@router.post("/products/{product_id}/apply-description", response_model=ApplyProductDescriptionResponse)
async def apply_product_description(
    product_id: UUID,
    request: ApplyProductDescriptionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Применение сгенерированного описания к товару (сохранение в БД).
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Получаем товар
        result = await db.execute(select(Product).where(Product.id == product_id))
        product = result.scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        
        # Сохраняем описание в БД
        product.description = request.description
        await db.commit()
        await db.refresh(product)
        
        logger.info(f"Description applied to product: {product.name} (ID: {product_id})")
        
        return ApplyProductDescriptionResponse(
            product_id=str(product.id),
            product_name=product.name,
            message="Описание успешно применено к товару"
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Ошибка при применении описания товара: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при применении описания: {str(e)}"
        )


@router.post("/products/batch-generate-descriptions")
async def batch_generate_descriptions(
    product_ids: List[UUID],
    rewrite_existing: bool = False,
    target_length: Optional[str] = "medium",
    db: AsyncSession = Depends(get_db),
):
    """
    Массовая генерация описаний для нескольких товаров.
    Полезно для обработки списка товаров без описаний.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    results = []
    errors = []
    
    agent = ContentAgent(db)
    
    for product_id in product_ids:
        try:
            result = await db.execute(select(Product).where(Product.id == product_id))
            product = result.scalar_one_or_none()
            if not product:
                errors.append({"product_id": str(product_id), "error": "Product not found"})
                continue
            
            old_description = product.description
            
            # Пропускаем, если описание есть и не нужно переписывать
            if not rewrite_existing and old_description and len(old_description) >= 50:
                results.append({
                    "product_id": str(product_id),
                    "product_name": product.name,
                    "status": "skipped",
                    "reason": "Description already exists",
                })
                continue
            
            result_data = await agent.generate_product_description(
                product=product,
                rewrite_existing=rewrite_existing,
                seo_keywords=None,
                target_length=target_length or "medium",
            )
            
            product.description = result_data["description"]
            await db.commit()
            await db.refresh(product)
            
            results.append({
                "product_id": str(product_id),
                "product_name": product.name,
                "status": "success",
                "description_length": result_data["length"],
                "rewritten": result_data["rewritten"],
            })
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Ошибка при генерации описания для товара {product_id}: {e}")
            errors.append({"product_id": str(product_id), "error": str(e)})
    
    return {
        "total": len(product_ids),
        "success": len(results),
        "errors": len(errors),
        "results": results,
        "errors_detail": errors,
    }


# --- Обработка фото украшений (AI Content Agent) ---

JEWELRY_PHOTO_MAX_FILES = 5
JEWELRY_PHOTO_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


class JewelryPhotoApplyRequest(BaseModel):
    """Тело запроса для добавления обработанных фото к карточке товара."""
    article: str
    image_urls: Optional[List[str]] = None
    image_url: Optional[str] = None  # обратная совместимость: один URL


class JewelryPhotoApplyResponse(BaseModel):
    success: bool
    product_id: str
    images_count: int


@router.post("/jewelry-photo/process")
async def process_jewelry_photos(
    article: str = Form(...),
    file: Optional[UploadFile] = File(None),
    files: Optional[List[UploadFile]] = File(None),
    revision_description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Обработка одного или нескольких фото украшений: удаление фона, белый фон, единый стиль.
    Модель берётся из настроек (Модель для генерации изображений).
    revision_description — описание доработок при перегенерации (опционально).
    """
    article_clean = (article or "").strip()
    if not article_clean:
        raise HTTPException(status_code=400, detail="Артикул изделия обязателен.")

    # Собираем список файлов: либо один file, либо несколько files
    uploads = []
    if files:
        uploads = list(files)
    elif file:
        uploads = [file]
    if not uploads:
        raise HTTPException(status_code=400, detail="Загрузите хотя бы одно изображение (file или files).")
    if len(uploads) > JEWELRY_PHOTO_MAX_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Максимум {JEWELRY_PHOTO_MAX_FILES} фото за один запрос.",
        )

    image_bytes_list = []
    for i, u in enumerate(uploads):
        if not u.filename:
            raise HTTPException(status_code=400, detail=f"Файл {i + 1} без имени.")
        ct = (u.content_type or "").lower()
        if ct not in ("image/jpeg", "image/png", "image/jpg"):
            raise HTTPException(
                status_code=400,
                detail=f"Файл {u.filename}: допускаются только image/jpeg, image/png.",
            )
        data = await u.read()
        if len(data) > JEWELRY_PHOTO_MAX_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"Файл {u.filename} превышает лимит 10 MB.",
            )
        image_bytes_list.append(data)

    revision = (revision_description or "").strip() or None

    service = JewelryPhotoService(db=db)
    try:
        urls = await service.process_batch(image_bytes_list, article_clean, revision_description=revision)
    except ModelDoesNotSupportImageError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except JewelryPhotoServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Jewelry photo process failed")
        err_msg = str(e)
        raise HTTPException(
            status_code=500,
            detail=err_msg if err_msg else "Ошибка обработки фото. Проверьте логи сервера.",
        )

    # Явный JSON-ответ со списком строк, чтобы избежать проблем сериализации
    url_list = [str(u) for u in urls]
    logger.info("Jewelry photo process success: %s urls for article %s", len(url_list), article_clean)
    return JSONResponse(status_code=200, content={"urls": url_list})


@router.post("/jewelry-photo/apply", response_model=JewelryPhotoApplyResponse)
async def apply_jewelry_photos_to_product(
    request: JewelryPhotoApplyRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Добавляет обработанные изображения в начало списка изображений товара (product.images) по артикулу.
    """
    article_clean = (request.article or "").strip()
    if not article_clean:
        raise HTTPException(status_code=400, detail="Артикул обязателен.")

    image_urls = request.image_urls or []
    if not image_urls and request.image_url:
        image_urls = [request.image_url]
    if not image_urls:
        raise HTTPException(status_code=400, detail="Укажите image_urls или image_url.")

    from sqlalchemy import or_
    result = await db.execute(
        select(Product).where(
            Product.article.isnot(None),
            func.lower(Product.article) == article_clean.lower(),
        ).limit(1)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Товар с таким артикулом не найден.")

    existing = list(product.images) if product.images and isinstance(product.images, list) else []
    product.images = list(image_urls) + existing
    await db.commit()
    await db.refresh(product)

    return JewelryPhotoApplyResponse(
        success=True,
        product_id=str(product.id),
        images_count=len(product.images),
    )


@router.get("/jewelry-photo/history")
async def get_jewelry_photo_history():
    """
    История генераций: список сохранённых обработанных фото, сгруппированных по артикулу.
    """
    service = JewelryPhotoService(db=None)
    items = service.list_history()
    return JSONResponse(status_code=200, content={"items": items})


@router.delete("/jewelry-photo/file")
async def delete_jewelry_photo_file(url: str = Query(..., description="URL файла, например /static/jewelry_processed/U10046_1.png")):
    """
    Удаляет один сохранённый файл обработанного фото по URL.
    """
    service = JewelryPhotoService(db=None)
    try:
        deleted = service.delete_file_by_url(url)
        if not deleted:
            raise HTTPException(status_code=404, detail="Файл не найден.")
        return JSONResponse(status_code=200, content={"deleted": True})
    except JewelryPhotoServiceError as e:
        raise HTTPException(status_code=400, detail=str(e))
