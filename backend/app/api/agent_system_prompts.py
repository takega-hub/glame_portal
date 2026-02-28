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

from app.database.connection import get_db
from app.api.auth import get_current_user, get_current_user_optional
from app.models.user import User
from app.models.agent_system_prompt import (
    AgentSystemPrompt,
    AgentPromptVersionHistory,
    AgentPromptGenerationRequest
)
from app.agents.advanced_content_agent import AdvancedContentAgent

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


# ============================================================================
# Endpoints для управления версиями
# ============================================================================

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
    
    query = select(AgentSystemPrompt).where(
        AgentSystemPrompt.agent_type == agent_type
    ).order_by(desc(AgentSystemPrompt.version))
    
    if not include_inactive:
        query = query.where(AgentSystemPrompt.is_active == True)
    
    result = await db.execute(query)
    prompts = result.scalars().all()
    
    return [
        PromptVersionResponse(
            id=str(p.id),
            agent_type=p.agent_type,
            version=p.version,
            version_name=p.version_name,
            name=p.name,
            description=p.description,
            system_prompt=p.system_prompt,
            metadata=p.meta_data or {},
            is_active=p.is_active,
            is_default=p.is_default,
            marketer_review_status=p.marketer_review_status,
            marketer_feedback=p.marketer_feedback,
            created_by=str(p.created_by) if p.created_by else None,
            approved_by=str(p.approved_by) if p.approved_by else None,
            created_at=p.created_at.isoformat() if p.created_at else None
        )
        for p in prompts
    ]


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
        prompt = await agent.get_active_system_prompt()
        
        if not prompt:
            return None
        
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
    finally:
        agent.AGENT_TYPE = original_type
