"""
API endpoints для межагентного взаимодействия.
Включает создание задач, валидацию, приоритизацию и логирование.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, asc, and_
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
import logging

from app.database.connection import get_db
from app.api.auth import get_current_user, get_current_user_optional
from app.models.user import User
from app.models.agent_interaction import (
    AgentInteractionTask,
    AgentInteractionLog,
    AgentValidationRule,
    AgentContentHandoff,
    InteractionStatus,
    TaskPriority
)
from app.agents.advanced_content_agent import AdvancedContentAgent
from app.services.agent_interaction_service import AgentInteractionService

router = APIRouter(prefix="/agent-interactions", tags=["agent-interactions"])
logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Models
# ============================================================================

class CreateAgentTaskRequest(BaseModel):
    source_agent: str = Field(..., min_length=1, max_length=64, description="Агент-инициатор")
    target_agent: str = Field(..., min_length=1, max_length=64, description="Целевой агент")
    task_type: str = Field(..., min_length=1, max_length=100, description="Тип задачи")
    task_context: Dict[str, Any] = Field(default_factory=dict, description="Контекст задачи")
    input_data: Dict[str, Any] = Field(default_factory=dict, description="Входные данные")
    target_metrics: Optional[Dict[str, Any]] = Field(None, description="Целевые метрики")
    requirements: Optional[Dict[str, Any]] = Field(None, description="Требования к результату")
    constraints: Optional[Dict[str, Any]] = Field(None, description="Ограничения")
    priority: int = Field(default=TaskPriority.NORMAL.value, ge=1, le=5, description="Приоритет (1-5, lower is higher)")
    deadline_at: Optional[datetime] = Field(None, description="Дедлайн выполнения")
    timeout_seconds: Optional[int] = Field(300, ge=10, description="Таймаут в секундах")


class AgentTaskResponse(BaseModel):
    id: str
    source_agent: str
    target_agent: str
    task_type: str
    status: str
    priority: int
    validation_result: Optional[Dict[str, Any]]
    validation_errors: List[str]
    created_at: str
    scheduled_at: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]
    deadline_at: Optional[str]
    
    class Config:
        from_attributes = True


class ValidationResultResponse(BaseModel):
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    rules_checked: int
    timestamp: str


class TaskLogResponse(BaseModel):
    id: str
    task_id: str
    agent_name: str
    event_type: str
    message: Optional[str]
    event_data: Dict[str, Any]
    created_at: str


class InteractionChainResponse(BaseModel):
    task: Dict[str, Any]
    logs: List[Dict[str, Any]]
    content_handoffs: List[Dict[str, Any]]
    audit_summary: Dict[str, Any]


class CreateValidationRuleRequest(BaseModel):
    task_type: str = Field(..., description="Тип задачи для валидации")
    rule_name: str = Field(..., description="Название правила")
    rule_description: Optional[str] = Field(None, description="Описание правила")
    validation_schema: Optional[Dict[str, Any]] = Field(None, description="JSON Schema для валидации")
    validation_function: Optional[str] = Field(None, description="Имя кастомной функции валидации")
    source_agent: Optional[str] = Field(None, description="Применять только для конкретного источника")
    target_agent: Optional[str] = Field(None, description="Применять только для конкретного получателя")
    is_required: bool = Field(True, description="Обязательное правило")
    error_message: Optional[str] = Field(None, description="Сообщение об ошибке")
    priority: int = Field(100, ge=0, description="Приоритет применения")


class ValidationRuleResponse(BaseModel):
    id: str
    task_type: str
    rule_name: str
    rule_description: Optional[str]
    source_agent: Optional[str]
    target_agent: Optional[str]
    is_required: bool
    is_active: bool
    priority: int
    created_at: str


# ============================================================================
# Endpoints для управления задачами
# ============================================================================

@router.post("/tasks", response_model=AgentTaskResponse)
async def create_agent_task(
    request: CreateAgentTaskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Создание новой задачи для межагентного взаимодействия.
    Задача автоматически проходит валидацию перед постановкой в очередь.
    """
    service = AgentInteractionService(db)
    
    # Создаем задачу через AdvancedContentAgent (если целевой агент - content-agent)
    if request.target_agent == "content-agent":
        agent = AdvancedContentAgent(db)
        task = await agent.receive_task_from_agent(
            source_agent=request.source_agent,
            task_type=request.task_type,
            task_context=request.task_context,
            input_data=request.input_data,
            target_metrics=request.target_metrics,
            requirements=request.requirements,
            constraints=request.constraints,
            priority=request.priority,
            deadline_at=request.deadline_at
        )
    else:
        # Другие агенты - прямое создание
        task = AgentInteractionTask(
            source_agent=request.source_agent,
            target_agent=request.target_agent,
            task_type=request.task_type,
            task_context=request.task_context,
            input_data=request.input_data,
            target_metrics=request.target_metrics or {},
            requirements=request.requirements or {},
            constraints=request.constraints or {},
            priority=request.priority,
            status=InteractionStatus.PENDING.value,
            deadline_at=request.deadline_at,
            timeout_seconds=request.timeout_seconds
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
    
    # Запускаем валидацию
    await service.validate_incoming_task(task)
    
    return AgentTaskResponse(
        id=str(task.id),
        source_agent=task.source_agent,
        target_agent=task.target_agent,
        task_type=task.task_type,
        status=task.status,
        priority=task.priority,
        validation_result=task.validation_result,
        validation_errors=task.validation_errors or [],
        created_at=task.created_at.isoformat() if task.created_at else None,
        scheduled_at=task.scheduled_at.isoformat() if task.scheduled_at else None,
        started_at=task.started_at.isoformat() if task.started_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
        deadline_at=task.deadline_at.isoformat() if task.deadline_at else None
    )


@router.get("/tasks", response_model=List[AgentTaskResponse])
async def list_agent_tasks(
    target_agent: Optional[str] = Query(None, description="Фильтр по целевому агенту"),
    source_agent: Optional[str] = Query(None, description="Фильтр по исходному агенту"),
    status: Optional[str] = Query(None, description="Фильтр по статусу"),
    task_type: Optional[str] = Query(None, description="Фильтр по типу задачи"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Получение списка задач межагентного взаимодействия"""
    query = select(AgentInteractionTask).order_by(desc(AgentInteractionTask.created_at)).limit(limit)
    
    if target_agent:
        query = query.where(AgentInteractionTask.target_agent == target_agent)
    if source_agent:
        query = query.where(AgentInteractionTask.source_agent == source_agent)
    if status:
        query = query.where(AgentInteractionTask.status == status)
    if task_type:
        query = query.where(AgentInteractionTask.task_type == task_type)
    
    result = await db.execute(query)
    tasks = result.scalars().all()
    
    return [
        AgentTaskResponse(
            id=str(t.id),
            source_agent=t.source_agent,
            target_agent=t.target_agent,
            task_type=t.task_type,
            status=t.status,
            priority=t.priority,
            validation_result=t.validation_result,
            validation_errors=t.validation_errors or [],
            created_at=t.created_at.isoformat() if t.created_at else None,
            scheduled_at=t.scheduled_at.isoformat() if t.scheduled_at else None,
            started_at=t.started_at.isoformat() if t.started_at else None,
            completed_at=t.completed_at.isoformat() if t.completed_at else None,
            deadline_at=t.deadline_at.isoformat() if t.deadline_at else None
        )
        for t in tasks
    ]


@router.get("/tasks/{task_id}", response_model=AgentTaskResponse)
async def get_agent_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Получение деталей задачи по ID"""
    service = AgentInteractionService(db)
    task = await service.get_task_by_id(str(task_id))
    
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    
    return AgentTaskResponse(
        id=str(task.id),
        source_agent=task.source_agent,
        target_agent=task.target_agent,
        task_type=task.task_type,
        status=task.status,
        priority=task.priority,
        validation_result=task.validation_result,
        validation_errors=task.validation_errors or [],
        created_at=task.created_at.isoformat() if task.created_at else None,
        scheduled_at=task.scheduled_at.isoformat() if task.scheduled_at else None,
        started_at=task.started_at.isoformat() if task.started_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
        deadline_at=task.deadline_at.isoformat() if task.deadline_at else None
    )


@router.post("/tasks/{task_id}/validate", response_model=ValidationResultResponse)
async def validate_agent_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Принудительная валидация задачи"""
    service = AgentInteractionService(db)
    
    task = await service.get_task_by_id(str(task_id))
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    
    result = await service.validate_incoming_task(task)
    
    return ValidationResultResponse(
        is_valid=result["is_valid"],
        errors=result["errors"],
        warnings=result["warnings"],
        rules_checked=result["rules_checked"],
        timestamp=result["timestamp"]
    )


@router.post("/tasks/{task_id}/queue")
async def queue_agent_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Постановка валидированной задачи в очередь на выполнение"""
    service = AgentInteractionService(db)
    
    try:
        task = await service.queue_task(str(task_id))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return {
        "message": "Задача поставлена в очередь",
        "task_id": str(task.id),
        "priority": task.priority,
        "status": task.status
    }


@router.post("/tasks/{task_id}/process")
async def process_agent_task(
    task_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Обработка задачи целевым агентом"""
    task_result = await db.execute(
        select(AgentInteractionTask).where(AgentInteractionTask.id == task_id)
    )
    task = task_result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    
    if task.target_agent == "content-agent":
        agent = AdvancedContentAgent(db)
        try:
            result = await agent.process_agent_task(str(task_id))
            return {
                "message": "Задача успешно обработана",
                "task_id": str(task_id),
                "result_summary": {k: v for k, v in result.items() if k != "raw_response"} if isinstance(result, dict) else {}
            }
        except Exception as e:
            logger.error(f"Ошибка обработки задачи {task_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Ошибка обработки: {str(e)}")
    else:
        raise HTTPException(status_code=400, detail=f"Обработка для агента '{task.target_agent}' не реализована")


@router.post("/tasks/{task_id}/cancel")
async def cancel_agent_task(
    task_id: UUID,
    reason: Optional[str] = Body(None, embed=True),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Отмена задачи"""
    service = AgentInteractionService(db)
    
    try:
        task = await service.cancel_task(str(task_id), reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return {
        "message": "Задача отменена",
        "task_id": str(task.id),
        "status": task.status,
        "reason": reason
    }


# ============================================================================
# Endpoints для приоритизации
# ============================================================================

@router.get("/tasks/prioritized/{target_agent}", response_model=List[AgentTaskResponse])
async def get_prioritized_tasks(
    target_agent: str,
    status: Optional[str] = Query(None, description="Фильтр по статусу"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Получение приоритизированного списка задач для агента"""
    service = AgentInteractionService(db)
    
    tasks = await service.get_prioritized_tasks(
        target_agent=target_agent,
        status=status,
        limit=limit
    )
    
    return [
        AgentTaskResponse(
            id=str(t.id),
            source_agent=t.source_agent,
            target_agent=t.target_agent,
            task_type=t.task_type,
            status=t.status,
            priority=t.priority,
            validation_result=t.validation_result,
            validation_errors=t.validation_errors or [],
            created_at=t.created_at.isoformat() if t.created_at else None,
            scheduled_at=t.scheduled_at.isoformat() if t.scheduled_at else None,
            started_at=t.started_at.isoformat() if t.started_at else None,
            completed_at=t.completed_at.isoformat() if t.completed_at else None,
            deadline_at=t.deadline_at.isoformat() if t.deadline_at else None
        )
        for t in tasks
    ]


# ============================================================================
# Endpoints для логирования и аудита
# ============================================================================

@router.get("/tasks/{task_id}/logs", response_model=List[TaskLogResponse])
async def get_task_logs(
    task_id: UUID,
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Получение логов задачи"""
    service = AgentInteractionService(db)
    
    logs = await service.get_task_logs(str(task_id), limit)
    
    return [
        TaskLogResponse(
            id=str(l.id),
            task_id=str(l.task_id),
            agent_name=l.agent_name,
            event_type=l.event_type,
            message=l.message,
            event_data=l.event_data or {},
            created_at=l.created_at.isoformat() if l.created_at else None
        )
        for l in logs
    ]


@router.get("/tasks/{task_id}/audit", response_model=InteractionChainResponse)
async def get_interaction_audit_chain(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Получение полной цепочки взаимодействия для аудита"""
    service = AgentInteractionService(db)
    
    try:
        chain = await service.get_interaction_chain(str(task_id))
        return InteractionChainResponse(**chain)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================================
# Endpoints для управления правилами валидации
# ============================================================================

@router.post("/validation-rules", response_model=ValidationRuleResponse)
async def create_validation_rule(
    request: CreateValidationRuleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Создание правила валидации (требуется аутентификация)"""
    service = AgentInteractionService(db)
    
    rule = await service.create_validation_rule(
        task_type=request.task_type,
        rule_name=request.rule_name,
        rule_description=request.rule_description,
        validation_schema=request.validation_schema,
        validation_function=request.validation_function,
        source_agent=request.source_agent,
        target_agent=request.target_agent,
        is_required=request.is_required,
        error_message=request.error_message,
        priority=request.priority
    )
    
    return ValidationRuleResponse(
        id=str(rule.id),
        task_type=rule.task_type,
        rule_name=rule.rule_name,
        rule_description=rule.rule_description,
        source_agent=rule.source_agent,
        target_agent=rule.target_agent,
        is_required=rule.is_required,
        is_active=rule.is_active,
        priority=rule.priority,
        created_at=rule.created_at.isoformat() if rule.created_at else None
    )


@router.get("/validation-rules", response_model=List[ValidationRuleResponse])
async def list_validation_rules(
    task_type: Optional[str] = Query(None, description="Фильтр по типу задачи"),
    is_active: Optional[bool] = Query(None, description="Фильтр по статусу активности"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Получение списка правил валидации"""
    service = AgentInteractionService(db)
    
    rules = await service.get_validation_rules(task_type, is_active)
    
    return [
        ValidationRuleResponse(
            id=str(r.id),
            task_type=r.task_type,
            rule_name=r.rule_name,
            rule_description=r.rule_description,
            source_agent=r.source_agent,
            target_agent=r.target_agent,
            is_required=r.is_required,
            is_active=r.is_active,
            priority=r.priority,
            created_at=r.created_at.isoformat() if r.created_at else None
        )
        for r in rules
    ]


@router.get("/validation-rules/{rule_id}", response_model=ValidationRuleResponse)
async def get_validation_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Получение деталей правила валидации"""
    result = await db.execute(
        select(AgentValidationRule).where(AgentValidationRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()
    
    if not rule:
        raise HTTPException(status_code=404, detail="Правило не найдено")
    
    return ValidationRuleResponse(
        id=str(rule.id),
        task_type=rule.task_type,
        rule_name=rule.rule_name,
        rule_description=rule.rule_description,
        source_agent=rule.source_agent,
        target_agent=rule.target_agent,
        is_required=rule.is_required,
        is_active=rule.is_active,
        priority=rule.priority,
        created_at=rule.created_at.isoformat() if rule.created_at else None
    )


@router.patch("/validation-rules/{rule_id}/toggle")
async def toggle_validation_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Включение/выключение правила валидации"""
    result = await db.execute(
        select(AgentValidationRule).where(AgentValidationRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()
    
    if not rule:
        raise HTTPException(status_code=404, detail="Правило не найдено")
    
    rule.is_active = not rule.is_active
    await db.commit()
    await db.refresh(rule)
    
    return {
        "message": f"Правило {'активировано' if rule.is_active else 'деактивировано'}",
        "rule_id": str(rule.id),
        "is_active": rule.is_active
    }
