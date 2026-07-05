from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, Text, Integer, Boolean, Index, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
import enum

from app.database.connection import Base


class InteractionStatus(str, enum.Enum):
    """Статусы межагентного взаимодействия"""
    PENDING = "pending"  # Ожидает обработки
    VALIDATING = "validating"  # Проходит валидацию
    VALIDATED = "validated"  # Прошел валидацию
    PENDING_APPROVAL = "pending_approval"  # Ожидает согласования (человеческого аппрува)
    APPROVED = "approved"  # Одобрен
    REJECTED = "rejected"  # Отклонен (не прошел валидацию или аппрув)
    QUEUED = "queued"  # В очереди на выполнение
    PROCESSING = "processing"  # В процессе выполнения
    COMPLETED = "completed"  # Выполнен успешно
    FAILED = "failed"  # Ошибка выполнения
    CANCELLED = "cancelled"  # Отменен
    DELETED = "deleted"


class TaskPriority(int, enum.Enum):
    """Приоритеты задач"""
    CRITICAL = 1  # Критический - немедленное выполнение
    HIGH = 2  # Высокий
    NORMAL = 3  # Нормальный
    LOW = 4  # Низкий
    BACKGROUND = 5  # Фоновый


class AgentInteractionTask(Base):
    """Задачи для межагентного взаимодействия"""
    
    __tablename__ = "agent_interaction_tasks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Идентификаторы агентов
    source_agent = Column(String(64), nullable=False, index=True)  # Инициатор (отправитель)
    target_agent = Column(String(64), nullable=False, index=True)  # Исполнитель (получатель)
    
    # Тип задачи и контекст
    task_type = Column(String(100), nullable=False)  # content_generation, content_review, strategy_request
    task_context = Column(JSON, nullable=False, default=dict)  # Контекст задачи
    
    # Входные данные
    input_data = Column(JSON, nullable=False, default=dict)
    
    # Целевые метрики и требования
    target_metrics = Column(JSON, nullable=True, default=dict)  # KPI, целевые показатели
    requirements = Column(JSON, nullable=True, default=dict)  # Требования к результату
    constraints = Column(JSON, nullable=True, default=dict)  # Ограничения
    
    # Приоритет и статус
    priority = Column(Integer, nullable=False, default=TaskPriority.NORMAL.value)
    status = Column(String(50), nullable=False, default=InteractionStatus.PENDING.value)
    
    # Валидация
    validation_result = Column(JSON, nullable=True)  # Результат валидации
    validation_errors = Column(JSON, nullable=True, default=list)  # Ошибки валидации
    
    # Результат выполнения
    output_data = Column(JSON, nullable=True)  # Результат работы
    output_metadata = Column("output_metadata", JSON, nullable=True, default=dict)  # Метаданные процесса создания
    
    # Ошибки
    error_message = Column(Text, nullable=True)
    error_details = Column(JSON, nullable=True)
    
    # Связь с контент-планом (если применимо)
    content_plan_id = Column(UUID(as_uuid=True), ForeignKey("content_plans.id"), nullable=True)
    content_item_id = Column(UUID(as_uuid=True), ForeignKey("content_items.id"), nullable=True)
    
    # Временные метки
    scheduled_at = Column(DateTime(timezone=True), nullable=True)  # Запланированное время выполнения
    started_at = Column(DateTime(timezone=True), nullable=True)  # Фактическое начало
    completed_at = Column(DateTime(timezone=True), nullable=True)  # Завершение
    deadline_at = Column(DateTime(timezone=True), nullable=True)  # Дедлайн
    
    # Таймаут и retry
    timeout_seconds = Column(Integer, nullable=True, default=300)  # Таймаут выполнения
    retry_count = Column(Integer, nullable=False, default=0)  # Количество попыток
    max_retries = Column(Integer, nullable=False, default=3)  # Максимум попыток
    
    # Таймстемпы
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Индексы
    __table_args__ = (
        Index('idx_agent_task_status', 'target_agent', 'status'),
        Index('idx_agent_task_priority', 'target_agent', 'priority', 'status'),
        Index('idx_agent_task_source', 'source_agent', 'status'),
        Index('idx_agent_task_schedule', 'scheduled_at', 'status'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертация модели в словарь"""
        return {
            "id": str(self.id),
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "task_type": self.task_type,
            "task_context": self.task_context or {},
            "input_data": self.input_data or {},
            "target_metrics": self.target_metrics or {},
            "requirements": self.requirements or {},
            "constraints": self.constraints or {},
            "priority": self.priority,
            "status": self.status,
            "validation_result": self.validation_result,
            "validation_errors": self.validation_errors or [],
            "output_data": self.output_data,
            "output_metadata": self.output_metadata or {},
            "error_message": self.error_message,
            "error_details": self.error_details,
            "content_plan_id": str(self.content_plan_id) if self.content_plan_id else None,
            "content_item_id": str(self.content_item_id) if self.content_item_id else None,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "deadline_at": self.deadline_at.isoformat() if self.deadline_at else None,
            "timeout_seconds": self.timeout_seconds,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AgentInteractionLog(Base):
    """Логирование цепочек взаимодействия между агентами"""
    
    __tablename__ = "agent_interaction_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("agent_interaction_tasks.id"), nullable=False, index=True)
    
    # Источник события
    agent_name = Column(String(64), nullable=False)  # Агент, создавший запись
    event_type = Column(String(100), nullable=False)  # Тип события
    
    # Данные события
    event_data = Column(JSON, nullable=False, default=dict)
    message = Column(Text, nullable=True)  # Человекочитаемое сообщение
    
    # Контекст выполнения
    execution_context = Column(JSON, nullable=True, default=dict)  # Контекст: время выполнения, ресурсы
    
    # Таймстемпы
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Индексы
    __table_args__ = (
        Index('idx_interaction_log_task', 'task_id', 'created_at'),
        Index('idx_interaction_log_agent', 'agent_name', 'event_type'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертация модели в словарь"""
        return {
            "id": str(self.id),
            "task_id": str(self.task_id),
            "agent_name": self.agent_name,
            "event_type": self.event_type,
            "event_data": self.event_data or {},
            "message": self.message,
            "execution_context": self.execution_context or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AgentValidationRule(Base):
    """Правила валидации для межагентных запросов"""
    
    __tablename__ = "agent_validation_rules"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Для какого типа задач и агентов
    task_type = Column(String(100), nullable=False, index=True)
    source_agent = Column(String(64), nullable=True)  # None = для всех
    target_agent = Column(String(64), nullable=True)  # None = для всех
    
    # Правило валидации
    rule_name = Column(String(255), nullable=False)
    rule_description = Column(Text, nullable=True)
    
    # JSON Schema для валидации или кастомная логика
    validation_schema = Column(JSON, nullable=True)  # JSON Schema
    validation_function = Column(String(255), nullable=True)  # Имя функции для кастомной валидации
    
    # Параметры правила
    is_required = Column(Boolean, nullable=False, default=True)  # Обязательное правило
    error_message = Column(Text, nullable=True)  # Сообщение об ошибке
    
    # Приоритет применения
    priority = Column(Integer, nullable=False, default=100)
    
    # Статус
    is_active = Column(Boolean, nullable=False, default=True)
    
    # Таймстемпы
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Индексы
    __table_args__ = (
        Index('idx_validation_rule_task', 'task_type', 'is_active'),
        Index('idx_validation_rule_agents', 'source_agent', 'target_agent', 'is_active'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертация модели в словарь"""
        return {
            "id": str(self.id),
            "task_type": self.task_type,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "rule_name": self.rule_name,
            "rule_description": self.rule_description,
            "validation_schema": self.validation_schema,
            "validation_function": self.validation_function,
            "is_required": self.is_required,
            "error_message": self.error_message,
            "priority": self.priority,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AgentContentHandoff(Base):
    """Передача контента между агентами"""
    
    __tablename__ = "agent_content_handoffs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("agent_interaction_tasks.id"), nullable=False, index=True)
    
    # Агенты
    from_agent = Column(String(64), nullable=False)
    to_agent = Column(String(64), nullable=False)
    
    # Контент
    content_type = Column(String(100), nullable=False)  # Тип контента: post, story, email, etc.
    content_data = Column(JSON, nullable=False)  # Данные контента
    content_metadata = Column("content_metadata", JSON, nullable=True, default=dict)  # Метаданные создания
    
    # Статус передачи
    status = Column(String(50), nullable=False, default="pending")  # pending, delivered, accepted, rejected
    
    # Обратная связь
    feedback_data = Column(JSON, nullable=True)  # Обратная связь получателя
    feedback_message = Column(Text, nullable=True)
    
    # Таймстемпы
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    responded_at = Column(DateTime(timezone=True), nullable=True)
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертация модели в словарь"""
        return {
            "id": str(self.id),
            "task_id": str(self.task_id),
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "content_type": self.content_type,
            "content_data": self.content_data,
            "content_metadata": self.content_metadata or {},
            "status": self.status,
            "feedback_data": self.feedback_data,
            "feedback_message": self.feedback_message,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "responded_at": self.responded_at.isoformat() if self.responded_at else None,
        }
