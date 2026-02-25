"""
Менеджер фоновых задач синхронизации с отслеживанием прогресса
"""
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from uuid import uuid4
from enum import Enum

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SyncTaskManager:
    """Менеджер для управления фоновыми задачами синхронизации"""
    
    def __init__(self):
        self.tasks: Dict[str, Dict[str, Any]] = {}
    
    def create_task(self, task_type: str, params: Dict[str, Any]) -> str:
        """Создание новой задачи"""
        task_id = str(uuid4())
        self.tasks[task_id] = {
            "id": task_id,
            "type": task_type,
            "status": TaskStatus.PENDING,
            "progress": 0,
            "current_step": "Инициализация...",
            "logs": [],
            "params": params,
            "result": None,
            "error": None,
            "created_at": datetime.utcnow(),
            "started_at": None,
            "completed_at": None,
        }
        logger.info(f"Создана задача синхронизации {task_id} типа {task_type}")
        return task_id
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Получение статуса задачи"""
        return self.tasks.get(task_id)
    
    def update_progress(self, task_id: str, progress: int, step: str, log: Optional[str] = None):
        """Обновление прогресса задачи"""
        if task_id in self.tasks:
            self.tasks[task_id]["progress"] = progress
            self.tasks[task_id]["current_step"] = step
            if log:
                self.tasks[task_id]["logs"].append({
                    "timestamp": datetime.utcnow().isoformat(),
                    "message": log
                })
                # Ограничиваем количество логов (последние 100)
                if len(self.tasks[task_id]["logs"]) > 100:
                    self.tasks[task_id]["logs"] = self.tasks[task_id]["logs"][-100:]
    
    def start_task(self, task_id: str):
        """Запуск задачи"""
        if task_id in self.tasks:
            self.tasks[task_id]["status"] = TaskStatus.RUNNING
            self.tasks[task_id]["started_at"] = datetime.utcnow()
    
    def complete_task(self, task_id: str, result: Dict[str, Any]):
        """Завершение задачи успешно"""
        if task_id in self.tasks:
            self.tasks[task_id]["status"] = TaskStatus.COMPLETED
            self.tasks[task_id]["progress"] = 100
            self.tasks[task_id]["current_step"] = "Завершено"
            self.tasks[task_id]["result"] = result
            self.tasks[task_id]["completed_at"] = datetime.utcnow()
    
    def fail_task(self, task_id: str, error: str):
        """Завершение задачи с ошибкой"""
        if task_id in self.tasks:
            self.tasks[task_id]["status"] = TaskStatus.FAILED
            self.tasks[task_id]["error"] = error
            self.tasks[task_id]["current_step"] = f"Ошибка: {error}"
            self.tasks[task_id]["completed_at"] = datetime.utcnow()
    
    def cleanup_old_tasks(self, max_age_hours: int = 24):
        """Очистка старых задач"""
        cutoff = datetime.utcnow().timestamp() - (max_age_hours * 3600)
        to_remove = []
        for task_id, task in self.tasks.items():
            if task["status"] in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                completed = task.get("completed_at")
                if completed and completed.timestamp() < cutoff:
                    to_remove.append(task_id)
        
        for task_id in to_remove:
            del self.tasks[task_id]
            logger.info(f"Удалена старая задача {task_id}")


# Глобальный экземпляр менеджера
task_manager = SyncTaskManager()
