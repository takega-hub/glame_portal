from __future__ import annotations

from datetime import date
import os
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_admin
from app.database.connection import get_db
from app.models.customer_message import CustomerMessage
from app.models.crm_task import CrmTask
from app.models.marketing_campaign import MarketingCampaign
from app.models.store import Store
from app.models.user import User
from app.schemas.crm_tasks import (
    CrmAttributionRequest,
    CrmAttributionResponse,
    CrmBirthdayGenerationRequest,
    CrmBirthdayGenerationResponse,
    CrmCampaignAnalyticsResponse,
    CrmDashboardResponse,
    CrmNewArrivalGenerationRequest,
    CrmNewArrivalGenerationResponse,
    CrmTaskAssignRequest,
    CrmTaskDto,
    CrmTaskImportRequest,
    CrmTaskImportResponse,
    CrmTaskListResponse,
    CrmTaskResultRequest,
    CrmTouchpointGenerationRequest,
    CrmTouchpointGenerationResponse,
)
from app.services.birthday_crm_service import BirthdayCrmService
from app.services.crm_new_arrival_service import CrmNewArrivalService
from app.services.crm_task_service import CrmTaskService
from app.services.crm_touchpoint_service import CrmTouchpointService
from app.services.onec_purchase_receipt_arrival_service import OneCPurchaseReceiptArrivalService

router = APIRouter()
require_crm_manager = require_admin()
CRM_ASSIGNEE_ROLES = ("seller", "manager")


def _crm_store_label(name: str) -> str:
    value = (name or "").strip()
    lowered = value.lower()
    if "ялта" in lowered:
        return "Ялта"
    if "мрия" in lowered or "меганом" in lowered or "meganom" in lowered:
        return "МРИЯ"
    if "центрум" in lowered or "centrum" in lowered:
        return "Центрум"
    return value


@router.get("", response_model=CrmTaskListResponse)
async def list_admin_crm_tasks(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    store_name: Optional[str] = Query(None),
    seller_user_id: Optional[UUID] = Query(None),
    seller_external_id: Optional[str] = Query(None),
    seller_name: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    crm_group: Optional[str] = Query(None),
    campaign_id: Optional[str] = Query(None),
    customer_query: Optional[str] = Query(None),
    customer_segment: Optional[str] = Query(None),
    min_total_spent: Optional[float] = Query(None, ge=0),
    max_total_spent: Optional[float] = Query(None, ge=0),
    only_overdue: bool = Query(False),
    only_without_comment: bool = Query(False),
    only_with_attribution: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_crm_manager),
    db: AsyncSession = Depends(get_db),
):
    service = CrmTaskService(db)
    items, total = await service.list_admin_tasks(
        start_date=start_date,
        end_date=end_date,
        store_name=store_name,
        seller_user_id=seller_user_id,
        seller_external_id=seller_external_id,
        seller_name=seller_name,
        status_value=status,
        crm_group=crm_group,
        campaign_id=campaign_id,
        customer_query=customer_query,
        customer_segment=customer_segment,
        min_total_spent=min_total_spent,
        max_total_spent=max_total_spent,
        only_overdue=only_overdue,
        only_without_comment=only_without_comment,
        only_with_attribution=only_with_attribution,
        limit=limit,
        offset=offset,
    )
    return CrmTaskListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/dashboard", response_model=CrmDashboardResponse)
async def admin_crm_dashboard(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    store_name: Optional[str] = Query(None),
    seller_user_id: Optional[UUID] = Query(None),
    seller_external_id: Optional[str] = Query(None),
    seller_name: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    crm_group: Optional[str] = Query(None),
    campaign_id: Optional[str] = Query(None),
    customer_query: Optional[str] = Query(None),
    customer_segment: Optional[str] = Query(None),
    min_total_spent: Optional[float] = Query(None, ge=0),
    max_total_spent: Optional[float] = Query(None, ge=0),
    only_overdue: bool = Query(False),
    only_without_comment: bool = Query(False),
    only_with_attribution: bool = Query(False),
    current_user: User = Depends(require_crm_manager),
    db: AsyncSession = Depends(get_db),
):
    service = CrmTaskService(db)
    return await service.dashboard(
        start_date=start_date,
        end_date=end_date,
        store_name=store_name,
        seller_user_id=seller_user_id,
        seller_external_id=seller_external_id,
        seller_name=seller_name,
        status_value=status,
        crm_group=crm_group,
        campaign_id=campaign_id,
        customer_query=customer_query,
        customer_segment=customer_segment,
        min_total_spent=min_total_spent,
        max_total_spent=max_total_spent,
        only_overdue=only_overdue,
        only_without_comment=only_without_comment,
        only_with_attribution=only_with_attribution,
    )


@router.get("/options")
async def admin_crm_options(
    current_user: User = Depends(require_crm_manager),
    db: AsyncSession = Depends(get_db),
):
    stores_result = await db.execute(
        select(Store.name, Store.external_id, Store.city)
        .where(
            Store.is_active == True,  # noqa: E712
            Store.external_id.isnot(None),
            ~Store.name.ilike("%склад%"),
            ~Store.name.ilike("%основной%"),
        )
        .order_by(Store.name.asc())
    )
    stores = [
        {
            "value": row.name,
            "label": _crm_store_label(row.name),
            "store_name": row.name,
            "external_id": row.external_id,
            "city": row.city,
        }
        for row in stores_result
        if row.name
    ]

    task_counts_subquery = (
        select(
            CrmTask.assigned_seller_user_id.label("seller_user_id"),
            func.count(CrmTask.id).label("tasks_count"),
        )
        .where(CrmTask.assigned_seller_user_id.isnot(None))
        .group_by(CrmTask.assigned_seller_user_id)
        .subquery()
    )
    sellers_result = await db.execute(
        select(
            User.id,
            User.full_name,
            User.email,
            User.phone,
            func.coalesce(task_counts_subquery.c.tasks_count, 0).label("tasks_count"),
        )
        .outerjoin(task_counts_subquery, task_counts_subquery.c.seller_user_id == User.id)
        .where(User.is_customer.is_(False), User.role.in_(CRM_ASSIGNEE_ROLES))
        .order_by(User.full_name.asc().nulls_last(), User.email.asc().nulls_last())
    )
    sellers = [
        {
            "value": str(row.id),
            "label": row.full_name or row.email or row.phone or str(row.id),
            "seller_name": row.full_name or row.email or row.phone or str(row.id),
            "user_id": str(row.id),
            "external_id": None,
            "tasks_count": int(row.tasks_count or 0),
        }
        for row in sellers_result
    ]

    crm_campaigns_result = await db.execute(
        select(
            CrmTask.campaign_id,
            func.max(CrmTask.campaign_name).label("campaign_name"),
            func.count(CrmTask.id).label("tasks_count"),
            func.max(CrmTask.work_date).label("last_work_date"),
        )
        .where(CrmTask.campaign_id.isnot(None), CrmTask.campaign_id != "")
        .group_by(CrmTask.campaign_id)
        .order_by(func.max(CrmTask.work_date).desc().nulls_last(), func.count(CrmTask.id).desc())
    )
    campaigns_by_id: dict[str, dict] = {}

    def add_campaign_option(
        campaign_id: object,
        campaign_name: object = None,
        *,
        tasks_count: int = 0,
        messages_count: int = 0,
        last_work_date: object = None,
        source: str = "crm_tasks",
    ) -> None:
        value = str(campaign_id or "").strip()
        if not value:
            return
        label = str(campaign_name or value).strip() or value
        existing = campaigns_by_id.get(value)
        if existing:
            existing["tasks_count"] = max(int(existing.get("tasks_count") or 0), int(tasks_count or 0))
            existing["messages_count"] = max(int(existing.get("messages_count") or 0), int(messages_count or 0))
            if not existing.get("campaign_name") or existing.get("campaign_name") == value:
                existing["campaign_name"] = label
                existing["label"] = label
            if last_work_date and not existing.get("last_work_date"):
                existing["last_work_date"] = last_work_date.isoformat() if hasattr(last_work_date, "isoformat") else str(last_work_date)
            existing["source"] = ",".join(sorted(set(str(existing.get("source") or "").split(",")) | {source}))
            return
        campaigns_by_id[value] = {
            "value": value,
            "label": label,
            "campaign_id": value,
            "campaign_name": label,
            "tasks_count": int(tasks_count or 0),
            "messages_count": int(messages_count or 0),
            "last_work_date": last_work_date.isoformat() if hasattr(last_work_date, "isoformat") else (str(last_work_date) if last_work_date else None),
            "source": source,
        }

    for row in crm_campaigns_result:
        add_campaign_option(
            row.campaign_id,
            row.campaign_name,
            tasks_count=int(row.tasks_count or 0),
            last_work_date=row.last_work_date,
            source="crm_tasks",
        )

    marketing_campaigns_result = await db.execute(
        select(
            MarketingCampaign.id,
            MarketingCampaign.name,
            MarketingCampaign.start_date,
            MarketingCampaign.metrics,
        )
        .where(MarketingCampaign.type.in_(["sms", "crm"]))
        .order_by(MarketingCampaign.start_date.desc().nulls_last(), MarketingCampaign.name.asc())
    )
    for campaign in marketing_campaigns_result:
        metrics = campaign.metrics or {}
        add_campaign_option(
            campaign.id,
            campaign.name,
            messages_count=int(metrics.get("recipients") or 0) if isinstance(metrics, dict) else 0,
            last_work_date=campaign.start_date,
            source="marketing_campaigns",
        )

    message_campaign_id_expr = CustomerMessage.payload["campaign_id"].astext
    message_campaign_name_expr = CustomerMessage.payload["campaign_name"].astext
    message_campaigns_result = await db.execute(
        select(
            message_campaign_id_expr.label("campaign_id"),
            func.max(message_campaign_name_expr).label("campaign_name"),
            func.count(CustomerMessage.id).label("messages_count"),
            func.max(CustomerMessage.sent_at).label("last_work_date"),
        )
        .where(message_campaign_id_expr.isnot(None))
        .group_by(message_campaign_id_expr)
        .order_by(func.max(CustomerMessage.sent_at).desc().nulls_last())
    )
    for row in message_campaigns_result:
        add_campaign_option(
            row.campaign_id,
            row.campaign_name,
            messages_count=int(row.messages_count or 0),
            last_work_date=row.last_work_date,
            source="customer_messages",
        )

    campaigns = sorted(
        campaigns_by_id.values(),
        key=lambda item: (item.get("last_work_date") or "", int(item.get("tasks_count") or 0), int(item.get("messages_count") or 0)),
        reverse=True,
    )

    segments_result = await db.execute(
        select(User.customer_segment, func.count(User.id).label("customers_count"))
        .where(
            User.is_customer.is_(True),
            User.customer_segment.isnot(None),
            func.length(func.trim(User.customer_segment)) > 0,
        )
        .group_by(User.customer_segment)
        .order_by(func.count(User.id).desc(), User.customer_segment.asc())
    )
    customer_segments = [
        {
            "value": row.customer_segment,
            "label": row.customer_segment,
            "customers_count": int(row.customers_count or 0),
        }
        for row in segments_result
        if row.customer_segment
    ]

    return {"stores": stores, "sellers": sellers, "campaigns": campaigns, "customer_segments": customer_segments}


@router.get("/analytics", response_model=CrmCampaignAnalyticsResponse)
async def admin_crm_campaign_analytics(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    store_name: Optional[str] = Query(None),
    seller_user_id: Optional[UUID] = Query(None),
    seller_external_id: Optional[str] = Query(None),
    seller_name: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    crm_group: Optional[str] = Query(None),
    campaign_id: Optional[str] = Query(None),
    customer_query: Optional[str] = Query(None),
    customer_segment: Optional[str] = Query(None),
    min_total_spent: Optional[float] = Query(None, ge=0),
    max_total_spent: Optional[float] = Query(None, ge=0),
    only_overdue: bool = Query(False),
    only_without_comment: bool = Query(False),
    only_with_attribution: bool = Query(False),
    window_days: int = Query(14, ge=1, le=90),
    current_user: User = Depends(require_crm_manager),
    db: AsyncSession = Depends(get_db),
):
    service = CrmTaskService(db)
    return await service.campaign_analytics(
        start_date=start_date,
        end_date=end_date,
        store_name=store_name,
        seller_user_id=seller_user_id,
        seller_external_id=seller_external_id,
        seller_name=seller_name,
        status_value=status,
        crm_group=crm_group,
        campaign_id=campaign_id,
        customer_query=customer_query,
        customer_segment=customer_segment,
        min_total_spent=min_total_spent,
        max_total_spent=max_total_spent,
        only_overdue=only_overdue,
        only_without_comment=only_without_comment,
        only_with_attribution=only_with_attribution,
        window_days=window_days,
    )


@router.delete("/campaigns/{campaign_id}")
async def delete_admin_crm_campaign_tasks(
    campaign_id: str,
    current_user: User = Depends(require_crm_manager),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(delete(CrmTask).where(CrmTask.campaign_id == campaign_id).returning(CrmTask.id))
    deleted_ids = [str(row[0]) for row in result.all()]
    await db.commit()
    return {"deleted": len(deleted_ids), "campaign_id": campaign_id, "task_ids": deleted_ids}


@router.post("/touchpoints/generate", response_model=CrmTouchpointGenerationResponse)
async def generate_post_purchase_touchpoints(
    payload: CrmTouchpointGenerationRequest,
    current_user: User = Depends(require_crm_manager),
    db: AsyncSession = Depends(get_db),
):
    service = CrmTouchpointService(db)
    return await service.generate_for_work_date(
        payload.work_date or date.today(),
        actor=current_user,
        warranty_days=payload.warranty_days,
        limit_documents_per_rule=payload.limit_documents_per_rule,
    )


@router.post("/birthday/generate", response_model=CrmBirthdayGenerationResponse)
async def generate_birthday_crm_tasks(
    payload: CrmBirthdayGenerationRequest,
    current_user: User = Depends(require_crm_manager),
    db: AsyncSession = Depends(get_db),
):
    return await BirthdayCrmService(db).generate_tasks(
        payload.work_date or date.today(),
        days_ahead=payload.days_ahead,
        limit=payload.limit,
        actor=current_user,
    )


@router.post("/birthday/preview-vip", response_model=CrmTaskDto)
async def preview_birthday_vip_crm_task(
    payload: CrmBirthdayGenerationRequest,
    current_user: User = Depends(require_crm_manager),
    db: AsyncSession = Depends(get_db),
):
    return await BirthdayCrmService(db).create_vip_preview_task(
        payload.work_date or date.today(),
        actor=current_user,
    )


@router.post("/new-arrivals/generate", response_model=CrmNewArrivalGenerationResponse)
async def generate_new_arrival_crm_tasks(
    payload: CrmNewArrivalGenerationRequest,
    current_user: User = Depends(require_crm_manager),
    db: AsyncSession = Depends(get_db),
):
    # Customer-facing CRM generation is intentionally gated. The new receipt
    # flow must first be inspected in dry-run and receive technical approval.
    if payload.send_push:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Массовая push-отправка по новинкам запрещена без отдельного approval; endpoint готовит только draft/preview")
    effective_dry_run = payload.dry_run or not payload.create_seller_tasks
    if not effective_dry_run and not payload.anatoliy_technical_approved:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Live-генерация требует технического одобрения Анатолия; сначала выполните dry-run")
    receipt_max_documents = int(os.getenv("CRM_NEW_ARRIVAL_RECEIPT_MAX_DOCUMENTS", "500"))
    transfer_max_documents = int(os.getenv("CRM_NEW_ARRIVAL_TRANSFER_MAX_DOCUMENTS", "500"))
    async with OneCPurchaseReceiptArrivalService(db) as receipt_service:
        receipt_sync = await receipt_service.sync_recent_receipts(
            lookback_hours=payload.lookback_hours,
            max_documents=receipt_max_documents,
            dry_run=effective_dry_run,
        )
        # Transfers are scanned for availability diagnostics only. They must not
        # create new-arrival events, batches, seller tasks or push waves.
        transfer_sync = await receipt_service.sync_recent_transfers(
            lookback_hours=payload.lookback_hours,
            max_documents=transfer_max_documents,
            dry_run=True,
        )
    result = await CrmNewArrivalService(db).generate_tasks(
        payload.work_date or date.today(),
        lookback_hours=payload.lookback_hours,
        limit_arrivals=payload.limit_arrivals,
        limit_clients_per_arrival=payload.limit_clients_per_arrival,
        use_polling_fallback=payload.use_polling_fallback,
        dry_run=effective_dry_run,
        batch_id=payload.batch_id,
        actor=current_user,
    )
    result["receipt_sync"] = receipt_sync
    result["transfer_sync"] = transfer_sync
    result["push_drafts"] = [] if not payload.prepare_push else [{
        "status": "push_pending_approval",
        "auto_send": False,
        "source": "primary_receipt_batch",
        "note": "Push-аудитория и финальный текст требуют отдельного approval Елены; массовая отправка не запускалась.",
    }]
    result["push_auto_send"] = False
    return result


@router.get("/{task_id}", response_model=CrmTaskDto)
async def get_admin_crm_task(
    task_id: UUID,
    current_user: User = Depends(require_crm_manager),
    db: AsyncSession = Depends(get_db),
):
    service = CrmTaskService(db)
    task = await service.get_task(task_id, admin=True)
    return await service.serialize_task(task)


@router.delete("/{task_id}")
async def delete_admin_crm_task(
    task_id: UUID,
    current_user: User = Depends(require_crm_manager),
    db: AsyncSession = Depends(get_db),
):
    service = CrmTaskService(db)
    return await service.delete_task(task_id, current_user, admin=True)


@router.post("/import", response_model=CrmTaskImportResponse)
async def import_admin_crm_tasks(
    payload: CrmTaskImportRequest,
    current_user: User = Depends(require_crm_manager),
    db: AsyncSession = Depends(get_db),
):
    service = CrmTaskService(db)
    return await service.import_tasks(payload, current_user)


@router.patch("/{task_id}/assign", response_model=CrmTaskDto)
async def assign_admin_crm_task(
    task_id: UUID,
    payload: CrmTaskAssignRequest,
    current_user: User = Depends(require_crm_manager),
    db: AsyncSession = Depends(get_db),
):
    service = CrmTaskService(db)
    return await service.assign_task(task_id, current_user, payload.dict(exclude_unset=True))


@router.patch("/{task_id}/start", response_model=CrmTaskDto)
async def start_admin_crm_task(
    task_id: UUID,
    current_user: User = Depends(require_crm_manager),
    db: AsyncSession = Depends(get_db),
):
    service = CrmTaskService(db)
    return await service.start_task(task_id, current_user, admin=True)


@router.patch("/{task_id}/result", response_model=CrmTaskDto)
async def update_admin_crm_task_result(
    task_id: UUID,
    payload: CrmTaskResultRequest,
    current_user: User = Depends(require_crm_manager),
    db: AsyncSession = Depends(get_db),
):
    service = CrmTaskService(db)
    return await service.update_result(
        task_id,
        current_user,
        payload.seller_outcome,
        payload.seller_comment,
        payload.next_action_date,
        admin=True,
    )


@router.patch("/{task_id}/complete", response_model=CrmTaskDto)
async def complete_admin_crm_task(
    task_id: UUID,
    current_user: User = Depends(require_crm_manager),
    db: AsyncSession = Depends(get_db),
):
    service = CrmTaskService(db)
    return await service.complete_task(task_id, current_user, admin=True)


@router.post("/attribute-purchases", response_model=CrmAttributionResponse)
async def attribute_admin_crm_purchases(
    payload: CrmAttributionRequest,
    current_user: User = Depends(require_crm_manager),
    db: AsyncSession = Depends(get_db),
):
    service = CrmTaskService(db)
    return await service.attribute_purchases(
        task_ids=payload.task_ids,
        start_date=payload.start_date,
        end_date=payload.end_date,
        window_days=payload.window_days,
    )
