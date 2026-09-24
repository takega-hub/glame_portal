"""
API синхронизации покупателей с 1С
"""
import asyncio
import base64
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks, Body, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, Dict, Any
from uuid import UUID

from app.database.connection import get_db, AsyncSessionLocal
from app.api.dependencies import require_admin, require_any_role
from app.models.user import User
from app.models.store import Store
from app.services.onec_sellers_service import OneCSellersService
from app.services.seller_kpi_service import SellerKPIService
from app.services.adaptive_daily_plan_service import AdaptiveDailyPlanService
from app.services.seller_shift_excel_import_service import SellerShiftExcelParser
try:
    from app.services.customer_sync_service import CustomerSyncService  # type: ignore
except Exception:
    CustomerSyncService = None  # type: ignore
from app.services.sync_task_manager import task_manager, TaskStatus
from app.services.crm_interaction_attribution_service import CrmInteractionAttributionService
from app.services.customer_sync_status_service import (
    get_successful_full_customer_sync,
    mark_successful_full_customer_sync,
)
from sync_recent_customer_purchases_from_checks import sync_recent as sync_recent_purchase_receipts

router = APIRouter()
logger = logging.getLogger(__name__)

# 1C register assignments are currently stale for the active retail team.
# This approved GLAME roster takes priority until 1C is corrected.
CURRENT_SELLER_STORES = {
    "eee9caf0-293b-11f1-83c6-fa163e4cc04e": ["CENTRUM"],  # Бешлиева Аджере
    "e0a1b36c-994e-11f1-863d-fa163e4cc04e": ["CENTRUM"],  # Дьяченко Мария
    "6ded351c-4a43-11f1-9b6c-fa163e4cc04e": ["MRIYA", "YALTA"],  # Максимычева Евгения
    "1d5f839e-ba5a-11f0-836e-fa163e4cc04e": ["MRIYA", "YALTA"],  # Рогалевич Ирина
    "4a1f26ca-a92d-11f0-9b8f-fa163e4cc04e": ["MRIYA", "YALTA"],  # Уразгильдеева Екатерина
}

CURRENT_SELLER_STORES_BY_NAME = {
    "бешлиева аджере айдеровна": ["CENTRUM"],
    "дьяченко мария георгиевна": ["CENTRUM"],
    "максимычева евгения александровна": ["MRIYA", "YALTA"],
    "рогалевич ирина евгеньевна": ["MRIYA", "YALTA"],
    "уразгильдеева екатерина ринадовна": ["MRIYA", "YALTA"],
}


def _store_scope_key(value: str | None) -> str:
    normalized = " ".join((value or "").lower().replace("ё", "е").split())
    if "центрум" in normalized or "centrum" in normalized:
        return "centrum"
    if "мрия" in normalized or "mriya" in normalized:
        return "mriya"
    if "ялта" in normalized or "yalta" in normalized:
        return "yalta"
    return normalized


def _person_scope_key(value: str | None) -> str:
    return " ".join((value or "").lower().replace("ё", "е").split())


async def _ensure_manager_can_schedule_seller(payload: Dict[str, Any], current_user: User, db: AsyncSession) -> None:
    """Managers can schedule only roster members of their managed stores."""
    if (current_user.role or "").lower() != "manager":
        return
    allowed_stores = {_store_scope_key(name) for name in await SellerKPIService(db)._managed_store_names(current_user)}
    requested_store = _store_scope_key(payload.get("store_name"))
    if not requested_store or requested_store not in allowed_stores:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нельзя редактировать график другого магазина")
    seller_stores = CURRENT_SELLER_STORES.get(str(payload.get("seller_external_id") or ""))
    if not seller_stores:
        seller_stores = CURRENT_SELLER_STORES_BY_NAME.get(_person_scope_key(payload.get("seller_name")))
    if not seller_stores or requested_store not in {_store_scope_key(name) for name in seller_stores}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нельзя назначать сотрудника из другого магазина")


def _role_label(value: str | None) -> str:
    normalized = (value or "").lower()
    return "Управляющий" if "управ" in normalized or "администратор магазин" in normalized else "Продавец"


async def update_crm_interaction_attribution(db: AsyncSession, user_ids: list[UUID] | None = None) -> Dict[str, Any]:
    try:
        return await CrmInteractionAttributionService(db).update_purchase_conversions(
            user_ids=user_ids,
            commit=True,
        )
    except Exception as exc:
        logger.warning("Не удалось обновить результаты CRM-взаимодействий: %s", exc, exc_info=True)
        return {"error": str(exc)}


@router.get("/sellers")
async def list_onec_sellers(
    limit: int = Query(200, ge=1, le=1000),
    current_user: User = Depends(require_any_role(["admin", "manager"])),
    db: AsyncSession = Depends(get_db),
):
    """Read-only список продавцов с текущим магазином из регистра 1С."""
    async with OneCSellersService() as service:
        result = await service.fetch_sellers(limit=limit)
        try:
            assignments_result = await service.fetch_staff_store_assignments(limit=1000)
        except Exception as exc:
            logger.warning("Не удалось получить назначения сотрудников по магазинам из 1С: %s", exc)
            assignments_result = {"endpoint": None, "assignments": [], "error": str(exc)}
        try:
            positions = await service.fetch_staff_positions(limit=1000)
        except Exception as exc:
            logger.warning("Не удалось получить должности сотрудников из 1С: %s", exc)
            positions = {}

    stores = (await db.execute(select(Store.external_id, Store.name).where(Store.external_id.isnot(None)))).all()
    store_names = {str(external_id): name for external_id, name in stores if external_id}
    assignments = {
        str(item.get("employee_external_id")): item
        for item in assignments_result.get("assignments", [])
        if item.get("employee_external_id")
    }
    for seller in result.get("sellers", []):
        approved_stores = CURRENT_SELLER_STORES.get(str(seller.get("external_id") or ""))
        if approved_stores:
            seller["stores"] = approved_stores
            seller["store"] = " · ".join(approved_stores)
            seller["store_assignment_source"] = "GLAME approved roster"
        assignment = assignments.get(str(seller.get("external_id") or ""))
        if assignment:
            position_id = str(assignment.get("position_external_id") or "")
            seller["position"] = positions.get(position_id) or seller.get("position")
        seller["role_label"] = _role_label(seller.get("position"))
        if approved_stores:
            continue
        if not assignment:
            seller["store_assignment_source"] = "employee_catalog" if seller.get("store") else None
            continue
        store_external_id = str(assignment.get("store_external_id") or "")
        seller["store"] = store_names.get(store_external_id) or seller.get("store") or "Магазин не сопоставлен"
        seller["stores"] = [seller["store"]]
        seller["store_external_id"] = store_external_id
        seller["store_assignment_source"] = "InformationRegister_Сотрудники_RecordType"
        seller["store_assignment_updated_at"] = assignment.get("period")
    if (current_user.role or "").lower() == "manager":
        allowed_store_keys = {_store_scope_key(name) for name in await SellerKPIService(db)._managed_store_names(current_user)}
        result["sellers"] = [
            seller for seller in result.get("sellers", [])
            if allowed_store_keys and any(_store_scope_key(store) in allowed_store_keys for store in (seller.get("stores") or [seller.get("store")]))
        ]
        result["count"] = len(result["sellers"])
    result["store_assignment_source"] = assignments_result.get("endpoint")
    return {"success": True, **result}


@router.get("/sellers/kpi/targets")
async def get_seller_kpi_targets(
    month: Optional[str] = Query(None, description="YYYY-MM"),
    store_name: Optional[str] = Query(None, description="Фильтр по магазину"),
    current_user: User = Depends(require_any_role(["admin", "manager", "seller"])),
    db: AsyncSession = Depends(get_db),
):
    """Таблица целевых KPI-показателей: план вручную, факт из чеков 1С."""
    service = SellerKPIService(db)
    try:
        return {"success": True, **await service.target_indicators(current_user=current_user, month=month, store_name=store_name)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/sellers/kpi/targets")
async def save_seller_kpi_targets(
    payload: Dict[str, Any] = Body(...),
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    """Сохранить плановые значения KPI на месяц. Доступно только администратору."""
    service = SellerKPIService(db)
    try:
        return await service.save_target_plans(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))



@router.get("/sellers/kpi/assortment-guidance")
async def get_seller_kpi_assortment_guidance(
    month: Optional[str] = Query(None, description="YYYY-MM"),
    store_name: Optional[str] = Query(None, description="Фильтр по магазину"),
    seller_personal_plan: Optional[float] = Query(None, description="Личный план продавца для пропорционального ориентира"),
    current_user: User = Depends(require_any_role(["admin", "manager", "seller"])),
    db: AsyncSession = Depends(get_db),
):
    """Мягкий ассортиментный ориентир плана: структура по блокам, остаткам и поступлениям."""
    service = SellerKPIService(db)
    try:
        return {"success": True, **await service.assortment_guidance(current_user=current_user, month=month, store_name=store_name, seller_personal_plan=seller_personal_plan)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/sellers/kpi/assortment-guidance")
async def save_seller_kpi_assortment_guidance(
    payload: Dict[str, Any] = Body(...),
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    """Сохранить мягкий ассортиментный ориентир магазина на месяц. Доступно только администратору."""
    service = SellerKPIService(db)
    try:
        return await service.save_assortment_guidance(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/sellers/plan-months")
async def get_seller_kpi_plan_months(
    limit: int = Query(24, ge=1, le=60),
    _current_user: User = Depends(require_any_role(["admin", "manager"])),
    db: AsyncSession = Depends(get_db),
):
    """История месяцев, по которым в админке заведены планы KPI."""
    service = SellerKPIService(db)
    return {"success": True, **await service.plan_months(limit=limit)}


@router.get("/sellers/kpi/snapshots")
async def get_seller_kpi_snapshots(
    month: Optional[str] = Query(None, description="YYYY-MM"),
    limit: int = Query(90, ge=1, le=366),
    _current_user: User = Depends(require_any_role(["admin", "manager"])),
    db: AsyncSession = Depends(get_db),
):
    """Исторические ежедневные снимки KPI для анализа и планирования будущих месяцев."""
    service = SellerKPIService(db)
    return {"success": True, **await service.snapshot_history(month=month, limit=limit)}


@router.post("/sellers/kpi/history/import")
async def import_seller_kpi_history(
    payload: Dict[str, Any] = Body(...),
    _current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db),
):
    """Загрузить исторические ЕО plan/fact данные в staging/history таблицы."""
    service = SellerKPIService(db)
    try:
        return await service.import_plan_fact_history(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/sellers/kpi/product-diagnostics")
async def get_seller_kpi_product_diagnostics(
    month: Optional[str] = Query(None, description="YYYY-MM"),
    store_name: Optional[str] = Query(None, description="Фильтр по магазину"),
    _current_user: User = Depends(require_any_role(["admin", "manager"])),
    db: AsyncSession = Depends(get_db),
):
    """Диагностика товарных строк, которые попадают/исключаются из KPI изделий."""
    service = SellerKPIService(db)
    return {"success": True, **await service.product_diagnostics(month=month, store_name=store_name)}


@router.get("/sellers/kpi/dashboard")
async def get_sellers_kpi_dashboard(
    month: Optional[str] = Query(None, description="YYYY-MM"),
    preview_user_id: Optional[UUID] = Query(None, description="Аккаунт для админского UI-preview роли"),
    current_user: User = Depends(require_any_role(["admin", "manager"])),
    db: AsyncSession = Depends(get_db),
):
    """Главный управленческий KPI dashboard по всем магазинам и продавцам."""
    service = SellerKPIService(db)
    try:
        scoped_user = current_user
        if preview_user_id and current_user.role == "admin":
            preview_result = await db.execute(select(User).where(User.id == preview_user_id))
            preview_user = preview_result.scalar_one_or_none()
            if preview_user and preview_user.role == "manager":
                scoped_user = preview_user
        return {"success": True, **await service.dashboard(current_user=scoped_user, month=month)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/sellers/kpi")
async def get_sellers_kpi(
    month: Optional[str] = Query(None, description="YYYY-MM"),
    store_name: Optional[str] = Query(None, description="Фильтр по магазину"),
    current_user: User = Depends(require_any_role(["admin", "manager", "seller"])),
    db: AsyncSession = Depends(get_db),
):
    """KPI продавцов: продавец видит себя, admin/manager видят всех."""
    service = SellerKPIService(db)
    try:
        return {"success": True, **await service.kpi_overview(current_user=current_user, month=month, store_name=store_name)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/sellers/kpi/daily-plan")
async def get_adaptive_daily_plan(
    month: Optional[str] = Query(None, description="YYYY-MM"),
    seller_external_id: Optional[str] = Query(None),
    seller_name: Optional[str] = Query(None),
    store_name: Optional[str] = Query(None),
    current_user: User = Depends(require_any_role(["admin", "manager", "seller"])),
    db: AsyncSession = Depends(get_db),
):
    """Explainable adaptive daily plan for a seller's personal KPI."""
    try:
        return {"success": True, **await AdaptiveDailyPlanService(db).calculate(
            current_user, month=month, seller_external_id=seller_external_id,
            seller_name=seller_name, store_name=store_name,
        )}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))



@router.get("/sellers/shifts")
async def get_seller_shifts(
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    store_name: Optional[str] = Query(None, description="Фильтр по магазину"),
    current_user: User = Depends(require_any_role(["admin", "manager", "seller"])),
    db: AsyncSession = Depends(get_db),
):
    """График смен продавцов по магазинам."""
    service = SellerKPIService(db)
    return {"success": True, **await service.shifts(start_date=start_date, end_date=end_date, store_name=store_name, current_user=current_user)}


@router.post("/sellers/shifts/import-excel")
async def import_seller_shifts_from_excel_upload(
    payload: Dict[str, Any] = Body(...),
    _current_user: User = Depends(require_any_role(["admin", "manager"])),
    db: AsyncSession = Depends(get_db),
):
    """Загрузить график смен из Excel-файла ЕО.

    The browser sends file bytes as base64 JSON instead of multipart UploadFile,
    because the lightweight backend environment may not have python-multipart.
    UploadFile is intentionally imported for future multipart migration.
    """
    try:
        content_base64 = payload.get("content_base64") or ""
        if not content_base64:
            raise ValueError("content_base64 обязателен")
        filename = payload.get("filename") or "schedule.xlsx"
        store_name = (payload.get("store_name") or "").strip()
        dry_run = bool(payload.get("dry_run", True))
        replace_existing = bool(payload.get("replace_existing", False))
        parsed = SellerShiftExcelParser().parse_base64(content_base64, store_name=store_name, source_filename=filename)
        service = SellerKPIService(db)
        return await service.import_shift_rows(parsed, dry_run=dry_run, replace_existing=replace_existing)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/sellers/shifts")
async def save_seller_shift(
    payload: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_any_role(["admin", "manager"])),
    db: AsyncSession = Depends(get_db),
):
    """Создать или обновить смену. Доступно только admin/manager."""
    service = SellerKPIService(db)
    try:
        await _ensure_manager_can_schedule_seller(payload, current_user, db)
        return await service.upsert_shift(payload)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/sellers/shifts/{shift_id}")
async def delete_seller_shift(
    shift_id: str,
    _current_user: User = Depends(require_any_role(["admin", "manager"])),
    db: AsyncSession = Depends(get_db),
):
    """Удалить смену. Доступно только admin/manager."""
    service = SellerKPIService(db)
    return await service.delete_shift(shift_id)


async def run_sync_task(task_id: str, task_type: str, params: Dict[str, Any]):
    """Выполнение задачи синхронизации в фоне"""
    import os
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        task_manager.start_task(task_id)
        task_manager.update_progress(task_id, 5, "Подготовка к синхронизации...", 
            "Инициализация сервисов синхронизации")
        
        async with AsyncSessionLocal() as session:
            if CustomerSyncService is None:
                raise RuntimeError("CustomerSyncService недоступен")
            sync_service = CustomerSyncService(session)
            
            stats = {}
            
            if task_type == "full":
                # Синхронизация карт
                limit = params.get("limit", 1000)
                task_manager.update_progress(task_id, 10, "Синхронизация дисконтных карт...", 
                    "Загрузка всех дисконтных карт из 1С")
                def _progress_cb(progress: int, step: str, log: str):
                    task_manager.update_progress(task_id, progress, step, log)

                stats["cards"] = await sync_service.sync_discount_cards(
                    limit=limit,
                    load_all=True,
                    progress_callback=_progress_cb,
                )
                task_manager.update_progress(task_id, 40, "Синхронизация карт завершена", 
                    f"Обработано: {stats['cards'].get('created', 0)} создано, {stats['cards'].get('updated', 0)} обновлено, {stats['cards'].get('total_loaded', 0)} всего")
                
                # Синхронизация начального ввода (миграция из старой системы)
                task_manager.update_progress(task_id, 42, "Синхронизация начального ввода...", 
                    "Загрузка данных переноса из старой системы (Document_ВводНачальныхОстатков)")
                stats["initial_balances"] = await sync_service.sync_initial_balances()
                task_manager.update_progress(task_id, 50, "Синхронизация начального ввода завершена", 
                    f"Обработано: {stats['initial_balances'].get('created', 0)} создано, {stats['initial_balances'].get('skipped', 0)} пропущено")
                
                # Синхронизация покупок
                days = params.get("days", 365)
                task_manager.update_progress(task_id, 55, "Синхронизация истории покупок по чекам...",
                    f"Загрузка точных чеков Document_ЧекККМ за {days} дней")
                stats["purchases"] = await sync_recent_purchase_receipts(
                    days=days,
                    create_missing=True,
                    dry_run=False,
                )
                stats["crm_interaction_attribution"] = await update_crm_interaction_attribution(session)
                task_manager.update_progress(task_id, 85, "Синхронизация покупок завершена", 
                    f"Чеков: {stats['purchases'].get('fetched', 0)}, создано: {stats['purchases'].get('created', 0)}, обновлено: {stats['purchases'].get('updated', 0)}, покупателей: {stats['purchases'].get('touched_users', 0)}, непривязано: {stats['purchases'].get('unresolved', 0)}")
                
                # Синхронизация бонусов
                if os.getenv("ONEC_LOYALTY_ENABLED", "true").lower() in {"1", "true", "yes", "y", "on"}:
                    task_manager.update_progress(task_id, 90, "Синхронизация бонусов...", 
                        "Обновление балансов бонусных баллов")
                    stats["loyalty"] = await sync_service.sync_loyalty_points()
                    task_manager.update_progress(task_id, 98, "Синхронизация бонусов завершена", 
                        f"Обновлено: {stats['loyalty'].get('updated', 0)} покупателей")
                else:
                    stats["loyalty"] = {"skipped": True, "message": "Loyalty sync disabled"}
                    task_manager.update_progress(task_id, 98, "Синхронизация бонусов пропущена", 
                        "Синхронизация бонусов отключена в настройках")

                try:
                    stats["full_sync_status"] = await mark_successful_full_customer_sync(
                        session,
                        source="admin_full_sync",
                        task_id=task_id,
                        stats=stats,
                        commit=True,
                    )
                except Exception as exc:
                    await session.rollback()
                    logger.warning(
                        "Не удалось сохранить время успешной полной синхронизации: %s",
                        exc,
                        exc_info=True,
                    )
            
            task_manager.update_progress(task_id, 100, "Синхронизация завершена", 
                "Все данные успешно синхронизированы")
            task_manager.complete_task(task_id, {
                "success": True,
                "message": "Синхронизация завершена",
                "stats": stats
            })
            
    except Exception as e:
        import traceback
        error_msg = str(e)
        logger.error(f"Ошибка в задаче синхронизации {task_id}: {error_msg}\n{traceback.format_exc()}")
        task_manager.fail_task(task_id, error_msg)


@router.post("/sync/full")
async def sync_full(
    limit: int = Query(1000, ge=1, le=10000),
    days: int = Query(365, ge=1, le=3650),
    current_user: User = Depends(require_admin()),
    background_tasks: BackgroundTasks = None
):
    """Полная синхронизация: карты + покупки + бонусы (запускается в фоне)"""
    if CustomerSyncService is None:
        raise HTTPException(status_code=503, detail="Сервис синхронизации недоступен")
    # Создаем задачу
    task_id = task_manager.create_task("full", {
        "limit": limit,
        "days": days
    })
    
    # Запускаем в фоне
    asyncio.create_task(run_sync_task(task_id, "full", {
        "limit": limit,
        "days": days
    }))
    
    return {
        "success": True,
        "message": "Синхронизация запущена в фоне",
        "task_id": task_id,
        "status_url": f"/api/admin/1c/sync/task/{task_id}"
    }
@router.post("/sync/customers")
async def sync_customers(
    limit: int = Query(1000, ge=1, le=10000),
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db)
):
    """Запуск синхронизации покупателей (только карты)"""
    if CustomerSyncService is None:
        raise HTTPException(status_code=503, detail="Сервис синхронизации недоступен")
    sync_service = CustomerSyncService(db)
    stats = await sync_service.sync_discount_cards(limit=limit)
    
    return {
        "success": True,
        "message": "Синхронизация покупателей завершена",
        "stats": stats
    }


@router.post("/sync/purchases")
async def sync_purchases(
    user_id: Optional[str] = Query(None),
    days: int = Query(365, ge=1, le=3650),
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db)
):
    """Синхронизация истории покупок"""
    if CustomerSyncService is None:
        raise HTTPException(status_code=503, detail="Сервис синхронизации недоступен")
    
    uid = None
    if user_id:
        try:
            uid = UUID(user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Неверный формат user_id")

    if uid:
        sync_service = CustomerSyncService(db)
        stats = await sync_service.sync_purchase_history(user_id=uid, days=days)
        attribution_stats = stats.get("crm_interaction_attribution", {})
    else:
        stats = await sync_recent_purchase_receipts(
            days=days,
            create_missing=True,
            dry_run=False,
        )
        attribution_stats = await update_crm_interaction_attribution(db)
    
    return {
        "success": True,
        "message": "Синхронизация истории покупок завершена",
        "stats": {
            **stats,
            "crm_interaction_attribution": attribution_stats,
        }
    }


@router.get("/sync/task/{task_id}")
async def get_sync_task_status(
    task_id: str,
):
    """Получение статуса задачи синхронизации"""
    task = task_manager.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    
    return {
        "task_id": task["id"],
        "type": task["type"],
        "status": task["status"],
        "progress": task["progress"],
        "current_step": task["current_step"],
        "logs": task["logs"][-20:],  # Последние 20 логов
        "result": task.get("result"),
        "error": task.get("error"),
        "created_at": task["created_at"].isoformat() if task["created_at"] else None,
        "started_at": task["started_at"].isoformat() if task["started_at"] else None,
        "completed_at": task["completed_at"].isoformat() if task["completed_at"] else None,
    }


@router.get("/sync/status")
async def get_sync_status(
    current_user: User = Depends(require_admin()),
    db: AsyncSession = Depends(get_db)
):
    """Статус синхронизации покупателей"""
    from sqlalchemy import select, func
    from datetime import datetime, timedelta
    
    # Статистика покупателей
    is_customer_col = User.__table__.columns.get("is_customer")
    if is_customer_col is None:
        from sqlalchemy import literal_column
        is_customer_col = literal_column("is_customer")
    
    synced_at_col = User.__table__.columns.get("synced_at")
    
    stmt = select(
        func.count(User.id).label("total_customers"),
    ).where(is_customer_col == True)
    result = await db.execute(stmt)
    row = result.first()
    
    total_customers = row.total_customers or 0
    
    # Последняя синхронизация
    # SQLAlchemy Column objects cannot be used in Python boolean context:
    # `if synced_at_col:` raises "Boolean value of this clause is not defined".
    if synced_at_col is not None:
        stmt = select(func.max(synced_at_col)).where(is_customer_col == True)
        result = await db.execute(stmt)
        last_sync = result.scalar()
    else:
        last_sync = None

    full_sync = await get_successful_full_customer_sync(db)
    
    # Активные задачи синхронизации
    active_tasks = [
        task for task in task_manager.tasks.values()
        if task["status"] == TaskStatus.RUNNING
    ]
    
    return {
        "total_customers": total_customers,
        "last_sync": last_sync.isoformat() if last_sync else None,
        "last_successful_full_sync": full_sync,
        "active_tasks": len(active_tasks),
        "errors": []
    }


@router.post("/update-segments")
async def update_customer_segments(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin()),
):
    """
    Обновление сегментов для всех покупателей.
    """
    task_id = task_manager.create_task("update_segments", {})
    
    async def run_update_segments_task(task_id: str):
        """Обновление сегментов в фоне"""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            task_manager.start_task(task_id)
            task_manager.update_progress(task_id, 5, "Загрузка списка покупателей...", 
                "Получение данных из БД")
            
            async with AsyncSessionLocal() as session:
                sync_service = CustomerSyncService(session)
                
                # Получаем всех покупателей с нужными полями
                stmt = select(
                    User.id,
                    User.full_name,
                    User.phone
                ).where(User.is_customer == True)
                result = await session.execute(stmt)
                users = result.all()
                
                total = len(users)
                task_manager.update_progress(task_id, 10, f"Найдено покупателей: {total}", 
                    "Начинаем обновление сегментов")
                
                updated_count = 0
                skipped_count = 0
                error_count = 0
                
                for i, user_row in enumerate(users, 1):
                    try:
                        user_id = user_row.id
                        user_name = user_row.full_name or user_row.phone or "Без имени"
                        
                        # Обновляем сегмент
                        segment = await sync_service.update_customer_segment(user_id)
                        
                        if segment:
                            updated_count += 1
                            progress = 10 + int((i / total) * 80)
                            task_manager.update_progress(
                                task_id, progress, 
                                f"Обработано {i}/{total}",
                                f"✓ {user_name}: {segment}"
                            )
                        else:
                            skipped_count += 1
                        
                    except Exception as e:
                        error_count += 1
                        logger.error(f"Ошибка обновления сегмента для {user_id}: {e}")
                        task_manager.update_progress(
                            task_id, 10 + int((i / total) * 80),
                            f"Обработано {i}/{total}",
                            f"✗ {user_name}: ошибка"
                        )
                        continue
                
                task_manager.complete_task(
                    task_id,
                    {
                        "total": total,
                        "updated": updated_count,
                        "skipped": skipped_count,
                        "errors": error_count
                    }
                )
                task_manager.update_progress(task_id, 100, "Обновление завершено", 
                    f"Обновлено: {updated_count}, Пропущено: {skipped_count}, Ошибок: {error_count}")
                
        except Exception as e:
            logger.error(f"Критическая ошибка при обновлении сегментов: {e}")
            task_manager.fail_task(task_id, str(e))
    
    # Запускаем задачу в фоне
    asyncio.create_task(run_update_segments_task(task_id))
    
    return {
        "task_id": task_id,
        "status": "started",
        "message": "Обновление сегментов запущено"
    }
