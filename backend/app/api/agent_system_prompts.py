"""
API endpoints для управления системными промптами агентов.
Включает версионность, интеграцию с AI Маркетологом и генерацию промптов.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, and_
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from pathlib import Path

from app.database.connection import get_db
from app.api.auth import get_current_user, get_current_user_optional
from app.models.user import User
from app.models.agent_system_prompt import (
    AgentSystemPrompt,
    AgentPromptVersionHistory,
    AgentPromptGenerationRequest
)
from app.agents.advanced_content_agent import AdvancedContentAgent
from app.agents.prompt_parser import parse_agent_prompts_from_markdown
from app.services.consultant_training_service import (
    DEFAULT_TRAINING_MATERIAL_REFORMATTER_PROMPT,
    TRAINING_MATERIAL_REFORMATTER_AGENT_TYPE,
)

router = APIRouter(tags=["agent-system-prompts"])


# ============================================================================
# Pydantic Models
# ============================================================================

class CreatePromptVersionRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Название промпта")
    system_prompt: str = Field(..., min_length=10, description="Текст системного промпта")
    description: Optional[str] = Field(None, description="Описание версии")
    version_name: Optional[str] = Field(None, description="Название версии")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Метаданные")


class UpdatePromptRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    version_name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class MarketerReviewRequest(BaseModel):
    status: str = Field(..., pattern="^(approved|rejected|needs_revision)$")
    feedback: Optional[str] = Field(None, description="Обратная связь от маркетолога")


class GeneratePromptRequest(BaseModel):
    user_description: str = Field(..., min_length=10, description="Описание задачи пользователя")
    target_tone: Optional[str] = Field(None, description="Желаемый тон")
    target_audience: Optional[str] = Field(None, description="Целевая аудитория")
    constraints: Optional[List[str]] = Field(default_factory=list, description="Ограничения")


class PromptVersionResponse(BaseModel):
    id: Any
    agent_type: Any
    version: Any
    version_name: Optional[Any] = None
    name: Any
    description: Optional[Any] = None
    system_prompt: Optional[Any] = None
    metadata: Optional[Any] = None
    is_active: Any = False
    is_default: Any = False
    marketer_review_status: Optional[Any] = None
    marketer_feedback: Optional[Any] = None
    created_by: Optional[Any] = None
    approved_by: Optional[Any] = None
    created_at: Optional[Any] = None
    
    class Config:
        from_attributes = True


class PromptHistoryResponse(BaseModel):
    id: str
    prompt_id: str
    change_type: str
    change_comment: Optional[str]
    changed_by: Optional[str]
    changed_at: str
    previous_value: Optional[Dict]
    new_value: Optional[Dict]


class GenerationRequestResponse(BaseModel):
    id: str
    agent_type: str
    user_description: str
    generated_prompt: Optional[str]
    status: str
    error_message: Optional[str]
    created_at: str
    completed_at: Optional[str]


class SeedPromptsResponse(BaseModel):
    seeded: int
    updated: int
    skipped: int
    agents: List[str]


def prompt_version_response(prompt: AgentSystemPrompt) -> PromptVersionResponse:
    return PromptVersionResponse(
        id=str(prompt.id),
        agent_type=prompt.agent_type,
        version=prompt.version,
        version_name=prompt.version_name,
        name=prompt.name,
        description=prompt.description,
        system_prompt=prompt.system_prompt,
        metadata=prompt.meta_data or {},
        is_active=prompt.is_active,
        is_default=prompt.is_default,
        marketer_review_status=prompt.marketer_review_status,
        marketer_feedback=prompt.marketer_feedback,
        created_by=str(prompt.created_by) if prompt.created_by else None,
        approved_by=str(prompt.approved_by) if prompt.approved_by else None,
        created_at=prompt.created_at.isoformat() if prompt.created_at else None,
    )


async def ensure_training_material_reformatter_default_prompt(
    db: AsyncSession,
    current_user: Optional[User] = None,
) -> AgentSystemPrompt:
    """Persist the code fallback prompt so admins can see and edit it."""
    result = await db.execute(
        select(AgentSystemPrompt)
        .where(AgentSystemPrompt.agent_type == TRAINING_MATERIAL_REFORMATTER_AGENT_TYPE)
        .order_by(desc(AgentSystemPrompt.version))
    )
    prompts = result.scalars().all()
    active = next((prompt for prompt in prompts if prompt.is_active), None)
    if active:
        return active

    prompt = AgentSystemPrompt(
        agent_type=TRAINING_MATERIAL_REFORMATTER_AGENT_TYPE,
        version=(int(prompts[0].version or 0) + 1) if prompts else 1,
        version_name="Default GLAME training reformatter",
        name="Базовый промпт агента учебных материалов",
        description=(
            "Переформатирование загруженных исходников GLAME в draft learning pack: "
            "слайды, практика, шаблон ответа, критерии проверки и admin-only visual/speaker notes."
        ),
        system_prompt=DEFAULT_TRAINING_MATERIAL_REFORMATTER_PROMPT,
        meta_data={"source": "code_default", "seeded": True, "auto_created": True},
        is_active=True,
        is_default=True,
        marketer_review_status="approved",
        created_by=current_user.id if current_user else None,
        approved_by=current_user.id if current_user else None,
        approved_at=datetime.utcnow(),
    )
    db.add(prompt)
    await db.commit()
    await db.refresh(prompt)
    return prompt


# ============================================================================
# Endpoints для управления версиями
# ============================================================================

@router.post("/seed-defaults", response_model=SeedPromptsResponse)
async def seed_default_agent_prompts(
    docs_path: str = Body("docs/admin/GLAME_AI_Agent_System_Prompts_v1_2.md", embed=True),
    activate: bool = Body(True, embed=True),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Загрузить типовые системные промпты агентов из markdown-документа в БД."""
    root = Path(__file__).resolve().parents[3]
    path = (root / docs_path).resolve()
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Prompt document not found: {docs_path}")

    text = path.read_text(encoding="utf-8")
    parsed = parse_agent_prompts_from_markdown(text, docs_path)

    seeded = 0
    updated = 0
    skipped = 0
    agents: List[str] = []
    for item in parsed:
        agents.append(item["agent_type"])
        result = await db.execute(
            select(AgentSystemPrompt)
            .where(
                and_(
                    AgentSystemPrompt.agent_type == item["agent_type"],
                    AgentSystemPrompt.is_default == True,
                )
            )
            .order_by(desc(AgentSystemPrompt.version))
        )
        existing = result.scalars().first()
        if existing and existing.system_prompt == item["system_prompt"]:
            skipped += 1
            if activate and not existing.is_active:
                active_result = await db.execute(
                    select(AgentSystemPrompt).where(AgentSystemPrompt.agent_type == item["agent_type"])
                )
                for prompt in active_result.scalars().all():
                    prompt.is_active = False
                existing.is_active = True
            continue

        if activate:
            active_result = await db.execute(
                select(AgentSystemPrompt).where(AgentSystemPrompt.agent_type == item["agent_type"])
            )
            for prompt in active_result.scalars().all():
                prompt.is_active = False

        prompt = AgentSystemPrompt(
            agent_type=item["agent_type"],
            version=(int(existing.version or 1) + 1) if existing else 1,
            version_name="Default from docs",
            name=item["name"],
            description=item["description"],
            system_prompt=item["system_prompt"],
            meta_data={"source": docs_path, "seeded": True},
            is_active=activate,
            is_default=True,
            marketer_review_status="approved",
            created_by=current_user.id if current_user else None,
            approved_by=current_user.id if current_user else None,
            approved_at=datetime.utcnow(),
        )
        db.add(prompt)
        if existing:
            updated += 1
        else:
            seeded += 1

    await db.commit()
    return SeedPromptsResponse(seeded=seeded, updated=updated, skipped=skipped, agents=agents)

@router.get("/{agent_type}/versions", response_model=List[PromptVersionResponse])
async def list_prompt_versions(
    agent_type: str,
    include_inactive: bool = Query(True, description="Включить неактивные версии"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Получение списка версий системных промптов для агента"""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Fetching versions for agent: {agent_type}")

    if agent_type == TRAINING_MATERIAL_REFORMATTER_AGENT_TYPE:
        await ensure_training_material_reformatter_default_prompt(db, current_user)
    
    query = select(AgentSystemPrompt).where(
        AgentSystemPrompt.agent_type == agent_type
    ).order_by(desc(AgentSystemPrompt.version))
    
    if not include_inactive:
        query = query.where(AgentSystemPrompt.is_active == True)
    
    result = await db.execute(query)
    prompts = result.scalars().all()
    
    return [prompt_version_response(p) for p in prompts]


@router.post("/{agent_type}/versions", response_model=PromptVersionResponse)
async def create_prompt_version(
    agent_type: str,
    request: CreatePromptVersionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Создание новой версии системного промпта для агента"""
    # Используем AdvancedContentAgent как универсальный инструмент для работы с промптами
    agent = AdvancedContentAgent(db)
    # Временно меняем тип агента для корректного сохранения
    original_type = agent.AGENT_TYPE
    agent.AGENT_TYPE = agent_type
    
    try:
        prompt = await agent.create_prompt_version(
            name=request.name,
            system_prompt=request.system_prompt,
            description=request.description,
            metadata=request.metadata,
            created_by=str(current_user.id) if current_user else None,
            version_name=request.version_name
        )
        
        return PromptVersionResponse(
            id=str(prompt.id),
            agent_type=prompt.agent_type,
            version=prompt.version,
            version_name=prompt.version_name,
            name=prompt.name,
            description=prompt.description,
            system_prompt=prompt.system_prompt,
            metadata=prompt.meta_data or {},
            is_active=prompt.is_active,
            is_default=prompt.is_default,
            marketer_review_status=prompt.marketer_review_status,
            marketer_feedback=prompt.marketer_feedback,
            created_by=str(prompt.created_by) if prompt.created_by else None,
            approved_by=None,
            created_at=prompt.created_at.isoformat() if prompt.created_at else None
        )
    finally:
        agent.AGENT_TYPE = original_type


@router.put("/{agent_type}/versions/{prompt_id}", response_model=PromptVersionResponse)
async def update_prompt_version(
    agent_type: str,
    prompt_id: UUID,
    request: UpdatePromptRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Обновление версии системного промпта"""
    agent = AdvancedContentAgent(db)
    original_type = agent.AGENT_TYPE
    agent.AGENT_TYPE = agent_type
    
    try:
        prompt = await agent.update_prompt_version(
            prompt_id=str(prompt_id),
            name=request.name,
            description=request.description,
            system_prompt=request.system_prompt,
            version_name=request.version_name,
            metadata=request.metadata,
            updated_by=str(current_user.id) if current_user else None
        )
        
        return PromptVersionResponse(
            id=str(prompt.id),
            agent_type=prompt.agent_type,
            version=prompt.version,
            version_name=prompt.version_name,
            name=prompt.name,
            description=prompt.description,
            system_prompt=prompt.system_prompt,
            metadata=prompt.meta_data or {},
            is_active=prompt.is_active,
            is_default=prompt.is_default,
            marketer_review_status=prompt.marketer_review_status,
            marketer_feedback=prompt.marketer_feedback,
            created_by=str(prompt.created_by) if prompt.created_by else None,
            approved_by=str(prompt.approved_by) if prompt.approved_by else None,
            created_at=prompt.created_at.isoformat() if prompt.created_at else None
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    finally:
        agent.AGENT_TYPE = original_type


@router.post("/{agent_type}/versions/{prompt_id}/activate", response_model=PromptVersionResponse)
async def activate_prompt_version(
    agent_type: str,
    prompt_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Активация версии системного промпта"""
    agent = AdvancedContentAgent(db)
    original_type = agent.AGENT_TYPE
    agent.AGENT_TYPE = agent_type
    
    try:
        prompt = await agent.activate_prompt_version(
            prompt_id=str(prompt_id),
            activated_by=str(current_user.id) if current_user else None
        )
        
        return PromptVersionResponse(
            id=str(prompt.id),
            agent_type=prompt.agent_type,
            version=prompt.version,
            version_name=prompt.version_name,
            name=prompt.name,
            description=prompt.description,
            system_prompt=prompt.system_prompt,
            metadata=prompt.meta_data or {},
            is_active=prompt.is_active,
            is_default=prompt.is_default,
            marketer_review_status=prompt.marketer_review_status,
            marketer_feedback=prompt.marketer_feedback,
            created_by=str(prompt.created_by) if prompt.created_by else None,
            approved_by=str(prompt.approved_by) if prompt.approved_by else None,
            created_at=prompt.created_at.isoformat() if prompt.created_at else None
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    finally:
        agent.AGENT_TYPE = original_type


@router.get("/{agent_type}/versions/{prompt_id}/history", response_model=List[PromptHistoryResponse])
async def get_prompt_history(
    agent_type: str,
    prompt_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Получение истории изменений промпта"""
    agent = AdvancedContentAgent(db)
    
    try:
        history = await agent.get_prompt_history(str(prompt_id))
        
        return [
            PromptHistoryResponse(
                id=str(h.id),
                prompt_id=str(h.prompt_id),
                change_type=h.change_type,
                change_comment=h.change_comment,
                changed_by=str(h.changed_by) if h.changed_by else None,
                changed_at=h.changed_at.isoformat() if h.changed_at else None,
                previous_value=h.previous_value,
                new_value=h.new_value
            )
            for h in history
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{agent_type}/versions/{prompt_id}/marketer-review", response_model=PromptVersionResponse)
async def review_prompt_as_marketer(
    agent_type: str,
    prompt_id: UUID,
    request: MarketerReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Ревью промпта AI Маркетологом.
    Требует аутентификации с правами маркетолога.
    """
    agent = AdvancedContentAgent(db)
    
    try:
        prompt = await agent.review_prompt_as_marketer(
            prompt_id=str(prompt_id),
            status=request.status,
            feedback=request.feedback,
            reviewed_by=str(current_user.id)
        )
        
        return PromptVersionResponse(
            id=str(prompt.id),
            agent_type=prompt.agent_type,
            version=prompt.version,
            version_name=prompt.version_name,
            name=prompt.name,
            description=prompt.description,
            system_prompt=prompt.system_prompt,
            metadata=prompt.meta_data or {},
            is_active=prompt.is_active,
            is_default=prompt.is_default,
            marketer_review_status=prompt.marketer_review_status,
            marketer_feedback=prompt.marketer_feedback,
            created_by=str(prompt.created_by) if prompt.created_by else None,
            approved_by=str(prompt.approved_by) if prompt.approved_by else None,
            created_at=prompt.created_at.isoformat() if prompt.created_at else None
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================================
# Endpoints для генерации промптов
# ============================================================================

@router.post("/{agent_type}/generate-from-description", response_model=GenerationRequestResponse)
async def generate_prompt_from_description(
    agent_type: str,
    request: GeneratePromptRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Генерация системного промпта на основе текстового описания задачи.
    Использует встроенный AI-ассистент для автоматической формализации требований.
    """
    agent = AdvancedContentAgent(db)
    original_type = agent.AGENT_TYPE
    agent.AGENT_TYPE = agent_type
    
    try:
        result = await agent.generate_system_prompt_from_description(
            user_description=request.user_description,
            target_tone=request.target_tone,
            target_audience=request.target_audience,
            constraints=request.constraints,
            created_by=str(current_user.id) if current_user else None
        )
        
        # Получаем созданный запрос
        result_query = await db.execute(
            select(AgentPromptGenerationRequest).where(
                AgentPromptGenerationRequest.id == result["request_id"]
            )
        )
        gen_request = result_query.scalar_one()
        
        return GenerationRequestResponse(
            id=str(gen_request.id),
            agent_type=gen_request.agent_type,
            user_description=gen_request.user_description,
            generated_prompt=gen_request.generated_prompt,
            status=gen_request.status,
            error_message=gen_request.error_message,
            created_at=gen_request.created_at.isoformat() if gen_request.created_at else None,
            completed_at=gen_request.completed_at.isoformat() if gen_request.completed_at else None
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка генерации промпта: {str(e)}")
    finally:
        agent.AGENT_TYPE = original_type


@router.get("/{agent_type}/generation-requests", response_model=List[GenerationRequestResponse])
async def list_generation_requests(
    agent_type: str,
    status: Optional[str] = Query(None, description="Фильтр по статусу"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Получение списка запросов на генерацию промптов"""
    query = select(AgentPromptGenerationRequest).where(
        AgentPromptGenerationRequest.agent_type == agent_type
    ).order_by(desc(AgentPromptGenerationRequest.created_at)).limit(limit)
    
    if status:
        query = query.where(AgentPromptGenerationRequest.status == status)
    
    result = await db.execute(query)
    requests = result.scalars().all()
    
    return [
        GenerationRequestResponse(
            id=str(r.id),
            agent_type=r.agent_type,
            user_description=r.user_description,
            generated_prompt=r.generated_prompt,
            status=r.status,
            error_message=r.error_message,
            created_at=r.created_at.isoformat() if r.created_at else None,
            completed_at=r.completed_at.isoformat() if r.completed_at else None
        )
        for r in requests
    ]


@router.post("/{agent_type}/generation-requests/{request_id}/create-prompt", response_model=PromptVersionResponse)
async def create_prompt_from_generation_request(
    agent_type: str,
    request_id: UUID,
    name: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Создание версии промпта из успешного запроса на генерацию"""
    # Получаем запрос на генерацию
    result = await db.execute(
        select(AgentPromptGenerationRequest).where(
            and_(
                AgentPromptGenerationRequest.id == request_id,
                AgentPromptGenerationRequest.status == "completed"
            )
        )
    )
    gen_request = result.scalar_one_or_none()
    
    if not gen_request:
        raise HTTPException(status_code=404, detail="Запрос на генерацию не найден или не завершен")
    
    if not gen_request.generated_prompt:
        raise HTTPException(status_code=400, detail="Запрос не содержит сгенерированного промпта")
    
    # Создаем версию промпта
    agent = AdvancedContentAgent(db)
    original_type = agent.AGENT_TYPE
    agent.AGENT_TYPE = agent_type
    
    try:
        prompt = await agent.create_prompt_version(
            name=name,
            system_prompt=gen_request.generated_prompt,
            description=f"Сгенерировано автоматически из описания: {gen_request.user_description[:100]}...",
            metadata=gen_request.generation_metadata or {},
            created_by=str(current_user.id) if current_user else None
        )
        
        # Обновляем запрос
        gen_request.created_prompt_id = prompt.id
        await db.commit()
        
        return PromptVersionResponse(
            id=str(prompt.id),
            agent_type=prompt.agent_type,
            version=prompt.version,
            version_name=prompt.version_name,
            name=prompt.name,
            description=prompt.description,
            system_prompt=prompt.system_prompt,
            metadata=prompt.meta_data or {},
            is_active=prompt.is_active,
            is_default=prompt.is_default,
            marketer_review_status=prompt.marketer_review_status,
            marketer_feedback=prompt.marketer_feedback,
            created_by=str(prompt.created_by) if prompt.created_by else None,
            approved_by=None,
            created_at=prompt.created_at.isoformat() if prompt.created_at else None
        )
    finally:
        agent.AGENT_TYPE = original_type


# ============================================================================
# Endpoints для получения активного промпта
# ============================================================================

@router.get("/{agent_type}/active", response_model=Optional[PromptVersionResponse])
async def get_active_prompt(
    agent_type: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Получение активной версии системного промпта для агента"""
    agent = AdvancedContentAgent(db)
    original_type = agent.AGENT_TYPE
    agent.AGENT_TYPE = agent_type
    
    try:
        if agent_type == TRAINING_MATERIAL_REFORMATTER_AGENT_TYPE:
            prompt = await ensure_training_material_reformatter_default_prompt(db, current_user)
            return prompt_version_response(prompt)

        prompt = await agent.get_active_system_prompt()
        
        if not prompt:
            return None
        
        return prompt_version_response(prompt)
    finally:
        agent.AGENT_TYPE = original_type
