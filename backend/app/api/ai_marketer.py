"""
API AI маркетолога
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4

from app.database.connection import get_db
from app.models.customer_segment import CustomerSegment
from app.models.user import User
from app.models.user_segment import UserSegment
from app.models.customer_message import CustomerMessage
from app.models.agent_interaction import AgentInteractionTask, AgentInteractionLog, InteractionStatus
from app.services.ai_segmentation_service import AISegmentationService
from app.services.customer_analytics_service import CustomerAnalyticsService
from app.services.communication_service import CommunicationService
from app.services.agent_interaction_service import AgentInteractionService
from app.agents.contracts import board_aliases
from app.agents.agent_registry import get_marketing_agent_runtime_registry
from app.services.hermes_agent_runtime import HermesAgentRuntime, hermes_runtime_config_from_env
from app.services.hermes_task_execution_service import agent_runtime_status_from_env

logger = logging.getLogger(__name__)

router = APIRouter()


class CampaignGenerateRequest(BaseModel):
    segment_id: Optional[str] = None
    campaign_type: str  # discount, new_product, re-engagement, birthday
    campaign_goal: Optional[str] = None


class BoardTaskEnsureRequest(BaseModel):
    source_agent: str = Field(default="ai-marketer-board", min_length=1, max_length=64)
    target_agent: str = Field(..., min_length=1, max_length=64)
    task_type: str = Field(..., min_length=1, max_length=100)
    input_data: Dict[str, Any] = Field(default_factory=dict)
    task_context: Dict[str, Any] = Field(default_factory=dict)
    target_metrics: Optional[Dict[str, Any]] = None
    requirements: Optional[Dict[str, Any]] = None
    constraints: Optional[Dict[str, Any]] = None
    priority: int = Field(default=3, ge=1, le=5)
    deadline_at: Optional[str] = None
    idempotency_key: Optional[str] = None


def _task_to_dict(task: AgentInteractionTask) -> Dict[str, Any]:
    return task.to_dict() if hasattr(task, "to_dict") else {
        "id": str(task.id),
        "source_agent": task.source_agent,
        "target_agent": task.target_agent,
        "task_type": task.task_type,
        "task_context": task.task_context or {},
        "input_data": task.input_data or {},
        "target_metrics": task.target_metrics or {},
        "requirements": task.requirements or {},
        "constraints": task.constraints or {},
        "status": task.status,
        "priority": task.priority,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "deadline_at": task.deadline_at.isoformat() if task.deadline_at else None,
    }


def _board_aliases(board_id: str) -> List[str]:
    return board_aliases(board_id)


def _task_matches_board(task: AgentInteractionTask, board_id: str) -> bool:
    ctx = task.task_context or {}
    inp = task.input_data or {}
    if ctx.get("board") == board_id or inp.get("source_board") == board_id:
        return True
    haystack = f"{task.source_agent} {task.target_agent} {task.task_type}".lower()
    return any(alias in haystack for alias in _board_aliases(board_id))


def _normalize_key(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _task_idempotency_key(board_id: str, request: BoardTaskEnsureRequest) -> str:
    title = request.input_data.get("title") or request.task_context.get("title") or request.task_type
    return request.idempotency_key or request.task_context.get("idempotency_key") or request.input_data.get("idempotency_key") or _normalize_key(
        f"{board_id}:{request.target_agent}:{request.task_type}:{title}"
    )


def _parse_optional_datetime(value: Optional[str]):
    if not value:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid deadline_at format: {value}")


@router.get("/agents/runtime")
async def get_runtime_agents():
    """Canonical AI agents with current runtime execution metadata."""

    return {"agents": get_marketing_agent_runtime_registry()}


@router.get("/agents/runtime/status")
async def get_agent_runtime_status():
    """Effective GLAME agent runtime feature-flag status, without secrets."""

    return agent_runtime_status_from_env()


@router.get("/agents/hermes/readiness")
async def get_hermes_runtime_readiness(
    run_dry: bool = Query(False, description="Run one no-GLAME-write Hermes prompt."),
    agent_id: str = Query("director-agent", min_length=1, max_length=64),
):
    """Read-only Hermes runtime smoke check: binary, profiles and optional dry-run."""

    runtime = HermesAgentRuntime(hermes_runtime_config_from_env())
    readiness = await runtime.check_readiness()
    readiness["runtime_status"] = agent_runtime_status_from_env()
    if run_dry:
        readiness["dry_run"] = await runtime.run_smoke_check(agent_id)
    return readiness


@router.post("/agents/hermes/{agent_id}/smoke-check")
async def run_hermes_runtime_smoke_check(agent_id: str):
    """Run one no-GLAME-write Hermes prompt for a selected profile."""

    runtime = HermesAgentRuntime(hermes_runtime_config_from_env())
    return await runtime.run_smoke_check(agent_id)


@router.get("/boards/{board_id}")
async def get_board_state(
    board_id: str,
    limit: int = 200,
    db: AsyncSession = Depends(get_db)
):
    """Единая backend-агрегация задач и базовых статусов для AI Marketer boards."""
    result = await db.execute(
        select(AgentInteractionTask)
        .where(AgentInteractionTask.status != InteractionStatus.DELETED.value)
        .order_by(desc(AgentInteractionTask.created_at))
        .limit(min(max(limit, 1), 500))
    )
    all_tasks = result.scalars().all()
    tasks = [task for task in all_tasks if _task_matches_board(task, board_id)]
    active_statuses = {
        InteractionStatus.PENDING.value,
        InteractionStatus.VALIDATING.value,
        InteractionStatus.VALIDATED.value,
        InteractionStatus.PENDING_APPROVAL.value,
        InteractionStatus.APPROVED.value,
        InteractionStatus.QUEUED.value,
        InteractionStatus.PROCESSING.value,
    }
    approval_statuses = {
        InteractionStatus.VALIDATED.value,
        InteractionStatus.PENDING_APPROVAL.value,
    }
    return {
        "board_id": board_id,
        "tasks": [_task_to_dict(task) for task in tasks],
        "stats": {
            "total": len(tasks),
            "active": sum(1 for task in tasks if task.status in active_statuses),
            "approvals": sum(1 for task in tasks if task.status in approval_statuses),
            "completed": sum(1 for task in tasks if task.status == InteractionStatus.COMPLETED.value),
            "failed": sum(1 for task in tasks if task.status == InteractionStatus.FAILED.value),
        },
    }


@router.post("/boards/{board_id}/tasks/ensure")
async def ensure_board_task(
    board_id: str,
    request: BoardTaskEnsureRequest,
    db: AsyncSession = Depends(get_db)
):
    """Создать задачу доски идемпотентно: если такая уже есть, вернуть существующую."""
    key = _task_idempotency_key(board_id, request)
    result = await db.execute(
        select(AgentInteractionTask)
        .where(
            AgentInteractionTask.status != InteractionStatus.DELETED.value,
            AgentInteractionTask.target_agent == request.target_agent,
            AgentInteractionTask.task_type == request.task_type,
        )
        .order_by(desc(AgentInteractionTask.created_at))
        .limit(200)
    )
    candidates = result.scalars().all()
    for task in candidates:
        ctx = task.task_context or {}
        inp = task.input_data or {}
        if ctx.get("idempotency_key") == key or inp.get("idempotency_key") == key:
            return {"created": False, "task": _task_to_dict(task)}
        if _task_matches_board(task, board_id):
            existing_title = _normalize_key(inp.get("title") or ctx.get("title") or task.task_type)
            requested_title = _normalize_key(request.input_data.get("title") or request.task_context.get("title") or request.task_type)
            if existing_title == requested_title:
                return {"created": False, "task": _task_to_dict(task)}

    context = dict(request.task_context or {})
    input_data = dict(request.input_data or {})
    context.update({"board": board_id, "idempotency_key": key})
    input_data.update({"source_board": board_id, "idempotency_key": key})

    task = AgentInteractionTask(
        source_agent=request.source_agent,
        target_agent=request.target_agent,
        task_type=request.task_type,
        task_context=context,
        input_data=input_data,
        target_metrics=request.target_metrics or {},
        requirements=request.requirements or {},
        constraints=request.constraints or {},
        priority=request.priority,
        status=InteractionStatus.PENDING.value,
        deadline_at=_parse_optional_datetime(request.deadline_at),
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    service = AgentInteractionService(db)
    await service.validate_incoming_task(task)

    db.add(AgentInteractionLog(
        task_id=task.id,
        agent_name=request.source_agent,
        event_type="board_task_ensured",
        event_data={"board_id": board_id, "idempotency_key": key, "created": True},
        message=f"Task ensured from {board_id} board",
    ))
    await db.commit()
    await db.refresh(task)

    return {"created": True, "task": _task_to_dict(task)}


@router.get("/dashboard")
async def get_dashboard(
    db: AsyncSession = Depends(get_db)
):
    """Дашборд с основными метриками"""
    try:
        analytics_service = CustomerAnalyticsService(db)
        
        # Статистика по сегментам (с обработкой ошибок)
        try:
            segments_stats = await analytics_service.get_customer_segments_stats()
        except Exception as e:
            logger.error(f"Ошибка получения статистики сегментов: {e}", exc_info=True)
            segments_stats = {}
        
        # Риски оттока (с обработкой ошибок)
        try:
            churn_risk = await analytics_service.get_churn_risk()
        except Exception as e:
            logger.error(f"Ошибка получения рисков оттока: {e}", exc_info=True)
            churn_risk = {}
        
        # Топ покупатели (с обработкой ошибок)
        try:
            top_customers = await analytics_service.get_top_customers(limit=10)
        except Exception as e:
            logger.error(f"Ошибка получения топ покупателей: {e}", exc_info=True)
            top_customers = []
        
        return {
            "segments_overview": segments_stats,
            "churn_risk": churn_risk,
            "top_customers": top_customers
        }
    except Exception as e:
        logger.error(f"Ошибка получения дашборда: {e}", exc_info=True)
        # Возвращаем базовую структуру даже при ошибке
        return {
            "segments_overview": {},
            "churn_risk": {},
            "top_customers": []
        }


@router.get("/segments/analysis")
async def get_segments_analysis(
    db: AsyncSession = Depends(get_db)
):
    """Быстрая сводка сегментов для досок AI-маркетолога."""
    stmt = select(CustomerSegment).where(CustomerSegment.is_active == True)
    result = await db.execute(stmt)
    segments = result.scalars().all()

    segment_ids = [segment.id for segment in segments]
    member_stats: Dict[UUID, Dict[str, float]] = {}
    if segment_ids:
        stats_stmt = (
            select(
                UserSegment.segment_id,
                func.count(User.id),
                func.coalesce(func.avg(User.total_spent), 0),
                func.coalesce(func.avg(User.total_purchases), 0),
            )
            .join(User, User.id == UserSegment.user_id)
            .where(UserSegment.segment_id.in_(segment_ids), User.is_customer == True)
            .group_by(UserSegment.segment_id)
        )
        stats_res = await db.execute(stats_stmt)
        for segment_id, size, avg_spent, avg_purchases in stats_res.all():
            member_stats[segment_id] = {
                "size": int(size or 0),
                "average_ltv": float(avg_spent or 0) / 100,
                "average_purchases": float(avg_purchases or 0),
            }

    analysis = []
    for segment in segments:
        stats = member_stats.get(segment.id) or {}
        size = int(stats.get("size") or segment.customer_count or 0)
        analysis.append({
            "segment_id": str(segment.id),
            "name": segment.name,
            "description": segment.description,
            "size": size,
            "average_ltv": stats.get("average_ltv", 0),
            "average_purchases": stats.get("average_purchases", 0),
            "insights": [
                f"Размер сегмента: {size}",
                "Откройте карточку сегмента для редактирования фильтров и выгрузки списка.",
            ],
        })
    
    return {"segments": analysis}


@router.post("/segments/auto-generate")
async def auto_generate_segments(
    db: AsyncSession = Depends(get_db)
):
    """Автоматическая сегментация AI"""
    ai_service = AISegmentationService(db)
    stats = await ai_service.auto_segment_customers()
    
    return {
        "success": True,
        "stats": stats
    }


@router.get("/customers/{user_id}/insights")
async def get_customer_insights(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """AI инсайты по покупателю"""
    try:
        uid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат user_id")
    
    stmt = select(User).where(User.id == uid)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="Покупатель не найден")
    
    analytics_service = CustomerAnalyticsService(db)
    ai_service = AISegmentationService(db)
    
    # Предсказание следующей покупки
    next_purchase = await ai_service.predict_next_purchase(uid)
    
    # Риск оттока
    churn_risk = await analytics_service.get_churn_risk(uid)
    
    return {
        "user_id": user_id,
        "persona": user.persona,
        "customer_segment": user.customer_segment,
        "rfm_score": user.rfm_score,
        "purchase_preferences": user.purchase_preferences,
        "next_purchase_prediction": next_purchase,
        "churn_risk": churn_risk
    }


@router.post("/campaigns/generate")
async def generate_campaign(
    request: CampaignGenerateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Генерация персонализированной кампании"""
    # TODO: Реализовать генерацию кампаний через LLM
    # Пока возвращаем заглушку
    
    return {
        "success": True,
        "message": "Генерация кампаний будет реализована в следующей версии",
        "campaign_type": request.campaign_type
    }


@router.get("/opportunities")
async def get_opportunities(
    db: AsyncSession = Depends(get_db)
):
    """AI поиск возможностей"""
    try:
        analytics_service = CustomerAnalyticsService(db)
        
        # Находим покупателей с высоким риском оттока
        churn_risk = await analytics_service.get_churn_risk()
        
        opportunities = []
        
        # Проверяем, что churn_risk не пустой и содержит нужные ключи
        if churn_risk and isinstance(churn_risk, dict):
            high_risk = churn_risk.get("high_risk", 0)
            if high_risk and high_risk > 0:
                opportunities.append({
                    "type": "re-engagement",
                    "description": f"{high_risk} VIP клиентов не покупали 90+ дней - возможна программа реактивации",
                    "customer_count": high_risk,
                    "potential_revenue": high_risk * 5000,  # Примерная оценка
                    "recommended_actions": ["Специальные скидки", "Персональные предложения"]
                })
        
        return {
            "opportunities": opportunities,
            "total": len(opportunities)
        }
    except Exception as e:
        logger.error(f"Ошибка получения возможностей: {e}", exc_info=True)
        # Возвращаем пустой список вместо ошибки 500
        return {
            "opportunities": [],
            "total": 0
        }


class MassPrepareRequest(BaseModel):
    plan_text: str
    plan_title: Optional[str] = None
    event_type: Optional[str] = None
    brand: Optional[str] = None
    message_count: Optional[int] = Field(None, ge=1, le=5000)
    metadata: Optional[Dict[str, Any]] = None


class MassSegmentOut(BaseModel):
    id: str
    name: str
    customer_count: int


class MassPrepareResponse(BaseModel):
    report: str
    segment: MassSegmentOut
    suggested: Dict[str, Any]


class MassRunRequest(BaseModel):
    segment_id: str
    event_type: str
    brand: Optional[str] = None
    message_count: int = Field(100, ge=1, le=5000)
    auto_detect_store: bool = True
    metadata: Optional[Dict[str, Any]] = None


class MassRunResponse(BaseModel):
    report: str
    saved: int
    recipients: int


def _derive_event_type(title: Optional[str], text: str) -> str:
    src = f"{title or ''}\n{text}".lower()
    if "sms" in src or "смс" in src:
        return "sms_broadcast"
    if "рассыл" in src:
        return "broadcast"
    return "mass_mailing"


def _derive_count(text: str, default: int = 100) -> int:
    import re
    m = re.search(r"\b(\d{1,5})\s*(сообщен|sms|смс)\w*\b", (text or "").lower())
    if not m:
        return default
    try:
        v = int(m.group(1))
        if v < 1:
            return default
        return min(v, 5000)
    except Exception:
        return default


def _make_segment_name(seed: str, title: Optional[str]) -> str:
    import re
    base = (title or "").strip() or "mass-mailing"
    base = re.sub(r"\s+", " ", base).strip().replace(" ", "_")
    name = f"auto_{seed[:8]}_{base}"
    return name[:100]


@router.post("/mass-mailing/prepare", response_model=MassPrepareResponse)
async def prepare_mass_mailing(
    body: MassPrepareRequest,
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func
    name = _make_segment_name(str(uuid4()), body.plan_title)
    existing = await db.execute(select(CustomerSegment).where(CustomerSegment.name == name))
    if existing.scalar_one_or_none():
        name = _make_segment_name(str(uuid4()), body.plan_title)
    total_customers_result = await db.execute(select(func.count(User.id)).where(User.is_customer == True))
    customer_count = int(total_customers_result.scalar() or 0)
    seg = CustomerSegment(
        id=uuid4(),
        name=name,
        description="Автосегмент для массовой генерации",
        rules={"logic": "AND", "filters": []},
        customer_count=customer_count,
        is_auto_generated=True,
        is_active=True,
    )
    db.add(seg)
    await db.commit()
    await db.refresh(seg)
    et = body.event_type or _derive_event_type(body.plan_title, body.plan_text)
    limit = int(body.message_count or _derive_count(body.plan_text, 100))
    suggested = {
        "event": {"type": et, "brand": body.brand or "GLAME", "metadata": body.metadata or {}},
        "limit": limit,
        "search_criteria": {"segment_id": str(seg.id)},
    }
    report = "\n".join([
        "План подготовлен",
        f"Сегмент: {seg.name}",
        f"Тип события: {et}",
        f"Количество сообщений: {limit}",
    ])
    return MassPrepareResponse(
        report=report,
        segment=MassSegmentOut(id=str(seg.id), name=seg.name, customer_count=customer_count),
        suggested=suggested,
    )


@router.post("/mass-mailing/run", response_model=MassRunResponse)
async def run_mass_mailing(
    body: MassRunRequest,
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func
    try:
        seg_uuid = UUID(body.segment_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Некорректный segment_id")
    seg_row = await db.execute(select(CustomerSegment).where(CustomerSegment.id == seg_uuid, CustomerSegment.is_active == True))
    seg = seg_row.scalar_one_or_none()
    if not seg:
        raise HTTPException(status_code=404, detail="Сегмент не найден или не активен")
    segment_client_ids: List[UUID] = []
    try:
        from app.api.customer_segmentation import _build_select_for_rules
        stmt, _ = _build_select_for_rules(seg.rules or {"logic": "AND", "filters": []})
        subq = stmt.subquery()
        res = await db.execute(select(User.id).where(User.id.in_(select(subq.c.id)), User.is_customer == True).limit(body.message_count))
        segment_client_ids = [row[0] for row in res.fetchall()]
    except Exception:
        res = await db.execute(select(UserSegment.user_id).join(User, User.id == UserSegment.user_id).where(UserSegment.segment_id == seg_uuid, User.is_customer == True).limit(body.message_count))
        segment_client_ids = [row[0] for row in res.fetchall()]
    lim = min(len(segment_client_ids), body.message_count or 100)
    client_ids = segment_client_ids[:lim]
    if not client_ids:
        return MassRunResponse(report="Клиенты не найдены", saved=0, recipients=0)
    service = CommunicationService(db)
    event = {"type": body.event_type, "brand": body.brand or "GLAME", "store": None, **(body.metadata or {})}
    messages = await service.generate_batch_messages(client_ids=client_ids, event=event)
    rows: List[CustomerMessage] = []
    for m in messages:
        try:
            uid = UUID(str(m.get("client_id")))
        except Exception:
            continue
        rows.append(CustomerMessage(
            id=uuid4(),
            user_id=uid,
            message=m.get("message") or "",
            cta=m.get("cta"),
            segment=str(m.get("segment") or ""),
            event_type=str(body.event_type),
            event_brand=body.brand or m.get("brand"),
            event_store=m.get("store"),
            payload=m,
            status="new",
        ))
    for r in rows:
        db.add(r)
    await db.commit()
    saved = len(rows)
    report = "\n".join([
        "Массовая генерация завершена",
        f"Сегмент: {seg.name}",
        f"Тип события: {body.event_type}",
        f"Получателей: {len(client_ids)}",
        f"Сохранено сообщений: {saved}",
    ])
    return MassRunResponse(report=report, saved=saved, recipients=len(client_ids))
