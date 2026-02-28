from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, asc, or_
from datetime import datetime, timezone, timedelta
import json
import logging

try:
    import jsonschema
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False

from app.models.agent_interaction import (
    AgentInteractionTask,
    AgentInteractionLog,
    AgentValidationRule,
    AgentContentHandoff,
    InteractionStatus,
    TaskPriority
)
from app.models.agent_system_prompt import AgentSystemPrompt

logger = logging.getLogger(__name__)


class AgentInteractionService:
    """
    Сервис для управления межагентным взаимодействием.
    Включает валидацию, приоритизацию и логирование.
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    # ============================================================================
    # ВАЛИДАЦИЯ ЗАПРОСОВ
    # ============================================================================
    
    async def validate_incoming_task(
        self,
        task: AgentInteractionTask
    ) -> Dict[str, Any]:
        """
        Валидация входящей задачи от другого агента.
        Проверяет соответствие правилам валидации.
        """
        validation_errors = []
        validation_warnings = []
        
        # Получаем правила валидации для данного типа задачи
        rules = await self._get_validation_rules(
            task_type=task.task_type,
            source_agent=task.source_agent,
            target_agent=task.target_agent
        )
        
        # Применяем каждое правило
        for rule in rules:
            if not rule.is_active:
                continue
                
            try:
                if rule.validation_schema:
                    # Валидация по JSON Schema
                    schema_errors = self._validate_by_schema(
                        data=task.input_data,
                        schema=rule.validation_schema
                    )
                    if schema_errors:
                        if rule.is_required:
                            validation_errors.extend([
                                f"[{rule.rule_name}] {err}" for err in schema_errors
                            ])
                        else:
                            validation_warnings.extend([
                                f"[{rule.rule_name}] {err}" for err in schema_errors
                            ])
                
                if rule.validation_function:
                    # Кастомная валидация (может быть реализована через отдельные функции)
                    custom_errors = await self._run_custom_validation(
                        function_name=rule.validation_function,
                        task=task
                    )
                    if custom_errors:
                        if rule.is_required:
                            validation_errors.extend([
                                f"[{rule.rule_name}] {err}" for err in custom_errors
                            ])
                        else:
                            validation_warnings.extend([
                                f"[{rule.rule_name}] {err}" for err in custom_errors
                            ])
                            
            except Exception as e:
                logger.error(f"Ошибка применения правила валидации {rule.rule_name}: {e}")
                if rule.is_required:
                    validation_errors.append(f"[{rule.rule_name}] Ошибка валидации: {str(e)}")
        
        # Базовые проверки
        basic_errors = self._run_basic_validations(task)
        validation_errors.extend(basic_errors)
        
        # Формируем результат
        is_valid = len(validation_errors) == 0
        
        result = {
            "is_valid": is_valid,
            "errors": validation_errors,
            "warnings": validation_warnings,
            "rules_checked": len(rules),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Сохраняем результат в задаче
        task.validation_result = result
        task.validation_errors = validation_errors
        
        if is_valid:
            task.status = InteractionStatus.VALIDATED.value
        else:
            task.status = InteractionStatus.REJECTED.value
        
        await self.db.commit()
        
        # Логируем результат валидации
        await self._log_validation_result(task, result)
        
        return result
    
    async def _get_validation_rules(
        self,
        task_type: str,
        source_agent: Optional[str] = None,
        target_agent: Optional[str] = None
    ) -> List[AgentValidationRule]:
        """Получение правил валидации для задачи"""
        query = select(AgentValidationRule).where(
            and_(
                AgentValidationRule.task_type == task_type,
                AgentValidationRule.is_active == True
            )
        )
        
        # Фильтруем по агентам если указаны
        if source_agent:
            query = query.where(
                or_(
                    AgentValidationRule.source_agent == source_agent,
                    AgentValidationRule.source_agent.is_(None)
                )
            )
        
        if target_agent:
            query = query.where(
                or_(
                    AgentValidationRule.target_agent == target_agent,
                    AgentValidationRule.target_agent.is_(None)
                )
            )
        
        query = query.order_by(asc(AgentValidationRule.priority))
        
        result = await self.db.execute(query)
        return result.scalars().all()
    
    def _validate_by_schema(self, data: Dict, schema: Dict) -> List[str]:
        """Валидация данных по JSON Schema"""
        errors = []
        if not JSONSCHEMA_AVAILABLE:
            logger.warning("jsonschema не установлен, пропускаю валидацию по схеме")
            return errors
        try:
            jsonschema.validate(instance=data, schema=schema)
        except jsonschema.ValidationError as e:
            errors.append(f"Ошибка валидации: {e.message} (path: {list(e.path)})")
        except jsonschema.SchemaError as e:
            errors.append(f"Ошибка схемы: {e.message}")
        return errors
    
    async def _run_custom_validation(
        self,
        function_name: str,
        task: AgentInteractionTask
    ) -> List[str]:
        """Выполнение кастомной функции валидации"""
        errors = []
        
        # Реализация кастомных валидаций
        if function_name == "validate_content_generation_input":
            errors = self._validate_content_generation_input(task.input_data)
        elif function_name == "validate_target_metrics":
            errors = self._validate_target_metrics(task.target_metrics)
        elif function_name == "validate_deadline":
            errors = self._validate_deadline(task.deadline_at)
        elif function_name == "validate_requirements":
            errors = self._validate_requirements(task.requirements)
        
        return errors
    
    def _run_basic_validations(self, task: AgentInteractionTask) -> List[str]:
        """Базовые проверки задачи"""
        errors = []
        
        # Проверка наличия входных данных
        if not task.input_data:
            errors.append("Отсутствуют входные данные (input_data)")
        
        # Проверка дедлайна
        if task.deadline_at:
            if task.deadline_at < datetime.now(timezone.utc):
                errors.append("Дедлайн уже прошел")
        
        # Проверка таймаута
        if task.timeout_seconds and task.timeout_seconds < 10:
            errors.append("Таймаут слишком мал (минимум 10 секунд)")
        
        return errors
    
    def _validate_content_generation_input(self, input_data: Dict) -> List[str]:
        """Валидация входных данных для генерации контента"""
        errors = []
        
        required_fields = ["channel", "content_type"]
        for field in required_fields:
            if field not in input_data or not input_data[field]:
                errors.append(f"Обязательное поле отсутствует: {field}")
        
        # Проверка допустимых каналов
        valid_channels = ["instagram", "telegram", "website_main", "email", "vk", "website_blog"]
        if input_data.get("channel") and input_data["channel"] not in valid_channels:
            errors.append(f"Недопустимый канал: {input_data['channel']}")
        
        return errors
    
    def _validate_target_metrics(self, metrics: Optional[Dict]) -> List[str]:
        """Валидация целевых метрик"""
        errors = []
        
        if not metrics:
            return errors
        
        # Проверка типов метрик
        valid_metric_types = ["engagement_rate", "conversion_rate", "reach", "clicks"]
        for key in metrics.keys():
            if key not in valid_metric_types:
                errors.append(f"Неизвестная метрика: {key}")
        
        return errors
    
    def _validate_deadline(self, deadline: Optional[datetime]) -> List[str]:
        """Валидация дедлайна"""
        errors = []
        
        if not deadline:
            return errors
        
        # Дедлайн должен быть в будущем
        if deadline < datetime.now(timezone.utc):
            errors.append("Дедлайн должен быть в будущем")
        
        # Максимальный горизонт - 1 год
        max_deadline = datetime.now(timezone.utc) + timedelta(days=365)
        if deadline > max_deadline:
            errors.append("Дедлайн слишком далеко в будущем (максимум 1 год)")
        
        return errors
    
    def _validate_requirements(self, requirements: Optional[Dict]) -> List[str]:
        """Валидация требований"""
        errors = []
        
        if not requirements:
            return errors
        
        # Проверка длины текстовых требований
        if "tone" in requirements and len(requirements["tone"]) > 100:
            errors.append("Описание тона слишком длинное (максимум 100 символов)")
        
        return errors
    
    async def _log_validation_result(
        self,
        task: AgentInteractionTask,
        result: Dict[str, Any]
    ):
        """Логирование результата валидации"""
        log = AgentInteractionLog(
            task_id=task.id,
            agent_name="validation_service",
            event_type="validation_completed" if result["is_valid"] else "validation_failed",
            message=f"Валидация {'успешна' if result['is_valid'] else 'не пройдена'}. "
                    f"Ошибок: {len(result['errors'])}, Предупреждений: {len(result['warnings'])}",
            event_data=result,
            execution_context={
                "rules_checked": result["rules_checked"],
                "validation_timestamp": result["timestamp"]
            }
        )
        self.db.add(log)
        await self.db.commit()
    
    # ============================================================================
    # ПРИОРИТИЗАЦИЯ ЗАДАЧ
    # ============================================================================
    
    async def get_prioritized_tasks(
        self,
        target_agent: str,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[AgentInteractionTask]:
        """
        Получение приоритизированного списка задач для агента.
        Сортировка по: приоритету, дедлайну, времени создания.
        """
        query = select(AgentInteractionTask).where(
            AgentInteractionTask.target_agent == target_agent
        )
        
        if status:
            query = query.where(AgentInteractionTask.status == status)
        else:
            # По умолчанию - только задачи, готовые к обработке
            query = query.where(
                AgentInteractionTask.status.in_([
                    InteractionStatus.VALIDATED.value,
                    InteractionStatus.QUEUED.value
                ])
            )
        
        # Сортировка по приоритету (возрастание - lower is higher priority)
        # Затем по дедлайну (ближайшие первыми)
        # Затем по времени создания (старые первыми - FIFO)
        query = query.order_by(
            asc(AgentInteractionTask.priority),
            asc(AgentInteractionTask.deadline_at),
            asc(AgentInteractionTask.created_at)
        ).limit(limit)
        
        result = await self.db.execute(query)
        return result.scalars().all()
    
    async def calculate_task_priority(
        self,
        task: AgentInteractionTask
    ) -> int:
        """
        Расчет динамического приоритета задачи на основе различных факторов.
        """
        base_priority = task.priority
        
        # Корректировка на основе срочности дедлайна
        if task.deadline_at:
            time_to_deadline = (task.deadline_at - datetime.now(timezone.utc)).total_seconds()
            
            if time_to_deadline < 3600:  # Менее часа
                base_priority -= 1
            elif time_to_deadline < 86400:  # Менее суток
                base_priority = max(base_priority - 0, base_priority)
            elif time_to_deadline > 604800:  # Более недели
                base_priority += 1
        
        # Корректировка на основе retry_count
        if task.retry_count > 0:
            base_priority -= min(task.retry_count, 2)  # Увеличиваем приоритет при повторных попытках
        
        # Границы приоритета
        return max(TaskPriority.CRITICAL.value, min(TaskPriority.BACKGROUND.value, int(base_priority)))
    
    async def queue_task(self, task_id: str) -> AgentInteractionTask:
        """Постановка задачи в очередь на выполнение"""
        result = await self.db.execute(
            select(AgentInteractionTask).where(AgentInteractionTask.id == task_id)
        )
        task = result.scalar_one_or_none()
        
        if not task:
            raise ValueError(f"Задача с ID {task_id} не найдена")
        
        if task.status != InteractionStatus.VALIDATED.value:
            raise ValueError(f"Задача должна быть валидирована перед постановкой в очередь. Текущий статус: {task.status}")
        
        # Рассчитываем приоритет
        task.priority = await self.calculate_task_priority(task)
        task.status = InteractionStatus.QUEUED.value
        
        await self.db.commit()
        
        # Логируем
        log = AgentInteractionLog(
            task_id=task.id,
            agent_name="queue_service",
            event_type="task_queued",
            message=f"Задача поставлена в очередь с приоритетом {task.priority}",
            event_data={"priority": task.priority}
        )
        self.db.add(log)
        await self.db.commit()
        
        return task
    
    # ============================================================================
    # УПРАВЛЕНИЕ ЗАДАЧАМИ
    # ============================================================================
    
    async def get_task_by_id(self, task_id: str) -> Optional[AgentInteractionTask]:
        """Получение задачи по ID"""
        result = await self.db.execute(
            select(AgentInteractionTask).where(AgentInteractionTask.id == task_id)
        )
        return result.scalar_one_or_none()
    
    async def get_tasks_by_status(
        self,
        target_agent: str,
        status: str,
        limit: int = 100
    ) -> List[AgentInteractionTask]:
        """Получение задач по статусу"""
        result = await self.db.execute(
            select(AgentInteractionTask).where(
                and_(
                    AgentInteractionTask.target_agent == target_agent,
                    AgentInteractionTask.status == status
                )
            ).order_by(desc(AgentInteractionTask.created_at)).limit(limit)
        )
        return result.scalars().all()
    
    async def cancel_task(
        self,
        task_id: str,
        reason: Optional[str] = None
    ) -> AgentInteractionTask:
        """Отмена задачи"""
        result = await self.db.execute(
            select(AgentInteractionTask).where(AgentInteractionTask.id == task_id)
        )
        task = result.scalar_one_or_none()
        
        if not task:
            raise ValueError(f"Задача с ID {task_id} не найдена")
        
        # Нельзя отменить уже завершенную задачу
        if task.status in [InteractionStatus.COMPLETED.value, InteractionStatus.FAILED.value]:
            raise ValueError(f"Нельзя отменить задачу со статусом {task.status}")
        
        task.status = InteractionStatus.CANCELLED.value
        
        await self.db.commit()
        
        # Логируем
        log = AgentInteractionLog(
            task_id=task.id,
            agent_name="task_manager",
            event_type="task_cancelled",
            message=f"Задача отменена. Причина: {reason or 'не указана'}",
            event_data={"reason": reason}
        )
        self.db.add(log)
        await self.db.commit()
        
        return task
    
    # ============================================================================
    # ЛОГИРОВАНИЕ И АУДИТ
    # ============================================================================
    
    async def get_task_logs(
        self,
        task_id: str,
        limit: int = 100
    ) -> List[AgentInteractionLog]:
        """Получение логов задачи"""
        result = await self.db.execute(
            select(AgentInteractionLog).where(
                AgentInteractionLog.task_id == task_id
            ).order_by(desc(AgentInteractionLog.created_at)).limit(limit)
        )
        return result.scalars().all()
    
    async def get_interaction_chain(
        self,
        task_id: str
    ) -> Dict[str, Any]:
        """
        Получение полной цепочки взаимодействия для аудита.
        Включает задачу, логи и передачи контента.
        """
        # Получаем задачу
        task_result = await self.db.execute(
            select(AgentInteractionTask).where(AgentInteractionTask.id == task_id)
        )
        task = task_result.scalar_one_or_none()
        
        if not task:
            raise ValueError(f"Задача с ID {task_id} не найдена")
        
        # Получаем логи
        logs = await self.get_task_logs(task_id, limit=1000)
        
        # Получаем передачи контента
        handoffs_result = await self.db.execute(
            select(AgentContentHandoff).where(
                AgentContentHandoff.task_id == task_id
            ).order_by(desc(AgentContentHandoff.sent_at))
        )
        handoffs = handoffs_result.scalars().all()
        
        return {
            "task": task.to_dict(),
            "logs": [log.to_dict() for log in logs],
            "content_handoffs": [handoff.to_dict() for handoff in handoffs],
            "audit_summary": {
                "total_events": len(logs),
                "total_handoffs": len(handoffs),
                "duration_seconds": (
                    (task.completed_at - task.created_at).total_seconds()
                    if task.completed_at and task.created_at else None
                ),
                "status_changes": self._extract_status_changes(logs)
            }
        }
    
    def _extract_status_changes(self, logs: List[AgentInteractionLog]) -> List[Dict]:
        """Извлечение изменений статуса из логов"""
        status_changes = []
        
        for log in logs:
            if "status" in log.event_data:
                status_changes.append({
                    "timestamp": log.created_at.isoformat() if log.created_at else None,
                    "agent": log.agent_name,
                    "status": log.event_data.get("status"),
                    "event_type": log.event_type
                })
        
        return status_changes
    
    # ============================================================================
    # ПРАВИЛА ВАЛИДАЦИИ (CRUD)
    # ============================================================================
    
    async def create_validation_rule(
        self,
        task_type: str,
        rule_name: str,
        rule_description: Optional[str] = None,
        validation_schema: Optional[Dict] = None,
        validation_function: Optional[str] = None,
        source_agent: Optional[str] = None,
        target_agent: Optional[str] = None,
        is_required: bool = True,
        error_message: Optional[str] = None,
        priority: int = 100
    ) -> AgentValidationRule:
        """Создание правила валидации"""
        rule = AgentValidationRule(
            task_type=task_type,
            rule_name=rule_name,
            rule_description=rule_description,
            validation_schema=validation_schema,
            validation_function=validation_function,
            source_agent=source_agent,
            target_agent=target_agent,
            is_required=is_required,
            error_message=error_message,
            priority=priority,
            is_active=True
        )
        
        self.db.add(rule)
        await self.db.commit()
        await self.db.refresh(rule)
        
        return rule
    
    async def get_validation_rules(
        self,
        task_type: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> List[AgentValidationRule]:
        """Получение правил валидации"""
        query = select(AgentValidationRule)
        
        if task_type:
            query = query.where(AgentValidationRule.task_type == task_type)
        
        if is_active is not None:
            query = query.where(AgentValidationRule.is_active == is_active)
        
        query = query.order_by(asc(AgentValidationRule.priority))
        
        result = await self.db.execute(query)
        return result.scalars().all()


# Для совместимости с SQLAlchemy
from sqlalchemy import or_