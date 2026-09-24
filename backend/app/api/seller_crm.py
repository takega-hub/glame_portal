from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database.connection import get_db
from app.models.user import User
from app.schemas.crm_tasks import CrmTaskDto, CrmTaskListResponse, CrmTaskPostponeRequest, CrmTaskResultRequest
from app.services.crm_task_service import CrmTaskService

router = APIRouter()


@router.get("/tasks", response_model=CrmTaskListResponse)
async def list_my_crm_tasks(
    date_value: str = Query("today", alias="date"),
    status: Optional[str] = Query(None),
    crm_group: Optional[str] = Query(None),
    include_overdue: bool = Query(True),
    limit: int = Query(100, ge=1, le=300),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = CrmTaskService(db)
    items, total = await service.list_seller_tasks(
        current_user,
        date_value=date_value,
        status_value=status,
        crm_group=crm_group,
        include_overdue=include_overdue,
        limit=limit,
        offset=offset,
    )
    return CrmTaskListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/tasks/{task_id}", response_model=CrmTaskDto)
async def get_my_crm_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = CrmTaskService(db)
    task = await service.get_task(task_id, user=current_user, admin=False)
    return await service.serialize_task(task)


@router.patch("/tasks/{task_id}/start", response_model=CrmTaskDto)
async def start_my_crm_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = CrmTaskService(db)
    return await service.start_task(task_id, current_user)


@router.patch("/tasks/{task_id}/result", response_model=CrmTaskDto)
async def update_my_crm_task_result(
    task_id: UUID,
    payload: CrmTaskResultRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = CrmTaskService(db)
    return await service.update_result(
        task_id,
        current_user,
        payload.seller_outcome,
        payload.seller_comment,
        payload.next_action_date,
    )


@router.patch("/tasks/{task_id}/postpone", response_model=CrmTaskDto)
async def postpone_my_crm_task(
    task_id: UUID,
    payload: CrmTaskPostponeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = CrmTaskService(db)
    return await service.postpone_task(task_id, current_user, payload.next_action_date, payload.seller_comment)


@router.patch("/tasks/{task_id}/complete", response_model=CrmTaskDto)
async def complete_my_crm_task(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = CrmTaskService(db)
    return await service.complete_task(task_id, current_user)
