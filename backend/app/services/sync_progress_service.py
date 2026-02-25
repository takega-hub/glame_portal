"""
Сервис для отслеживания прогресса синхронизации товаров
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class SyncProgressService:
    """Сервис для отслеживания прогресса синхронизации"""
    
    _instance: Optional['SyncProgressService'] = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._tasks: Dict[str, Dict] = {}
    
    async def create_task(
        self,
        task_type: str = "products",
        total: int = 0,
        description: str = "Синхронизация товаров"
    ) -> str:
        """Создать новую задачу синхронизации"""
        async with self._lock:
            task_id = str(uuid4())
            self._tasks[task_id] = {
                "task_id": task_id,
                "task_type": task_type,
                "status": "running",  # running, completed, failed, cancelled
                "progress": 0,
                "total": total,
                "current": 0,
                "description": description,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "completed_at": None,
                "error": None,
                "result": None,
                "stage": "initializing",  # initializing, fetching, processing, saving, completed
                "stage_description": "Инициализация...",
            }
            logger.info(f"Создана задача синхронизации: {task_id} ({task_type})")
            return task_id
    
    async def update_progress(
        self,
        task_id: str,
        current: Optional[int] = None,
        total: Optional[int] = None,
        progress: Optional[float] = None,
        stage: Optional[str] = None,
        stage_description: Optional[str] = None,
    ):
        """Обновить прогресс задачи"""
        async with self._lock:
            if task_id not in self._tasks:
                logger.warning(f"Задача {task_id} не найдена")
                return
            
            task = self._tasks[task_id]
            
            if current is not None:
                task["current"] = current
            if total is not None:
                task["total"] = total
            if progress is not None:
                task["progress"] = min(100.0, max(0.0, progress))
            elif task["total"] > 0:
                task["progress"] = min(100.0, (task["current"] / task["total"]) * 100.0)
            
            if stage:
                task["stage"] = stage
            if stage_description:
                task["stage_description"] = stage_description
            
            logger.debug(f"Прогресс задачи {task_id}: {task['current']}/{task['total']} ({task['progress']:.1f}%) - {task['stage_description']}")
    
    async def update_task(
        self,
        task_id: str,
        status: Optional[str] = None,
        current: Optional[int] = None,
        total: Optional[int] = None,
        progress: Optional[float] = None,
        stage: Optional[str] = None,
        stage_description: Optional[str] = None,
        result: Optional[Dict] = None,
        error: Optional[str] = None,
    ):
        """Обновить задачу (алиас для update_progress с дополнительными параметрами)"""
        async with self._lock:
            if task_id not in self._tasks:
                logger.warning(f"Задача {task_id} не найдена")
                return
            
            task = self._tasks[task_id]
            
            if status:
                task["status"] = status
            
            if current is not None:
                task["current"] = current
            if total is not None:
                task["total"] = total
            if progress is not None:
                task["progress"] = min(100.0, max(0.0, progress))
            elif task["total"] > 0 and current is not None:
                task["progress"] = min(100.0, (task["current"] / task["total"]) * 100.0)
            
            if stage:
                task["stage"] = stage
            if stage_description:
                task["stage_description"] = stage_description
            
            if result is not None:
                task["result"] = result
            if error is not None:
                task["error"] = error
                task["status"] = "failed"
            
            logger.info(f"Обновление задачи {task_id}: {task['progress']:.1f}% - {task['stage_description']}")
    
    async def complete_task(
        self,
        task_id: str,
        result: Optional[Dict] = None,
        error: Optional[str] = None
    ):
        """Завершить задачу"""
        async with self._lock:
            if task_id not in self._tasks:
                logger.warning(f"Задача {task_id} не найдена")
                return
            
            task = self._tasks[task_id]
            task["status"] = "failed" if error else "completed"
            task["completed_at"] = datetime.now(timezone.utc).isoformat()
            task["progress"] = 100.0 if not error else task["progress"]
            task["stage"] = "completed"
            task["stage_description"] = "Завершено" if not error else f"Ошибка: {error}"
            
            if error:
                task["error"] = error
            if result:
                task["result"] = result
            
            logger.info(f"Задача {task_id} завершена: {task['status']}")
    
    async def cancel_task(self, task_id: str):
        """Отменить задачу"""
        async with self._lock:
            if task_id not in self._tasks:
                return
            
            task = self._tasks[task_id]
            task["status"] = "cancelled"
            task["completed_at"] = datetime.now(timezone.utc).isoformat()
            task["stage"] = "cancelled"
            task["stage_description"] = "Отменено"
            logger.info(f"Задача {task_id} отменена")
    
    async def get_task(self, task_id: str) -> Optional[Dict]:
        """Получить информацию о задаче"""
        async with self._lock:
            return self._tasks.get(task_id)
    
    async def get_latest_task(self, task_type: str = "products") -> Optional[Dict]:
        """Получить последнюю задачу указанного типа"""
        async with self._lock:
            tasks_of_type = [
                task for task in self._tasks.values()
                if task["task_type"] == task_type
            ]
            if not tasks_of_type:
                return None
            
            # Сортируем по времени создания (последняя первая)
            tasks_of_type.sort(key=lambda t: t["started_at"], reverse=True)
            return tasks_of_type[0]
    
    async def cleanup_old_tasks(self, days: int = 7):
        """Удалить старые задачи (старше указанного количества дней)"""
        async with self._lock:
            cutoff = datetime.now(timezone.utc).timestamp() - (days * 24 * 60 * 60)
            to_remove = []
            
            for task_id, task in self._tasks.items():
                try:
                    started_at = datetime.fromisoformat(task["started_at"].replace("Z", "+00:00"))
                    if started_at.timestamp() < cutoff:
                        to_remove.append(task_id)
                except:
                    pass
            
            for task_id in to_remove:
                del self._tasks[task_id]
            
            if to_remove:
                logger.info(f"Удалено {len(to_remove)} старых задач")


# Глобальный экземпляр
_sync_progress_service = SyncProgressService()


def get_sync_progress_service() -> SyncProgressService:
    """Получить экземпляр сервиса отслеживания прогресса"""
    return _sync_progress_service
