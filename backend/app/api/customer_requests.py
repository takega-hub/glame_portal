from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database.connection import get_db
from app.models.customer_request import CustomerRequest, CustomerRequestAudit
from app.models.crm_service_case import CrmServiceCase
from app.models.crm_task import CrmTask, CrmTaskEvent
from app.models.gift_certificate import GiftCertificate
from app.models.product import Product
from app.models.product_stock import ProductStock
from app.models.user import User
from app.services.gift_certificate_service import GiftCertificateService
from app.services.upload_security import validate_image_upload

router = APIRouter()

CUSTOMER_REQUEST_PHOTO_ROOT = Path(__file__).resolve().parents[2] / "uploads" / "customer_requests"
CUSTOMER_REQUEST_PHOTO_MAX_FILES = 5

STORE_MAP = {"CENTRUM": "CENTRUM", "MEGANOM": "CENTRUM", "YALTA": "YALTA", "MRIYA": "YALTA"}
CLOSED_STORE_ALIASES = {"MEGANOM": "CENTRUM"}
OPEN_STATUSES = {"WAITING", "ORDERED", "ARRIVED_STORE", "IN_PROGRESS", "NEW", "UNDER_REVIEW", "DECISION_READY", "IN_REPAIR", "READY", "CUSTOMER_NOTIFIED"}
SERVICE_TYPES = {"REPAIR_CUSTOMER", "RETURN", "EXCHANGE", "SERVICE_CLAIM"}
DEFAULT_STATUS = {"WAITING_ITEM": "WAITING", "WAITING_SIZE": "WAITING", "WAITING_BRAND": "WAITING", "CUSTOM_ORDER": "ORDERED", "REPAIR_CUSTOMER": "NEW", "REPAIR_STORE_STOCK": "NEW", "EXCHANGE": "NEW", "RETURN": "NEW", "SERVICE_CLAIM": "NEW"}
ALLOWED_STATUSES = {
    "WAITING_ITEM": {"WAITING", "ORDERED", "ARRIVED_STORE", "IN_PROGRESS", "REFUSED", "PURCHASED"},
    "WAITING_SIZE": {"WAITING", "ORDERED", "ARRIVED_STORE", "IN_PROGRESS", "REFUSED", "PURCHASED"},
    "WAITING_BRAND": {"WAITING", "ORDERED", "ARRIVED_STORE", "IN_PROGRESS", "REFUSED", "PURCHASED"},
    "CUSTOM_ORDER": {"WAITING", "ORDERED", "ARRIVED_STORE", "IN_PROGRESS", "REFUSED", "PURCHASED"},
    "EXCHANGE": {"NEW", "IN_PROGRESS", "UNDER_REVIEW", "DECISION_READY", "COMPLETED"},
    "RETURN": {"NEW", "IN_PROGRESS", "UNDER_REVIEW", "DECISION_READY", "COMPLETED"},
    "SERVICE_CLAIM": {"NEW", "IN_PROGRESS", "UNDER_REVIEW", "DECISION_READY", "COMPLETED"},
    "REPAIR_CUSTOMER": {"NEW", "IN_PROGRESS", "IN_REPAIR", "READY", "CUSTOMER_NOTIFIED", "DELIVERED_CLOSED"},
    "REPAIR_STORE_STOCK": {"NEW", "IN_PROGRESS", "IN_REPAIR", "READY", "DELIVERED_CLOSED"},
}


class RequestPayload(BaseModel):
    client_id: UUID | None = None
    request_type: str
    physical_store: str | None = None
    assigned_consultant_id: UUID | None = None
    status: str | None = None
    priority: str = "normal"
    product_name: str | None = None
    sku: str | None = None
    size: str | None = None
    brand: str | None = None
    original_comment: str | None = None
    structured_context: dict[str, Any] = Field(default_factory=dict)
    next_action: str | None = None
    next_action_at: datetime | None = None


class StatusPayload(BaseModel):
    status: str
    comment: str | None = None
    next_action: str | None = None
    next_action_at: datetime | None = None


class RequestUpdatePayload(BaseModel):
    assigned_consultant_id: UUID | None = None
    physical_store: str | None = None
    priority: str | None = None
    product_name: str | None = None
    sku: str | None = None
    size: str | None = None
    brand: str | None = None
    original_comment: str | None = None
    structured_context: dict[str, Any] | None = None
    next_action: str | None = None
    next_action_at: datetime | None = None


class CompensationCertificatePayload(BaseModel):
    amount_rub: int = Field(gt=0, le=100_000, description="Номинал сертификата в рублях")
    expires_in_days: int = Field(default=30, ge=1, le=365)
    comment: str | None = Field(default=None, max_length=500)


def serialize(row: CustomerRequest) -> dict[str, Any]:
    return {
        "id": str(row.id), "client_id": str(row.client_id) if row.client_id else None,
        "request_type": row.request_type, "physical_store": row.physical_store, "crm_store": row.crm_store,
        "assigned_consultant_id": str(row.assigned_consultant_id) if row.assigned_consultant_id else None,
        "status": row.status, "priority": row.priority, "product_name": row.product_name, "sku": row.sku,
        "size": row.size, "brand": row.brand, "original_comment": row.original_comment,
        "photo_urls": row.photo_urls or [],
        "structured_context": row.structured_context or {}, "next_action": row.next_action,
        "next_action_at": row.next_action_at, "closed_at": row.closed_at, "created_at": row.created_at,
    }


async def add_audit(db: AsyncSession, row: CustomerRequest, actor: User | None, action: str, old: str | None = None, comment: str | None = None):
    db.add(CustomerRequestAudit(request_id=row.id, actor_id=getattr(actor, "id", None), action=action, old_status=old, new_status=row.status, comment=comment))


async def ensure_operational_task(db: AsyncSession, row: CustomerRequest, actor: User | None, trigger: str) -> bool:
    """Create one concise seller task per meaningful request event, never a duplicate."""
    if not row.client_id or row.request_type == "REPAIR_STORE_STOCK":
        return False
    key = f"customer_request:{row.id}:{trigger}:{row.status}"
    if await db.scalar(select(CrmTask.id).where(CrmTask.source_idempotency_key == key)):
        return False
    title = {"ARRIVED_STORE": "Размер или изделие поступило — связаться с клиентом сегодня.", "READY": "Изделие готово — сообщить клиенту о готовности к выдаче.", "NEW": "Подтвердить приём обращения и уточнить следующий шаг.", "DUE_SOON": "Проверить обещанный срок и получить фактический статус."}.get(row.status, row.next_action or "Проверить обращение и выполнить следующий шаг.")
    task = CrmTask(customer_id=row.client_id, assigned_seller_user_id=row.assigned_consultant_id, store_name=row.crm_store, work_date=date.today(), due_date=datetime.combine(date.today(), time(20), tzinfo=timezone.utc), priority=1 if row.request_type in SERVICE_TYPES else 2, crm_group="service_request", reason=f"{row.request_type}: {row.product_name or row.sku or 'изделие'}", seller_action=title, script_text=None, status="new", source="customer_request", source_row_id=str(row.id), source_idempotency_key=key, source_payload={"request_id": str(row.id), "request_type": row.request_type, "trigger": trigger, "original_comment": row.original_comment}, created_by_user_id=getattr(actor, "id", None))
    db.add(task); await db.flush()
    db.add(CrmTaskEvent(task_id=task.id, event_type="created_from_customer_request", actor_user_id=getattr(actor, "id", None), previous_status=None, next_status="new", payload={"request_id": str(row.id), "trigger": trigger}))
    return True


async def sync_service_block(db: AsyncSession, row: CustomerRequest):
    if not row.client_id or row.request_type not in SERVICE_TYPES:
        return
    result = await db.execute(select(CrmServiceCase).where(CrmServiceCase.customer_id == row.client_id, CrmServiceCase.source_payload["customer_request_id"].astext == str(row.id)))
    case = result.scalar_one_or_none()
    is_open = row.status in OPEN_STATUSES
    if is_open and not case:
        db.add(CrmServiceCase(customer_id=row.client_id, status="open", case_type=row.request_type, title=row.product_name or row.request_type, description=row.original_comment, source="customer_request", source_payload={"customer_request_id": str(row.id)}))
    elif case:
        case.status = "open" if is_open else "closed"; case.closed_at = None if is_open else datetime.now(timezone.utc)


async def run_due_control(db: AsyncSession, actor: User | None = None) -> dict[str, int]:
    rows = (await db.execute(select(CustomerRequest).where(CustomerRequest.status.in_(OPEN_STATUSES)))).scalars().all()
    created = 0; arrivals = 0; now = datetime.now(timezone.utc)
    for row in rows:
        promised = row.next_action_at or (row.structured_context or {}).get("expected_date")
        if isinstance(promised, str):
            try: promised = datetime.fromisoformat(promised.replace("Z", "+00:00"))
            except ValueError: promised = None
        if promised and getattr(promised, "tzinfo", None) is None: promised = promised.replace(tzinfo=timezone.utc)
        if promised and promised <= now + timedelta(days=2):
            row.next_action = row.next_action or "Уточнить фактический статус до обращения клиента."
            if await ensure_operational_task(db, row, actor, "due_soon"):
                created += 1; await add_audit(db, row, actor, "control_task_created", comment="Срок обращения требует контроля")
        # Exact SKU matching is deterministic. Text/colour matching deliberately remains a manual review.
        if row.status in {"WAITING", "ORDERED"} and row.sku:
            stock = await db.scalar(
                select(ProductStock.id).join(Product, Product.id == ProductStock.product_id).where(
                    ProductStock.available_quantity > 0,
                    or_(Product.article == row.sku, Product.external_code == row.sku, Product.vendor_code == row.sku),
                ).limit(1)
            )
            if stock:
                old = row.status; row.status = "ARRIVED_STORE"; row.next_action = "Связаться с клиентом сегодня: ожидаемое изделие или размер поступили."
                await add_audit(db, row, actor, "stock_matched", old, "Точное совпадение SKU с доступным остатком")
                if await ensure_operational_task(db, row, actor, "stock_received"):
                    created += 1
                arrivals += 1
    await db.commit()
    return {"checked": len(rows), "tasks_created": created, "arrivals_matched": arrivals}


@router.get("")
async def list_requests(status: str | None = None, request_type: str | None = None, limit: int = Query(100, ge=1, le=300), db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    query = select(CustomerRequest).order_by(CustomerRequest.next_action_at.asc().nullslast(), CustomerRequest.created_at.desc()).limit(limit)
    if status: query = query.where(CustomerRequest.status == status)
    if request_type: query = query.where(CustomerRequest.request_type == request_type)
    return {"items": [serialize(row) for row in (await db.execute(query)).scalars().all()]}


@router.get("/clients")
async def search_clients(q: str = Query("", min_length=2), db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    pattern = f"%{q.strip()}%"
    rows = (await db.execute(select(User).where(User.is_customer.is_(True), or_(User.full_name.ilike(pattern), User.phone.ilike(pattern))).order_by(User.full_name).limit(20))).scalars().all()
    return {"items": [{"id": str(x.id), "name": x.full_name or x.phone or "Без имени", "phone": x.phone, "city": x.city} for x in rows]}


@router.get("/summary")
async def summary(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    result = await db.execute(select(CustomerRequest.request_type, func.count(CustomerRequest.id)).where(CustomerRequest.status.in_(OPEN_STATUSES)).group_by(CustomerRequest.request_type))
    by_type = {key: count for key, count in result.all()}
    overdue = await db.scalar(select(func.count(CustomerRequest.id)).where(CustomerRequest.status.in_(OPEN_STATUSES), CustomerRequest.next_action_at < datetime.now(timezone.utc)))
    return {"open": sum(by_type.values()), "overdue": overdue or 0, "by_type": by_type}


@router.get("/analytics")
async def analytics(db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    rows = (await db.execute(select(CustomerRequest))).scalars().all()
    open_rows = [x for x in rows if x.status in OPEN_STATUSES]
    completed = [x for x in rows if x.closed_at]
    quality: dict[tuple[str, str], int] = {}
    for row in rows:
        if row.request_type not in SERVICE_TYPES: continue
        reason = str((row.structured_context or {}).get("reason") or row.original_comment or "не указана").strip().lower()[:100]
        key = (row.sku or row.brand or "без SKU", reason)
        quality[key] = quality.get(key, 0) + 1
    alerts = [{"sku_or_brand": key[0], "reason": key[1], "count": count} for key, count in quality.items() if count >= 3]
    return {"open": len(open_rows), "completed": len(completed), "by_type": {key: sum(1 for x in rows if x.request_type == key) for key in DEFAULT_STATUS}, "quality_alerts": sorted(alerts, key=lambda x: x["count"], reverse=True)}


@router.post("")
async def create_request(payload: RequestPayload, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    kind = payload.request_type.upper()
    if kind not in DEFAULT_STATUS: raise HTTPException(422, "Неизвестный тип обращения")
    physical = (payload.physical_store or "").upper() or None
    physical = CLOSED_STORE_ALIASES.get(physical, physical)
    values = payload.model_dump()
    if not values.get("assigned_consultant_id") and (current_user.role or "").lower() in {"seller", "manager"}:
        values["assigned_consultant_id"] = current_user.id
    values.update(request_type=kind, physical_store=physical, crm_store=STORE_MAP.get(physical), status=payload.status or DEFAULT_STATUS[kind])
    row = CustomerRequest(**values)
    db.add(row); await db.flush()
    await add_audit(db, row, current_user, "created", comment=payload.original_comment)
    await sync_service_block(db, row)
    if row.request_type in SERVICE_TYPES:
        await ensure_operational_task(db, row, current_user, "created")
    await db.commit(); await db.refresh(row)
    return serialize(row)


@router.patch("/{request_id}/status")
async def update_status(request_id: UUID, payload: StatusPayload, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    row = await db.get(CustomerRequest, request_id)
    if not row: raise HTTPException(404, "Обращение не найдено")
    next_status = payload.status.upper()
    if next_status not in ALLOWED_STATUSES.get(row.request_type, set()):
        raise HTTPException(422, "Этот статус недоступен для выбранного типа обращения")
    old = row.status; row.status = next_status; row.next_action = payload.next_action or row.next_action; row.next_action_at = payload.next_action_at
    if row.status in {"PURCHASED", "REFUSED", "COMPLETED", "DELIVERED_CLOSED", "RETURN_COMPLETED", "EXCHANGE_COMPLETED"}: row.closed_at = datetime.now(timezone.utc)
    await add_audit(db, row, current_user, "status_changed", old, payload.comment)
    await sync_service_block(db, row)
    if row.status in {"ARRIVED_STORE", "READY", "NEW"}:
        await ensure_operational_task(db, row, current_user, "status_changed")
    await db.commit(); await db.refresh(row)
    return serialize(row)


@router.patch("/{request_id}")
async def update_request(request_id: UUID, payload: RequestUpdatePayload, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    row = await db.get(CustomerRequest, request_id)
    if not row: raise HTTPException(404, "Обращение не найдено")
    changes = payload.model_dump(exclude_unset=True)
    # Product/requisition attributes are business-critical. Only an
    # administrator can correct them after the request has been created;
    # consultants may still maintain the customer comment and next action.
    if (current_user.role or "").lower() != "admin":
        for field in {"assigned_consultant_id", "physical_store", "product_name", "sku", "size", "brand"}:
            changes.pop(field, None)
    if "physical_store" in changes:
        physical = (changes["physical_store"] or "").upper() or None
        physical = CLOSED_STORE_ALIASES.get(physical, physical)
        row.physical_store = physical; row.crm_store = STORE_MAP.get(physical)
        changes.pop("physical_store")
    for field, value in changes.items():
        setattr(row, field, value)
    await add_audit(db, row, current_user, "updated", comment="Обновлены данные обращения")
    await db.commit(); await db.refresh(row)
    return serialize(row)


@router.post("/{request_id}/compensation-certificate")
async def issue_compensation_certificate(
    request_id: UUID,
    payload: CompensationCertificatePayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Issue a compensation certificate and create a seller notification task.

    This endpoint deliberately does not send email/SMS. The assigned seller
    receives a CRM task and records the actual client notification separately.
    """
    if (current_user.role or "").lower() != "admin":
        raise HTTPException(status_code=403, detail="Выпуск компенсационного сертификата доступен только администратору")
    request = await db.get(CustomerRequest, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Обращение не найдено")
    if not request.client_id:
        raise HTTPException(status_code=422, detail="Для выпуска сертификата у обращения должен быть указан клиент")
    customer = await db.get(User, request.client_id)
    if not customer:
        raise HTTPException(status_code=422, detail="Клиент обращения не найден")

    existing = (await db.execute(
        select(GiftCertificate).where(
            GiftCertificate.recipient_user_id == customer.id,
            GiftCertificate.meta["customer_request_id"].as_string() == str(request.id),
            GiftCertificate.meta["compensation_certificate"].as_boolean().is_(True),
        ).order_by(GiftCertificate.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"Для этого обращения уже выпущен сертификат {existing.number}")

    amount_kopecks = payload.amount_rub * 100
    source_key = f"customer_request_compensation:{request.id}"
    certificate, pin, created = await GiftCertificateService(db).create_program_certificate(
        recipient_user_id=customer.id,
        nominal_amount=amount_kopecks,
        source="customer_request_compensation",
        source_idempotency_key=source_key,
        recipient_name=customer.full_name,
        recipient_phone=customer.phone,
        recipient_email=customer.email,
        message=payload.comment or "Компенсационный электронный сертификат GLAME",
        expires_in_days=payload.expires_in_days,
        buyer_user_id=current_user.id,
        meta={
            "compensation_certificate": True,
            "customer_request_id": str(request.id),
            "issued_by_user_id": str(current_user.id),
            "notification_required": True,
            "auto_send": False,
        },
    )
    task_key = f"customer_request_certificate_notification:{certificate.id}"
    task = await db.scalar(select(CrmTask).where(CrmTask.source_idempotency_key == task_key))
    if not task:
        task = CrmTask(
            customer_id=customer.id,
            assigned_seller_user_id=request.assigned_consultant_id,
            store_name=request.physical_store,
            work_date=date.today(),
            due_date=datetime.combine(date.today(), time(20), tzinfo=timezone.utc),
            priority=1,
            crm_group="service_request",
            reason="Компенсация по обращению клиента",
            seller_action=f"Уведомить клиента о выпуске электронного сертификата {certificate.number} на {payload.amount_rub:,} ₽.",
            script_key="customer_request_compensation_certificate",
            script_text="Сообщите клиенту о компенсационном сертификате, его номере, номинале и сроке действия. Факт отправки/звонка зафиксируйте в результате задачи.",
            status="new",
            source="customer_request_certificate",
            source_row_id=str(request.id),
            source_idempotency_key=task_key,
            source_payload={
                "customer_request_id": str(request.id),
                "certificate_id": str(certificate.id),
                "certificate_number": certificate.number,
                "amount_rub": payload.amount_rub,
                "expires_at": certificate.expires_at.isoformat() if certificate.expires_at else None,
                "notification_required": True,
                "auto_send": False,
            },
            created_by_user_id=current_user.id,
        )
        db.add(task)
        await db.flush()
        db.add(CrmTaskEvent(
            task_id=task.id,
            event_type="created_from_compensation_certificate",
            actor_user_id=current_user.id,
            previous_status=None,
            next_status="new",
            payload={"certificate_number": certificate.number, "amount_rub": payload.amount_rub},
        ))
    if created:
        await add_audit(
            db, request, current_user, "compensation_certificate_issued",
            comment=f"Выпущен электронный сертификат {certificate.number} на {payload.amount_rub:,} ₽; создана задача уведомить клиента",
        )
    await db.commit()
    return {
        "certificate": {
            "id": str(certificate.id), "number": certificate.number, "pin": pin,
            "amount_rub": payload.amount_rub, "status": certificate.status,
            "expires_at": certificate.expires_at,
        },
        "crm_task_id": str(task.id), "created": created, "auto_sent": False,
    }


@router.post("/{request_id}/photos")
async def upload_request_photos(
    request_id: UUID,
    files: list[UploadFile] = File(..., description="Фотографии обращения в JPEG, PNG или WebP"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Attach customer-provided product photos to an existing request."""
    row = await db.get(CustomerRequest, request_id)
    if not row:
        raise HTTPException(404, "Обращение не найдено")
    existing = list(row.photo_urls or [])
    if not files:
        raise HTTPException(422, "Выберите хотя бы одну фотографию")
    if len(existing) + len(files) > CUSTOMER_REQUEST_PHOTO_MAX_FILES:
        raise HTTPException(422, f"К обращению можно прикрепить не более {CUSTOMER_REQUEST_PHOTO_MAX_FILES} фотографий")

    folder = CUSTOMER_REQUEST_PHOTO_ROOT / str(row.id)
    folder.mkdir(parents=True, exist_ok=True)
    suffixes = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    uploaded: list[str] = []
    for file in files:
        content = await file.read()
        content_type = validate_image_upload(content, file.content_type)
        filename = f"{uuid4().hex}{suffixes[content_type]}"
        (folder / filename).write_bytes(content)
        uploaded.append(f"/uploads/customer_requests/{row.id}/{filename}")

    row.photo_urls = existing + uploaded
    await add_audit(db, row, current_user, "photos_attached", comment=f"Прикреплено фотографий: {len(uploaded)}")
    await db.commit()
    await db.refresh(row)
    return serialize(row)


@router.post("/control/run")
async def run_daily_control(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Deterministic daily safety net for cases whose promised date is near or overdue."""
    return await run_due_control(db, current_user)


@router.get("/{request_id}")
async def get_request(request_id: UUID, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    row = await db.get(CustomerRequest, request_id)
    if not row: raise HTTPException(404, "Обращение не найдено")
    audits = (await db.execute(select(CustomerRequestAudit).where(CustomerRequestAudit.request_id == row.id).order_by(CustomerRequestAudit.created_at.desc()))).scalars().all()
    return {**serialize(row), "audit": [{"id": str(x.id), "action": x.action, "old_status": x.old_status, "new_status": x.new_status, "comment": x.comment, "created_at": x.created_at} for x in audits]}
