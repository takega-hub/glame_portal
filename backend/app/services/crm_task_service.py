from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID
import re

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import normalize_phone
from app.models.crm_task import CrmTask, CrmTaskEvent
from app.models.customer_message import CustomerMessage
from app.models.purchase_history import PurchaseHistory
from app.models.user import User
from app.schemas.crm_tasks import (
    CrmAttributionResponse,
    CrmCampaignAnalyticsChannel,
    CrmCampaignAnalyticsItem,
    CrmCampaignAnalyticsPurchase,
    CrmCampaignAnalyticsResponse,
    CrmCustomerSummary,
    CrmDashboardResponse,
    CrmTaskDto,
    CrmTaskEventDto,
    CrmTaskImportRequest,
    CrmTaskImportResponse,
)
from app.services.crm_task_validation import (
    CONTACT_OUTCOMES,
    POSTPONE_OUTCOME,
    TERMINAL_OUTCOME_STATUS,
    build_crm_customer_message_payload,
    validate_crm_task_result,
)
from app.services.sales_record_filters import is_analytics_eligible_product
from app.services.customer_questionnaire_service import (
    crm_contact_instruction,
    questionnaire_from_preferences,
)

OPEN_STATUSES = {"new", "in_progress", "postponed"}
RESOLVED_STATUSES = {"worked", "closed", "not_relevant", "do_not_disturb", "quality_complaint"}
OVERDUE_STATUS = "overdue"
ACTIVE_STATUSES = OPEN_STATUSES | {OVERDUE_STATUS}
TERMINAL_STATUSES = {"closed", "not_relevant", "do_not_disturb", "quality_complaint"}
CRM_ASSIGNEE_ROLES = {"seller", "manager"}
CRM_TASK_OVERDUE_AFTER_DAYS = 3
INVALID_CRM_CITY_VALUES = {
    "меме овна",
    "сейтджелилова алина эбазеровна",
    "уразгильдеева екатерина ринадовна",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_customer_city(value: Optional[str]) -> Optional[str]:
    text = " ".join(str(value or "").replace("\u00a0", " ").strip().split())
    if not text:
        return None
    if text.lower() in INVALID_CRM_CITY_VALUES:
        return None
    return text


def _as_date(value: str | date | None) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if value == "today":
        return date.today()
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def _money_filter_to_kopecks(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        amount = float(str(value).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return None
    if amount < 0:
        return None
    return int(round(amount * 100))


class CrmTaskService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _actor_name(self, user: Optional[User]) -> Optional[str]:
        if not user:
            return None
        return getattr(user, "full_name", None) or getattr(user, "email", None) or getattr(user, "phone", None)

    async def _add_event(self, task: CrmTask, event_type: str, actor: Optional[User], previous_status: Optional[str], payload: Optional[Dict[str, Any]] = None) -> None:
        self.db.add(CrmTaskEvent(
            task_id=task.id,
            event_type=event_type,
            actor_user_id=getattr(actor, "id", None),
            actor_name=self._actor_name(actor),
            previous_status=previous_status,
            next_status=task.status,
            payload=payload or {},
        ))

    def _seller_scope(self, user: User):
        return CrmTask.assigned_seller_user_id == user.id

    async def mark_overdue_tasks(self, *, today: Optional[date] = None, actor: Optional[User] = None) -> int:
        """Move active unfinished tasks to explicit overdue status after the 3-day work window."""
        target_day = today or date.today()
        cutoff = target_day - timedelta(days=CRM_TASK_OVERDUE_AFTER_DAYS)
        result = await self.db.execute(
            select(CrmTask).where(
                CrmTask.status.in_(list(OPEN_STATUSES)),
                CrmTask.work_date <= cutoff,
            )
        )
        tasks = result.scalars().all()
        if not tasks:
            return 0
        now = _now()
        for task in tasks:
            previous = task.status
            task.status = OVERDUE_STATUS
            task.updated_at = now
            await self._add_event(task, "marked_overdue", actor, previous, {
                "overdue_after_days": CRM_TASK_OVERDUE_AFTER_DAYS,
                "work_date": task.work_date.isoformat() if task.work_date else None,
                "cutoff_date": cutoff.isoformat(),
            })
        await self.db.commit()
        return len(tasks)

    def _base_query(self):
        return select(CrmTask).options(
            selectinload(CrmTask.customer),
            selectinload(CrmTask.events),
        )

    def _apply_common_filters(
        self,
        stmt,
        *,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        status_value: Optional[str] = None,
        store_name: Optional[str] = None,
        seller_user_id: Optional[UUID] = None,
        seller_external_id: Optional[str] = None,
        seller_name: Optional[str] = None,
        crm_group: Optional[str] = None,
        campaign_id: Optional[str] = None,
        customer_query: Optional[str] = None,
        customer_segment: Optional[str] = None,
        min_total_spent: Optional[Any] = None,
        max_total_spent: Optional[Any] = None,
        only_overdue: bool = False,
        only_without_comment: bool = False,
        only_with_attribution: bool = False,
    ):
        if start_date:
            stmt = stmt.where(CrmTask.work_date >= start_date)
        if end_date:
            stmt = stmt.where(CrmTask.work_date <= end_date)
        if status_value:
            statuses = [x.strip() for x in status_value.split(",") if x.strip()]
            if statuses:
                stmt = stmt.where(CrmTask.status.in_(statuses))
        if store_name:
            stmt = stmt.where(CrmTask.store_name == store_name)
        if seller_user_id:
            stmt = stmt.where(CrmTask.assigned_seller_user_id == seller_user_id)
        if seller_external_id:
            stmt = stmt.where(CrmTask.assigned_seller_external_id == seller_external_id)
        if seller_name:
            stmt = stmt.where(func.lower(CrmTask.assigned_seller_name).like(f"%{seller_name.lower()}%"))
        if crm_group:
            stmt = stmt.where(CrmTask.crm_group == crm_group)
        if campaign_id:
            stmt = stmt.where(CrmTask.campaign_id == campaign_id)
        if customer_query:
            query = customer_query.strip()
            if query:
                lowered = f"%{query.lower()}%"
                digits = re.sub(r"\D+", "", query)
                phone_terms = [query]
                if digits:
                    phone_terms.append(digits)
                    normalized = normalize_phone(digits)
                    if normalized:
                        phone_terms.append(normalized)
                customer_conditions = [
                    func.lower(User.full_name).like(lowered),
                    func.lower(User.email).like(lowered),
                ]
                customer_conditions.extend(User.phone.ilike(f"%{term}%") for term in set(phone_terms) if term)
                stmt = stmt.where(CrmTask.customer.has(or_(*customer_conditions)))
        if customer_segment:
            segment = customer_segment.strip().lower()
            if segment:
                aliases = {
                    "vip": ["vip", "вип"],
                    "вип": ["vip", "вип"],
                    "new": ["new", "новый", "новые"],
                    "active": ["active", "активный", "активные"],
                    "sleeping": ["sleeping", "спящий", "спящие"],
                }.get(segment, [segment])
                stmt = stmt.where(CrmTask.customer.has(func.lower(User.customer_segment).in_(aliases)))
        min_total_kopecks = _money_filter_to_kopecks(min_total_spent)
        max_total_kopecks = _money_filter_to_kopecks(max_total_spent)
        if min_total_kopecks is not None or max_total_kopecks is not None:
            customer_total = (
                select(func.coalesce(func.max(User.total_spent), 0))
                .where(User.id == CrmTask.customer_id)
                .scalar_subquery()
            )
            purchase_total = (
                select(func.coalesce(func.sum(PurchaseHistory.total_amount), 0))
                .where(PurchaseHistory.user_id == CrmTask.customer_id)
                .scalar_subquery()
            )
            if min_total_kopecks is not None:
                stmt = stmt.where(or_(customer_total >= min_total_kopecks, purchase_total >= min_total_kopecks))
            if max_total_kopecks is not None:
                stmt = stmt.where(and_(customer_total <= max_total_kopecks, purchase_total <= max_total_kopecks))
        if only_overdue:
            stmt = stmt.where(CrmTask.status == OVERDUE_STATUS)
        if only_without_comment:
            stmt = stmt.where(or_(CrmTask.seller_comment.is_(None), func.length(func.trim(CrmTask.seller_comment)) == 0))
        if only_with_attribution:
            stmt = stmt.where(
                or_(
                    CrmTask.attributed_purchase_count > 0,
                    CrmTask.attributed_revenue_kopecks > 0,
                )
            )
        return stmt

    async def list_seller_tasks(
        self,
        user: User,
        date_value: str | date | None = "today",
        status_value: Optional[str] = None,
        crm_group: Optional[str] = None,
        include_overdue: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[List[CrmTaskDto], int]:
        await self.mark_overdue_tasks(today=_as_date(date_value) or date.today())
        target_date = _as_date(date_value)
        where = [self._seller_scope(user)]
        if target_date:
            # A task has a 3-day work window. It must stay visible to the
            # assigned seller on the days after creation until it is completed
            # or explicitly moved to overdue by mark_overdue_tasks().
            date_clause = CrmTask.work_date <= target_date
            if include_overdue:
                date_clause = or_(date_clause, CrmTask.status == OVERDUE_STATUS)
            where.append(date_clause)
        statuses = [x.strip() for x in (status_value or "").split(",") if x.strip()]
        where.append(CrmTask.status.in_(statuses or list(ACTIVE_STATUSES)))
        if crm_group:
            where.append(CrmTask.crm_group == crm_group)
        stmt = self._base_query().where(*where).order_by(CrmTask.priority.asc(), CrmTask.work_date.asc(), CrmTask.created_at.asc())
        total = await self._count(stmt)
        result = await self.db.execute(stmt.limit(limit).offset(offset))
        tasks = result.scalars().unique().all()
        return [await self.serialize_task(task, include_detail=False) for task in tasks], total

    async def list_admin_tasks(self, *, limit: int = 100, offset: int = 0, **filters: Any) -> tuple[List[CrmTaskDto], int]:
        await self.mark_overdue_tasks()
        stmt = self._apply_common_filters(self._base_query(), **filters).order_by(CrmTask.work_date.desc(), CrmTask.priority.asc(), CrmTask.created_at.desc())
        total = await self._count(stmt)
        result = await self.db.execute(stmt.limit(limit).offset(offset))
        tasks = result.scalars().unique().all()
        return [await self.serialize_task(task, include_detail=False) for task in tasks], total

    async def _count(self, stmt) -> int:
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        return int((await self.db.execute(count_stmt)).scalar() or 0)

    async def get_task(self, task_id: UUID, *, user: Optional[User] = None, admin: bool = False) -> CrmTask:
        result = await self.db.execute(self._base_query().where(CrmTask.id == task_id))
        task = result.scalars().unique().one_or_none()
        if not task:
            raise HTTPException(status_code=404, detail="CRM-задача не найдена")
        if user and not admin and not self._can_seller_access(task, user):
            raise HTTPException(status_code=403, detail="Нет доступа к CRM-задаче другого продавца")
        return task

    def _can_seller_access(self, task: CrmTask, user: User) -> bool:
        return bool(task.assigned_seller_user_id and task.assigned_seller_user_id == user.id)

    async def start_task(self, task_id: UUID, actor: User, *, admin: bool = False) -> CrmTaskDto:
        await self.mark_overdue_tasks()
        task = await self.get_task(task_id, user=actor, admin=admin)
        previous = task.status
        if task.status == OVERDUE_STATUS:
            if admin:
                raise HTTPException(status_code=400, detail="Просроченную задачу можно вернуть в работу только через переназначение исполнителя")
            raise HTTPException(status_code=403, detail="Просроченную задачу не может взять в работу сотрудник. Обратитесь к администратору.")
        if task.status == "new":
            task.status = "in_progress"
            task.updated_at = _now()
            await self._add_event(task, "started", actor, previous)
            await self.db.commit()
            await self.db.refresh(task)
        return await self.serialize_task(task)

    async def _record_customer_message(self, task: CrmTask, actor: Optional[User]) -> None:
        payload = build_crm_customer_message_payload(
            task_id=str(task.id),
            status=task.status,
            seller_outcome=task.seller_outcome or "",
            seller_comment=task.seller_comment or "",
            next_action_date=task.next_action_date,
            crm_group=task.crm_group,
            reason=task.reason,
            seller_action=task.seller_action,
            script_key=task.script_key,
            store_name=task.store_name,
            seller_name=self._actor_name(actor) or task.assigned_seller_name,
            work_date=task.work_date,
            campaign_id=task.campaign_id,
            campaign_name=task.campaign_name,
        )
        # customer_messages has no dedicated message_kind column; the customer card reads it from payload.
        payload["message_kind"] = "crm_call"
        profile = questionnaire_from_preferences(getattr(task.customer, "preferences", None)) if getattr(task, "customer", None) else None
        if profile:
            payload["questionnaire_contact_policy"] = {
                "channels": profile.get("contact_channels", []),
                "do_not_contact": profile.get("do_not_contact", False),
                "instruction": crm_contact_instruction(profile),
            }
        existing_result = await self.db.execute(
            select(CustomerMessage).where(
                CustomerMessage.user_id == task.customer_id,
                CustomerMessage.event_type == "crm_call",
                CustomerMessage.payload["crm_task_id"].astext == str(task.id),
            )
        )
        message = existing_result.scalar_one_or_none()
        if message is None:
            message = CustomerMessage(
                user_id=task.customer_id,
                message=task.seller_comment or task.seller_action or task.reason or "CRM взаимодействие",
                cta=task.seller_action,
                segment=task.crm_group,
                event_type="crm_call",
                event_brand=task.script_key,
                event_store=task.store_name,
                payload=payload,
                status="completed",
                sent_at=task.last_contacted_at,
            )
            self.db.add(message)
        else:
            message.message = task.seller_comment or message.message
            message.cta = task.seller_action
            message.segment = task.crm_group
            message.event_brand = task.script_key
            message.event_store = task.store_name
            message.payload = {**(message.payload or {}), **payload}
            message.status = "completed"
            message.sent_at = task.last_contacted_at or message.sent_at

    async def update_result(self, task_id: UUID, actor: User, seller_outcome: str, seller_comment: str, next_action_date: Optional[date], *, admin: bool = False) -> CrmTaskDto:
        await self.mark_overdue_tasks()
        task = await self.get_task(task_id, user=actor, admin=admin)
        if task.status == OVERDUE_STATUS and not admin:
            raise HTTPException(status_code=403, detail="Просроченную задачу сначала должен вернуть в работу администратор")
        try:
            next_status = validate_crm_task_result(seller_outcome, seller_comment, next_action_date)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        previous = task.status
        task.status = next_status
        task.seller_outcome = seller_outcome
        task.seller_comment = seller_comment.strip()
        task.next_action_date = next_action_date
        task.updated_at = _now()
        if seller_outcome in CONTACT_OUTCOMES or next_status in {"worked", "closed"}:
            task.last_contacted_at = _now()
        if next_status in RESOLVED_STATUSES:
            task.completed_at = _now()
        else:
            task.completed_at = None
        await self._add_event(task, "result_updated", actor, previous, {
            "seller_outcome": seller_outcome,
            "seller_comment": seller_comment,
            "next_action_date": next_action_date.isoformat() if next_action_date else None,
        })
        await self._create_followup_task_if_needed(task, actor)
        await self._record_customer_message(task, actor)
        await self.db.commit()
        await self.db.refresh(task)
        return await self.serialize_task(task)

    async def _create_followup_task_if_needed(self, task: CrmTask, actor: Optional[User]) -> None:
        if not task.next_action_date:
            return
        if task.next_action_date <= date.today():
            return
        if task.seller_outcome == POSTPONE_OUTCOME:
            return
        idempotency_key = f"crm_followup:{task.id}:{task.next_action_date.isoformat()}"
        existing = await self.db.scalar(select(CrmTask.id).where(CrmTask.source_idempotency_key == idempotency_key))
        if existing:
            return
        followup = CrmTask(
            customer_id=task.customer_id,
            assigned_seller_user_id=task.assigned_seller_user_id,
            assigned_seller_external_id=task.assigned_seller_external_id,
            assigned_seller_name=task.assigned_seller_name,
            store_id=task.store_id,
            store_name=task.store_name,
            work_date=task.next_action_date,
            due_date=datetime.combine(task.next_action_date, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=20),
            priority=max(1, int(task.priority or 3)),
            crm_group=task.crm_group,
            reason=f"Follow-up по CRM-задаче: {task.seller_comment or task.reason or 'связаться повторно'}",
            seller_action="Связаться с клиентом по зафиксированной договорённости и обновить результат.",
            script_key=f"{task.script_key or task.crm_group}_followup",
            script_text=task.script_text,
            status="new",
            campaign_id=task.campaign_id,
            campaign_name=task.campaign_name,
            source="crm_followup",
            source_row_id=str(task.id),
            source_idempotency_key=idempotency_key,
            source_payload={
                **(task.source_payload or {}),
                "task_type": "FOLLOW_UP",
                "parent_task_id": str(task.id),
                "parent_source": task.source,
                "parent_outcome": task.seller_outcome,
                "next_action_date": task.next_action_date.isoformat(),
            },
            created_by_user_id=getattr(actor, "id", None),
            updated_at=_now(),
        )
        self.db.add(followup)
        await self.db.flush()
        await self._add_event(followup, "created_from_followup", actor, None, {
            "parent_task_id": str(task.id),
            "next_action_date": task.next_action_date.isoformat(),
        })

    async def postpone_task(self, task_id: UUID, actor: User, next_action_date: date, seller_comment: str, *, admin: bool = False) -> CrmTaskDto:
        return await self.update_result(task_id, actor, POSTPONE_OUTCOME, seller_comment, next_action_date, admin=admin)

    async def complete_task(self, task_id: UUID, actor: User, *, admin: bool = False) -> CrmTaskDto:
        task = await self.get_task(task_id, user=actor, admin=admin)
        if not task.seller_outcome or not (task.seller_comment or "").strip():
            raise HTTPException(status_code=400, detail="Для закрытия нужны итог и комментарий продавца")
        previous = task.status
        task.status = "closed"
        task.completed_at = _now()
        task.updated_at = _now()
        await self._add_event(task, "completed", actor, previous)
        await self.db.commit()
        await self.db.refresh(task)
        return await self.serialize_task(task)

    async def assign_task(self, task_id: UUID, actor: User, payload: Dict[str, Any]) -> CrmTaskDto:
        task = await self.get_task(task_id, admin=True)
        previous = task.status

        seller_user_id = payload.get("assigned_seller_user_id")
        if seller_user_id:
            seller_result = await self.db.execute(
                select(User).where(
                    User.id == seller_user_id,
                    User.is_customer.is_(False),
                    User.role.in_(CRM_ASSIGNEE_ROLES),
                )
            )
            seller = seller_result.scalar_one_or_none()
            if not seller:
                raise HTTPException(status_code=400, detail="Выбранный исполнитель не найден среди пользователей платформы")
            task.assigned_seller_user_id = seller.id
            task.assigned_seller_name = self._actor_name(seller)
            task.assigned_seller_external_id = payload.get("assigned_seller_external_id")
        elif "assigned_seller_user_id" in payload:
            task.assigned_seller_user_id = None
            task.assigned_seller_name = None
            task.assigned_seller_external_id = None

        for field in ["store_id", "store_name"]:
            if field in payload:
                setattr(task, field, payload[field])
        if previous == OVERDUE_STATUS and task.assigned_seller_user_id:
            task.status = "in_progress"
            task.completed_at = None
        task.updated_at = _now()
        await self._add_event(task, "assigned", actor, previous, {
            **payload,
            "overdue_returned_to_work": previous == OVERDUE_STATUS and task.status == "in_progress",
        })
        await self.db.commit()
        await self.db.refresh(task)
        return await self.serialize_task(task)

    async def delete_task(self, task_id: UUID, actor: User, *, admin: bool = False) -> Dict[str, Any]:
        task = await self.get_task(task_id, user=actor, admin=admin)
        deleted_id = str(task.id)
        customer_id = str(task.customer_id)
        campaign_id = task.campaign_id
        await self.db.delete(task)
        await self.db.commit()
        return {"deleted": True, "task_id": deleted_id, "customer_id": customer_id, "campaign_id": campaign_id}

    async def import_tasks(self, request: CrmTaskImportRequest, actor: Optional[User]) -> CrmTaskImportResponse:
        response = CrmTaskImportResponse()
        for index, row in enumerate(request.rows):
            try:
                phone = normalize_phone(row.phone)
                user = await self._find_customer_by_phone(phone)
                if not user:
                    response.not_found_customers += 1
                    response.errors.append({"row": index + 1, "phone": phone, "error": "customer_not_found"})
                    continue
                seller_name = self._clean_imported_seller_name(row.seller_name)
                seller = await self._find_seller_by_name(seller_name)
                idempotency = self._row_idempotency_key(request, row, phone, index)
                existing = None
                if idempotency:
                    existing_result = await self.db.execute(
                        select(CrmTask)
                        .options(selectinload(CrmTask.customer))
                        .where(CrmTask.source_idempotency_key == idempotency)
                    )
                    existing = existing_result.scalar_one_or_none()
                task = existing or CrmTask(customer_id=user.id, created_by_user_id=getattr(actor, "id", None))
                if not existing:
                    task.customer = user
                if not existing:
                    task.assigned_seller_user_id = None
                    task.assigned_seller_external_id = None
                    task.assigned_seller_name = None
                if seller:
                    task.assigned_seller_user_id = seller.id
                    task.assigned_seller_external_id = row.seller_external_id
                    task.assigned_seller_name = seller.full_name or seller_name
                elif seller_name:
                    task.assigned_seller_user_id = None
                    task.assigned_seller_external_id = row.seller_external_id
                    task.assigned_seller_name = seller_name
                elif request.source == "google_sheet_seller_crm":
                    task.assigned_seller_user_id = None
                    task.assigned_seller_external_id = None
                    task.assigned_seller_name = None
                task.store_id = row.store_id
                task.store_name = row.store_name
                task.work_date = row.work_date
                task.due_date = row.due_date
                task.priority = row.priority
                task.crm_group = row.crm_group
                task.reason = row.reason
                task.seller_action = row.seller_action
                task.script_key = row.script_key
                task.script_text = row.script_text
                task.status = self._status_from_import_row(row, task.status)
                task.seller_outcome = row.seller_outcome
                task.seller_comment = row.seller_comment
                task.next_action_date = row.next_action_date
                if task.status in RESOLVED_STATUSES:
                    task.completed_at = task.completed_at or _now()
                    if request.source == "google_sheet_seller_crm" and task.work_date > task.completed_at.date():
                        task.work_date = task.completed_at.date()
                elif task.status in OPEN_STATUSES:
                    task.completed_at = None
                task.campaign_id = request.campaign_id
                task.campaign_name = request.campaign_name
                task.source = request.source
                task.source_row_id = row.source_row_id
                task.source_idempotency_key = idempotency
                task.source_payload = {
                    **(row.source_payload or {}),
                    "phone": phone,
                    "customer_name": row.customer_name,
                    "imported_seller_name": row.seller_name,
                    "imported_seller_external_id": row.seller_external_id,
                }
                task.updated_at = _now()
                if not existing:
                    self.db.add(task)
                    await self.db.flush()
                    await self._add_event(task, "created_from_import", actor, None, {"source": request.source, "row": index + 1})
                    response.created += 1
                else:
                    await self._add_event(task, "updated_from_import", actor, task.status, {"source": request.source, "row": index + 1})
                    response.updated += 1
                response.tasks.append(await self.serialize_task(task, include_detail=False))
            except Exception as exc:
                response.errors.append({"row": index + 1, "error": str(exc)})
                response.skipped += 1
        await self.db.commit()
        return response

    async def _find_customer_by_phone(self, normalized_phone: str) -> Optional[User]:
        phone_variants = {normalized_phone}
        if len(normalized_phone) == 11 and normalized_phone.startswith("7"):
            phone_variants.add("8" + normalized_phone[1:])
            phone_variants.add(normalized_phone[1:])
        elif len(normalized_phone) == 11 and normalized_phone.startswith("8"):
            phone_variants.add("7" + normalized_phone[1:])
            phone_variants.add(normalized_phone[1:])
        elif len(normalized_phone) == 10:
            phone_variants.add("7" + normalized_phone)
            phone_variants.add("8" + normalized_phone)

        db_phone_digits = func.regexp_replace(func.coalesce(User.phone, ""), r"\D+", "", "g")
        result = await self.db.execute(
            select(User).where(
                User.is_customer == True,
                or_(
                    User.phone.in_(phone_variants),
                    db_phone_digits.in_(phone_variants),
                ),
            ).order_by(User.updated_at.desc().nullslast(), User.created_at.desc().nullslast())
        )
        users = result.scalars().all()
        if not users:
            return None
        for user in users:
            if normalize_phone(user.phone or "") == normalized_phone:
                return user
        return users[0]

    def _normalize_person_name(self, value: Optional[str]) -> str:
        text = re.sub(r"\s+", " ", (value or "").replace("ё", "е").lower()).strip()
        return text

    def _clean_imported_seller_name(self, value: Optional[str]) -> Optional[str]:
        text = re.sub(r"\s+", " ", (value or "").strip())
        if not text:
            return None
        normalized = self._normalize_person_name(text)
        if normalized.startswith("создано в 1с"):
            return None
        return text

    async def _find_seller_by_name(self, seller_name: Optional[str]) -> Optional[User]:
        normalized = self._normalize_person_name(seller_name)
        if not normalized:
            return None
        staff_roles = ("seller", "manager", "admin")
        result = await self.db.execute(
            select(User)
            .where(User.role.in_(staff_roles), User.full_name.is_not(None))
            .order_by(User.updated_at.desc().nullslast(), User.created_at.desc().nullslast())
        )
        staff = result.scalars().all()
        if not staff:
            return None

        def staff_name(user: User) -> str:
            return self._normalize_person_name(user.full_name)

        for user in staff:
            if staff_name(user) == normalized:
                return user
        for user in staff:
            name = staff_name(user)
            if name.startswith(normalized + " ") or normalized.startswith(name + " "):
                return user
        seller_parts = normalized.split()
        if seller_parts:
            surname = seller_parts[0]
            surname_matches = [user for user in staff if staff_name(user).split()[:1] == [surname]]
            if len(surname_matches) == 1:
                return surname_matches[0]
        return None

    def _row_idempotency_key(self, request: CrmTaskImportRequest, row: Any, phone: str, index: int) -> str:
        if row.source_row_id:
            return f"{request.source}:{request.campaign_id or 'no_campaign'}:{row.source_row_id}"
        return f"{request.source}:{request.campaign_id or 'no_campaign'}:{phone}:{row.work_date.isoformat()}:{row.crm_group}:{index}"

    async def dashboard(self, **filters: Any) -> CrmDashboardResponse:
        await self.mark_overdue_tasks()
        stmt = self._apply_common_filters(select(CrmTask), **filters)
        result = await self.db.execute(stmt)
        tasks = result.scalars().all()
        today = date.today()
        dashboard = CrmDashboardResponse(total=len(tasks))
        by_status: Dict[str, int] = {}
        by_group: Dict[str, int] = {}
        by_seller: Dict[str, Dict[str, Any]] = {}
        for task in tasks:
            by_status[task.status] = by_status.get(task.status, 0) + 1
            by_group[task.crm_group] = by_group.get(task.crm_group, 0) + 1
            seller_label = task.assigned_seller_name or task.assigned_seller_external_id or "Не назначено"
            seller_key = str(task.assigned_seller_user_id or task.assigned_seller_external_id or seller_label)
            seller_row = by_seller.setdefault(seller_key, {
                "seller": seller_label,
                "seller_user_id": str(task.assigned_seller_user_id) if task.assigned_seller_user_id else None,
                "seller_external_id": task.assigned_seller_external_id,
                "total": 0,
                "active": 0,
                "completed": 0,
                "overdue": 0,
                "without_comment": 0,
                "postponed": 0,
                "buyers": 0,
                "purchase_count": 0,
                "revenue_kopecks": 0,
            })
            seller_row["total"] += 1
            if task.status == OVERDUE_STATUS:
                dashboard.overdue += 1
                seller_row["overdue"] += 1
            elif task.status in TERMINAL_STATUSES or task.completed_at:
                dashboard.completed += 1
                seller_row["completed"] += 1
            elif task.status == "worked":
                dashboard.completed += 1
                seller_row["completed"] += 1
            else:
                dashboard.active += 1
                seller_row["active"] += 1
            if not (task.seller_comment or "").strip():
                dashboard.without_comment += 1
                seller_row["without_comment"] += 1
            if task.status == "postponed":
                dashboard.postponed += 1
                seller_row["postponed"] += 1
            attributed_purchase_count = int(task.attributed_purchase_count or 0)
            attributed_revenue = int(task.attributed_revenue_kopecks or 0)
            if attributed_purchase_count > 0 or attributed_revenue > 0:
                seller_row["buyers"] += 1
            seller_row["purchase_count"] += attributed_purchase_count
            seller_row["revenue_kopecks"] += attributed_revenue
            dashboard.attributed_purchase_count += attributed_purchase_count
            dashboard.attributed_revenue_kopecks += attributed_revenue
        for row in by_seller.values():
            total = int(row.get("total") or 0)
            completed = int(row.get("completed") or 0)
            buyers = int(row.get("buyers") or 0)
            revenue = int(row.get("revenue_kopecks") or 0)
            row["completion_rate"] = round((completed / total) * 100, 1) if total else 0
            row["conversion_rate"] = round((buyers / completed) * 100, 1) if completed else 0
            row["revenue_per_task_kopecks"] = int(revenue / total) if total else 0
            row["revenue_per_completed_task_kopecks"] = int(revenue / completed) if completed else 0
        dashboard.by_status = by_status
        dashboard.by_group = by_group
        dashboard.by_seller = sorted(by_seller.values(), key=lambda row: (row["revenue_kopecks"], row["completed"], row["total"]), reverse=True)
        return dashboard

    def _interaction_channel(self, task: CrmTask) -> tuple[str, str]:
        payload = task.source_payload or {}
        raw = str(
            payload.get("channel")
            or payload.get("message_channel")
            or payload.get("communication_channel")
            or payload.get("Тип взаимодействия")
            or task.crm_group
            or task.source
            or "other"
        ).strip().lower()
        if "sms" in raw or "смс" in raw or "sms" in (task.source or "").lower():
            return "sms", "SMS"
        if "звон" in raw or "call" in raw or task.crm_group == "personal_call":
            return "call", "Звонки"
        if "whatsapp" in raw or "wa" == raw:
            return "whatsapp", "WhatsApp"
        if "telegram" in raw or "телеграм" in raw:
            return "telegram", "Telegram"
        if "instagram" in raw or "инстаграм" in raw:
            return "instagram", "Instagram"
        if "message" in raw or "сообщ" in raw or task.crm_group in {"personal_message", "segmented_message"}:
            return "message", "Сообщения"
        return "other", "Прочее"

    def _datetime_in_date_window(self, value: Optional[datetime], *, start_date: Optional[date], end_date: Optional[date]) -> bool:
        if value is None:
            return start_date is None and end_date is None
        value_date = value.date()
        if start_date and value_date < start_date:
            return False
        if end_date and value_date > end_date:
            return False
        return True

    def _task_campaign_date(self, task: CrmTask) -> Optional[datetime]:
        if task.last_contacted_at:
            return task.last_contacted_at
        if task.completed_at:
            return task.completed_at
        if task.work_date:
            return datetime.combine(task.work_date, datetime.min.time(), tzinfo=timezone.utc)
        return task.created_at

    def _task_purchase_window_start(self, task: CrmTask) -> Optional[datetime]:
        if task.last_contacted_at:
            return task.last_contacted_at
        if task.source == "google_sheet_seller_crm" and task.work_date:
            return datetime.combine(task.work_date, datetime.min.time(), tzinfo=timezone.utc)
        return task.last_contacted_at or task.completed_at

    async def _task_window_purchases(self, task: CrmTask, *, window_days: int) -> List[PurchaseHistory]:
        start = self._task_purchase_window_start(task)
        if not start:
            return []
        end = start + timedelta(days=window_days)
        purchases_result = await self.db.execute(select(PurchaseHistory).where(
            PurchaseHistory.user_id == task.customer_id,
            PurchaseHistory.purchase_date >= start,
            PurchaseHistory.purchase_date <= end,
        ))
        return [p for p in purchases_result.scalars().all() if self._eligible_purchase(p)]

    async def campaign_analytics(self, *, window_days: int = 14, **filters: Any) -> CrmCampaignAnalyticsResponse:
        start_date = filters.get("start_date")
        end_date = filters.get("end_date")
        task_filters = dict(filters)
        task_filters["start_date"] = None
        task_filters["end_date"] = None
        only_with_attribution = bool(task_filters.pop("only_with_attribution", False))
        stmt = self._apply_common_filters(self._base_query(), **task_filters).order_by(CrmTask.created_at.desc())
        result = await self.db.execute(stmt)
        tasks = result.scalars().unique().all()
        grouped: Dict[str, CrmCampaignAnalyticsItem] = {}
        channel_rows: Dict[str, Dict[str, CrmCampaignAnalyticsChannel]] = {}

        for task in tasks:
            if task.source == "manual_test" or task.campaign_id == "manual-test":
                continue
            campaign_date = self._task_campaign_date(task)
            if not self._datetime_in_date_window(campaign_date, start_date=start_date, end_date=end_date):
                continue
            contacted = bool(self._task_purchase_window_start(task) or (task.seller_comment or "").strip())
            purchases = await self._task_window_purchases(task, window_days=window_days)
            document_ids = list(dict.fromkeys([str(p.document_id_1c or p.id) for p in purchases]))
            purchase_count = len(document_ids)
            revenue = sum(int(p.total_amount or 0) for p in purchases)
            if only_with_attribution and purchase_count <= 0 and revenue <= 0:
                continue

            campaign_key = task.campaign_id or f"source:{task.source or 'manual'}:{task.campaign_name or 'Без кампании'}"
            campaign = grouped.setdefault(
                campaign_key,
                CrmCampaignAnalyticsItem(
                    campaign_id=task.campaign_id,
                    campaign_name=task.campaign_name or task.campaign_id or "Без кампании",
                    source=task.source or "manual",
                ),
            )
            campaign.recipients += 1
            if contacted:
                campaign.contacted += 1
            if task.status in RESOLVED_STATUSES or task.completed_at:
                campaign.completed += 1
            campaign.purchases += purchase_count
            campaign.revenue_kopecks += revenue
            if purchase_count > 0 or revenue > 0:
                campaign.buyers += 1
                campaign.purchases_list.append(CrmCampaignAnalyticsPurchase(
                    task_id=str(task.id),
                    customer_id=str(task.customer_id),
                    customer_name=getattr(task.customer, "full_name", None),
                    customer_phone=getattr(task.customer, "phone", None),
                    store_name=task.store_name,
                    seller_name=task.assigned_seller_name,
                    contact_date=self._task_purchase_window_start(task),
                    purchase_count=purchase_count,
                    revenue_kopecks=revenue,
                    purchase_ids=document_ids,
                ))

            channel_key, channel_label = self._interaction_channel(task)
            campaign_channels = channel_rows.setdefault(campaign_key, {})
            channel = campaign_channels.setdefault(channel_key, CrmCampaignAnalyticsChannel(channel=channel_key, label=channel_label))
            channel.recipients += 1
            if contacted:
                channel.contacted += 1
            channel.purchases += purchase_count
            channel.revenue_kopecks += revenue

        await self._append_sms_campaign_analytics(
            grouped,
            channel_rows,
            start_date=start_date,
            end_date=end_date,
            store_name=filters.get("store_name"),
            campaign_id=filters.get("campaign_id"),
            only_with_attribution=only_with_attribution,
            window_days=window_days,
        )

        for key, campaign in grouped.items():
            campaign.conversion_rate = round((campaign.buyers / campaign.contacted) * 100, 1) if campaign.contacted else 0
            campaign.revenue_per_contact_kopecks = int(campaign.revenue_kopecks / campaign.contacted) if campaign.contacted else 0
            for channel in channel_rows.get(key, {}).values():
                channel.conversion_rate = round((channel.purchases / channel.contacted) * 100, 1) if channel.contacted else 0
            campaign.by_channel = sorted(channel_rows.get(key, {}).values(), key=lambda row: row.recipients, reverse=True)
            campaign.purchases_list = sorted(campaign.purchases_list, key=lambda row: row.revenue_kopecks, reverse=True)

        campaigns = sorted(grouped.values(), key=lambda row: (row.revenue_kopecks, row.contacted, row.recipients), reverse=True)
        return CrmCampaignAnalyticsResponse(
            window_days=window_days,
            total_campaigns=len(campaigns),
            total_recipients=sum(row.recipients for row in campaigns),
            total_contacted=sum(row.contacted for row in campaigns),
            total_purchases=sum(row.purchases for row in campaigns),
            total_revenue_kopecks=sum(row.revenue_kopecks for row in campaigns),
            campaigns=campaigns,
        )

    async def _append_sms_campaign_analytics(
        self,
        grouped: Dict[str, CrmCampaignAnalyticsItem],
        channel_rows: Dict[str, Dict[str, CrmCampaignAnalyticsChannel]],
        *,
        start_date: Optional[date],
        end_date: Optional[date],
        store_name: Optional[str],
        campaign_id: Optional[str],
        only_with_attribution: bool,
        window_days: int,
    ) -> None:
        stmt = select(CustomerMessage).options(selectinload(CustomerMessage.user)).where(
            or_(
                CustomerMessage.event_type == "external_sms_aero",
                CustomerMessage.payload["generation_id"].astext.isnot(None),
            )
        )
        if store_name:
            stmt = stmt.where(CustomerMessage.event_store == store_name)
        result = await self.db.execute(stmt.order_by(CustomerMessage.sent_at.desc().nulls_last(), CustomerMessage.created_at.desc()))
        messages = result.scalars().unique().all()
        seen_sms_touches: set[tuple[str, str, str, Optional[date]]] = set()

        for message in messages:
            payload = message.payload or {}
            if payload.get("is_technical") is True:
                continue
            interaction_at = message.sent_at
            if not self._datetime_in_date_window(interaction_at, start_date=start_date, end_date=end_date):
                continue
            generation_id = str(payload.get("generation_id") or "").strip()
            explicit_campaign_id = str(payload.get("campaign_id") or payload.get("sms_campaign_id") or "").strip()
            message_text = (message.message or "").lower()
            is_service_sms_aero_import = (
                message.event_type == "external_sms_aero"
                and not generation_id
                and not explicit_campaign_id
                and payload.get("source") == "sms_aero_list_import"
                and any(token in message_text for token in ("sertifikat", "сертификат", "pin", "prilozhen", "приложен"))
            )
            if is_service_sms_aero_import:
                continue
            if generation_id:
                base_name = " / ".join([x for x in [message.event_type, message.segment] if x]) or "SMS-кампания"
                sms_campaign_name = str(payload.get("campaign_name") or base_name).strip() or "SMS-кампания"
                sms_campaign_id = str(explicit_campaign_id or f"sms-generation:{generation_id}").strip()
            else:
                sms_campaign_name = str(payload.get("campaign_name") or "SMS Aero импорт").strip() or "SMS Aero импорт"
                sms_campaign_id = str(explicit_campaign_id or f"sms-aero:{sms_campaign_name}").strip()
            if campaign_id and campaign_id not in {sms_campaign_id, sms_campaign_name, generation_id}:
                continue
            campaign_key = f"sms-campaign:{sms_campaign_name.lower()}"
            touch_key = (
                campaign_key,
                str(message.user_id),
                (message.message or "").strip(),
                interaction_at.date() if interaction_at else None,
            )
            if touch_key in seen_sms_touches:
                continue
            seen_sms_touches.add(touch_key)
            purchases = await self._message_window_purchases(message, window_days=window_days)
            document_ids = list(dict.fromkeys([str(p.document_id_1c or p.id) for p in purchases]))
            revenue = sum(int(p.total_amount or 0) for p in purchases)
            purchase_count = len(document_ids)
            if only_with_attribution and purchase_count <= 0 and revenue <= 0:
                continue

            campaign = grouped.setdefault(
                campaign_key,
                CrmCampaignAnalyticsItem(
                    campaign_id=sms_campaign_id,
                    campaign_name=sms_campaign_name,
                    source="sms_aero" if payload.get("sms_id") or message.event_type == "external_sms_aero" else "generated_sms",
                ),
            )
            campaign.recipients += 1
            contacted = message.status in {"delivered", "sent"} or bool(message.sent_at)
            if contacted:
                campaign.contacted += 1
                campaign.completed += 1
            campaign.purchases += purchase_count
            campaign.revenue_kopecks += revenue
            if purchase_count > 0 or revenue > 0:
                campaign.buyers += 1
                user = getattr(message, "user", None)
                campaign.purchases_list.append(CrmCampaignAnalyticsPurchase(
                    task_id=str(message.id),
                    customer_id=str(message.user_id),
                    customer_name=getattr(user, "full_name", None),
                    customer_phone=getattr(user, "phone", None),
                    store_name=message.event_store,
                    seller_name="SMS Aero",
                    contact_date=interaction_at,
                    purchase_count=purchase_count,
                    revenue_kopecks=revenue,
                    purchase_ids=document_ids,
                ))

            campaign_channels = channel_rows.setdefault(campaign_key, {})
            channel = campaign_channels.setdefault("sms", CrmCampaignAnalyticsChannel(channel="sms", label="SMS"))
            channel.recipients += 1
            if contacted:
                channel.contacted += 1
            channel.purchases += purchase_count
            channel.revenue_kopecks += revenue

    async def _message_window_purchases(self, message: CustomerMessage, *, window_days: int) -> List[PurchaseHistory]:
        if not message.sent_at:
            return []
        start = message.sent_at
        end = start + timedelta(days=window_days)
        purchases_result = await self.db.execute(select(PurchaseHistory).where(
            PurchaseHistory.user_id == message.user_id,
            PurchaseHistory.purchase_date >= start,
            PurchaseHistory.purchase_date <= end,
        ))
        return [p for p in purchases_result.scalars().all() if self._eligible_purchase(p)]

    def _status_from_import_row(self, row: Any, current_status: Optional[str]) -> str:
        if row.seller_outcome and row.seller_comment:
            try:
                return validate_crm_task_result(row.seller_outcome, row.seller_comment, row.next_action_date)
            except ValueError:
                pass
        return row.status or current_status or "new"

    async def attribute_purchases(self, *, task_ids: Optional[Sequence[UUID]] = None, start_date: Optional[date] = None, end_date: Optional[date] = None, window_days: int = 14) -> CrmAttributionResponse:
        stmt = select(CrmTask).where((CrmTask.last_contacted_at.is_not(None)) | (CrmTask.completed_at.is_not(None)))
        if task_ids:
            stmt = stmt.where(CrmTask.id.in_(task_ids))
        result = await self.db.execute(stmt)
        tasks = result.scalars().all()
        total = CrmAttributionResponse()
        for task in tasks:
            campaign_date = self._task_campaign_date(task)
            if not self._datetime_in_date_window(campaign_date, start_date=start_date, end_date=end_date):
                continue
            start = self._task_purchase_window_start(task)
            if not start:
                continue
            end = start + timedelta(days=window_days)
            purchases_result = await self.db.execute(select(PurchaseHistory).where(
                PurchaseHistory.user_id == task.customer_id,
                PurchaseHistory.purchase_date >= start,
                PurchaseHistory.purchase_date <= end,
            ))
            purchases = [p for p in purchases_result.scalars().all() if self._eligible_purchase(p)]
            document_ids = list(dict.fromkeys([str(p.document_id_1c or p.id) for p in purchases]))
            revenue = sum(int(p.total_amount or 0) for p in purchases)
            task.attributed_purchase_ids = document_ids
            task.attributed_purchase_count = len(document_ids)
            task.attributed_revenue_kopecks = revenue
            task.attributed_at = _now()
            await self._update_customer_message_attribution(task, window_days=window_days)
            total.updated += 1
            total.purchase_count += len(document_ids)
            total.revenue_kopecks += revenue
        await self.db.commit()
        return total

    def _eligible_purchase(self, purchase: PurchaseHistory) -> bool:
        return is_analytics_eligible_product(
            product_name=getattr(purchase, "product_name", None),
            product_category=getattr(purchase, "category", None),
            product_article=getattr(purchase, "product_article", None),
            product_id=getattr(purchase, "product_id_1c", None) or getattr(purchase, "product_id", None),
            total_amount_kopecks=int(getattr(purchase, "total_amount", 0) or 0),
        )

    async def _update_customer_message_attribution(self, task: CrmTask, *, window_days: int) -> None:
        result = await self.db.execute(
            select(CustomerMessage).where(
                CustomerMessage.user_id == task.customer_id,
                CustomerMessage.event_type == "crm_call",
                CustomerMessage.payload["crm_task_id"].astext == str(task.id),
            )
        )
        message = result.scalar_one_or_none()
        if not message:
            return
        payload = dict(message.payload or {})
        converted = bool(task.attributed_revenue_kopecks and task.attributed_revenue_kopecks > 0)
        payload["conversion_result"] = {
            "window_days": window_days,
            "converted": converted,
            "status": "positive" if converted else "no_purchase_14d",
            "purchase_count": task.attributed_purchase_count or 0,
            "revenue_kopecks": task.attributed_revenue_kopecks or 0,
            "revenue_rub": round((task.attributed_revenue_kopecks or 0) / 100, 2),
            "purchase_ids": task.attributed_purchase_ids or [],
            "attributed_at": task.attributed_at.isoformat() if task.attributed_at else None,
        }
        payload["interaction_result"] = "positive_purchase_after_contact" if converted else "no_purchase_after_contact_14d"
        message.payload = payload

    async def serialize_task(self, task: CrmTask, *, include_detail: bool = True) -> CrmTaskDto:
        recent_messages: List[Dict[str, Any]] = []
        if include_detail:
            msg_result = await self.db.execute(select(CustomerMessage).where(CustomerMessage.user_id == task.customer_id).order_by(CustomerMessage.created_at.desc()).limit(10))
            for msg in msg_result.scalars().all():
                recent_messages.append({
                    "id": str(msg.id),
                    "message": msg.message,
                    "cta": msg.cta,
                    "segment": msg.segment,
                    "event_type": msg.event_type,
                    "status": msg.status,
                    "sent_at": msg.sent_at.isoformat() if msg.sent_at else None,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                    "payload": msg.payload or {},
                })
        questionnaire = questionnaire_from_preferences(getattr(task.customer, "preferences", None)) if getattr(task, "customer", None) else None
        contact_instruction = crm_contact_instruction(questionnaire)
        action = task.seller_action or task.reason
        if questionnaire:
            action = f"{contact_instruction}\n\n{action or 'Сверьте запрос клиента и зафиксируйте результат.'}"
        source_payload = dict(task.source_payload or {})
        if questionnaire:
            source_payload["questionnaire_contact_policy"] = {
                "recommended_contact_channel": questionnaire.get("recommended_contact_channel"),
                "contact_channels": questionnaire.get("contact_channels") or [],
                "do_not_contact": questionnaire.get("do_not_contact", False),
                "marketing_consent": questionnaire.get("marketing_consent", False),
            }
        return CrmTaskDto(
            id=str(task.id),
            customer_id=str(task.customer_id),
            customer=await self._serialize_customer(task.customer, use_purchase_history=include_detail) if getattr(task, "customer", None) else None,
            assigned_seller_user_id=str(task.assigned_seller_user_id) if task.assigned_seller_user_id else None,
            assigned_seller_external_id=task.assigned_seller_external_id,
            assigned_seller_name=task.assigned_seller_name,
            store_id=task.store_id,
            store_name=task.store_name,
            work_date=task.work_date,
            due_date=task.due_date,
            priority=task.priority or 3,
            crm_group=task.crm_group,
            reason=task.reason,
            seller_action=action,
            script_key=task.script_key,
            script_text=task.script_text,
            status=task.status,
            seller_outcome=task.seller_outcome,
            seller_comment=task.seller_comment,
            next_action_date=task.next_action_date,
            campaign_id=task.campaign_id,
            campaign_name=task.campaign_name,
            source=task.source or "manual",
            source_row_id=task.source_row_id,
            source_idempotency_key=task.source_idempotency_key,
            source_payload=source_payload,
            last_contacted_at=task.last_contacted_at,
            completed_at=task.completed_at,
            attributed_purchase_count=task.attributed_purchase_count or 0,
            attributed_revenue_kopecks=task.attributed_revenue_kopecks or 0,
            attributed_purchase_ids=[str(x) for x in (task.attributed_purchase_ids or [])],
            attributed_at=task.attributed_at,
            created_at=task.created_at,
            updated_at=task.updated_at,
            events=[self._serialize_event(event) for event in (task.events or [])] if include_detail else [],
            recent_messages=recent_messages,
        )

    async def _serialize_customer(self, user: User, *, use_purchase_history: bool = False) -> CrmCustomerSummary:
        total_purchases = user.total_purchases or 0
        total_spent = user.total_spent or 0
        average_check = user.average_check
        last_purchase_date = user.last_purchase_date

        if use_purchase_history:
            rows = (
                await self.db.execute(
                    select(
                        PurchaseHistory.id,
                        PurchaseHistory.document_id_1c,
                        PurchaseHistory.total_amount,
                        PurchaseHistory.purchase_date,
                    ).where(PurchaseHistory.user_id == user.id)
                )
            ).all()
            if rows:
                document_ids = {
                    str(row.document_id_1c or row.id)
                    for row in rows
                }
                total_purchases = len(document_ids)
                total_spent = sum(int(row.total_amount or 0) for row in rows)
                average_check = int(total_spent / total_purchases) if total_purchases else None
                last_purchase_date = max((row.purchase_date for row in rows if row.purchase_date), default=last_purchase_date)

        questionnaire = questionnaire_from_preferences(user.preferences)
        return CrmCustomerSummary(
            id=str(user.id),
            full_name=user.full_name,
            phone=user.phone,
            city=_safe_customer_city(user.city),
            birth_date=user.birth_date,
            preferred_store_name=user.preferred_store_name,
            secondary_store_name=user.secondary_store_name,
            total_purchases=total_purchases,
            total_spent=total_spent,
            average_check=average_check,
            last_purchase_date=last_purchase_date,
            customer_segment=user.customer_segment,
            loyalty_points=user.loyalty_points or 0,
            questionnaire=questionnaire or {},
            contact_instruction=crm_contact_instruction(questionnaire),
        )

    def _serialize_event(self, event: CrmTaskEvent) -> CrmTaskEventDto:
        return CrmTaskEventDto(
            id=str(event.id),
            event_type=event.event_type,
            actor_user_id=str(event.actor_user_id) if event.actor_user_id else None,
            actor_name=event.actor_name,
            previous_status=event.previous_status,
            next_status=event.next_status,
            payload=event.payload or {},
            created_at=event.created_at,
        )
