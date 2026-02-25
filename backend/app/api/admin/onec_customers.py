"""
API синхронизации покупателей с 1С
"""
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, Dict, Any
from uuid import UUID

from app.database.connection import get_db, AsyncSessionLocal
from app.api.dependencies import require_admin
from app.models.user import User
from app.services.customer_sync_service import CustomerSyncService
from app.services.sync_task_manager import task_manager, TaskStatus

router = APIRouter()


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
            sync_service = CustomerSyncService(session)
            
            stats = {}
            
            if task_type == "full":
                # Синхронизация карт
                limit = params.get("limit", 1000)
                task_manager.update_progress(task_id, 10, "Синхронизация дисконтных карт...", 
                    f"Загрузка до {limit} карт из 1С")
                def _progress_cb(progress: int, step: str, log: str):
                    task_manager.update_progress(task_id, progress, step, log)

                stats["cards"] = await sync_service.sync_discount_cards(
                    limit=limit,
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
                task_manager.update_progress(task_id, 55, "Синхронизация истории покупок...", 
                    f"Загрузка покупок за {days} дней. Это может занять несколько минут...")
                stats["purchases"] = await sync_service.sync_purchase_history(days=days)
                task_manager.update_progress(task_id, 85, "Синхронизация покупок завершена", 
                    f"Обработано: {stats['purchases'].get('created', 0)} создано, {stats['purchases'].get('updated', 0)} обновлено")
                
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
    sync_service = CustomerSyncService(db)
    
    uid = None
    if user_id:
        try:
            uid = UUID(user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Неверный формат user_id")
    
    stats = await sync_service.sync_purchase_history(user_id=uid, days=days)
    
    return {
        "success": True,
        "message": "Синхронизация истории покупок завершена",
        "stats": stats
    }


@router.get("/sync/task/{task_id}")
async def get_sync_task_status(
    task_id: str,
    current_user: User = Depends(require_admin())
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
    if synced_at_col:
        stmt = select(func.max(synced_at_col)).where(is_customer_col == True)
        result = await db.execute(stmt)
        last_sync = result.scalar()
    else:
        last_sync = None
    
    # Активные задачи синхронизации
    active_tasks = [
        task for task in task_manager.tasks.values()
        if task["status"] == TaskStatus.RUNNING
    ]
    
    return {
        "total_customers": total_customers,
        "last_sync": last_sync.isoformat() if last_sync else None,
        "active_tasks": len(active_tasks),
        "errors": []
    }


@router.post("/update-segments")
async def update_customer_segments(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
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
