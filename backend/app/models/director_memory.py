from sqlalchemy import Column, String, Text, DateTime, JSON, ForeignKey, Integer, Boolean, Index, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List

from app.database.connection import Base


class DirectorChatMessage(Base):
    """Модель сообщений в чате с директором"""
    __tablename__ = "director_chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    # Контент сообщения
    message = Column(Text, nullable=False)
    message_type = Column(String(50), nullable=False, default="text")  # text, task, report, approval, knowledge
    message_direction = Column(String(20), nullable=False, index=True)  # user, director

    # Контекст и категории
    category = Column(String(100), nullable=True, index=True)  # planning, task, report, approval, knowledge
    priority = Column(String(20), nullable=True, index=True)  # P0, P1, P2, P3
    session_id = Column(String(100), nullable=True, index=True)  # ID сессии чата

    # Временные метки
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Векторизация (для поиска)
    vector_id = Column(String(100), nullable=True, index=True)  # ID в Qdrant

    # Дополнительные данные
    extra_data = Column("extra_data", JSON, nullable=True, default=dict)

    # Статус
    status = Column(String(50), nullable=False, default="pending", index=True)  # pending, processing, completed, archived
    is_important = Column(Boolean, nullable=False, default=False, index=True)  # Отмечено как важное

    # Связи
    parent_message_id = Column(UUID(as_uuid=True), ForeignKey("director_chat_messages.id"), nullable=True)
    related_task_id = Column(UUID(as_uuid=True), ForeignKey("director_tasks.id"), nullable=True, index=True)

    # Вложенные сообщения (ответы)
    replies = relationship("DirectorChatMessage", backref="parent", remote_side=[id])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "message": self.message,
            "message_type": self.message_type,
            "message_direction": self.message_direction,
            "category": self.category,
            "priority": self.priority,
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "vector_id": self.vector_id,
            "extra_data": self.extra_data or {},
            "status": self.status,
            "is_important": self.is_important,
            "parent_message_id": str(self.parent_message_id) if self.parent_message_id else None,
            "related_task_id": str(self.related_task_id) if self.related_task_id else None,
        }


class DirectorTask(Base):
    """Модель задач от директора"""
    __tablename__ = "director_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    # Заголовок и описание
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)

    # Тип задачи
    task_type = Column(String(100), nullable=False, index=True)  # planning, assignment, report, approval, knowledge
    target_agent = Column(String(100), nullable=True, index=True)  # ai_marketing_director, ai_personal_media, etc.

    # Приоритет и статус
    priority = Column(String(20), nullable=False, default="P2", index=True)  # P0, P1, P2, P3
    status = Column(String(50), nullable=False, default="pending", index=True)  # pending, in_progress, completed, rejected

    # Дедлайны
    deadline_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Выполнение
    assigned_to = Column(String(100), nullable=True)  # Кто выполняет
    execution_notes = Column(Text, nullable=True)  # Заметки о выполнении

    # Результат
    result_summary = Column(Text, nullable=True)  # Краткий результат
    detailed_result = Column(JSON, nullable=True)  # Детальный результат

    # Векторизация
    vector_id = Column(String(100), nullable=True, index=True)

    # Метаданные
    extra_data = Column("extra_data", JSON, nullable=True, default=dict)

    # Связи с сообщениями
    related_message_id = Column(UUID(as_uuid=True), ForeignKey("director_chat_messages.id"), nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "title": self.title,
            "description": self.description,
            "task_type": self.task_type,
            "target_agent": self.target_agent,
            "priority": self.priority,
            "status": self.status,
            "deadline_at": self.deadline_at.isoformat() if self.deadline_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "assigned_to": self.assigned_to,
            "execution_notes": self.execution_notes,
            "result_summary": self.result_summary,
            "detailed_result": self.detailed_result,
            "vector_id": self.vector_id,
            "extra_data": self.extra_data or {},
            "related_message_id": str(self.related_message_id) if self.related_message_id else None,
        }


class DirectorMemory(Base):
    """Модель памяти агента-директора (кратковременная, средняя, долгая)"""
    __tablename__ = "director_memory"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    # Тип памяти
    memory_type = Column(String(50), nullable=False, index=True)  # short_term, medium_term, long_term

    # Содержимое
    content = Column(Text, nullable=False)
    content_type = Column(String(100), nullable=True)  # text, summary, insight, rule, fact

    # Векторизация
    vector_id = Column(String(100), nullable=True, index=True)

    # Дополнительные данные
    extra_data = Column("extra_data", JSON, nullable=True, default=dict)

    # Связи
    source_message_id = Column(UUID(as_uuid=True), ForeignKey("director_chat_messages.id"), nullable=True)
    source_task_id = Column(UUID(as_uuid=True), ForeignKey("director_tasks.id"), nullable=True)

    # Важность и актуальность
    importance = Column(Integer, nullable=False, default=1, index=True)  # 1-5
    relevance_score = Column(Float, nullable=True, index=True)  # Оценка релевантности

    # Временные метки
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    last_accessed_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Для кратковременной памяти

    # Статус
    status = Column(String(50), nullable=False, default="active", index=True)  # active, archived, deleted

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "memory_type": self.memory_type,
            "content": self.content,
            "content_type": self.content_type,
            "vector_id": self.vector_id,
            "extra_data": self.extra_data or {},
            "source_message_id": str(self.source_message_id) if self.source_message_id else None,
            "source_task_id": str(self.source_task_id) if self.source_task_id else None,
            "importance": self.importance,
            "relevance_score": self.relevance_score,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_accessed_at": self.last_accessed_at.isoformat() if self.last_accessed_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "status": self.status,
        }


class DirectorKnowledge(Base):
    """Модель для долгосрочной памяти и базы знаний"""
    __tablename__ = "director_knowledge"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    # Заголовок и категория
    title = Column(String(500), nullable=False)
    category = Column(String(100), nullable=False, index=True)  # strategy, process, rule, fact, insight

    # Содержимое
    content = Column(Text, nullable=False)
    content_type = Column(String(100), nullable=True)  # text, summary, guideline, best_practice

    # Векторизация
    vector_id = Column(String(100), nullable=True, index=True)

    # Дополнительные данные
    extra_data = Column("extra_data", JSON, nullable=True, default=dict)

    # Источники
    source = Column(String(255), nullable=True)  # Откуда взято (chat, task, external)
    source_message_id = Column(UUID(as_uuid=True), ForeignKey("director_chat_messages.id"), nullable=True)
    source_task_id = Column(UUID(as_uuid=True), ForeignKey("director_tasks.id"), nullable=True)

    # Важность и использование
    importance = Column(Integer, nullable=False, default=1, index=True)  # 1-5
    usage_count = Column(Integer, nullable=False, default=0, index=True)  # Сколько раз использовалось
    last_used_at = Column(DateTime(timezone=True), nullable=True, index=True)

    # Временные метки
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), index=True)

    # Статус
    status = Column(String(50), nullable=False, default="active", index=True)  # active, archived, deleted

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "title": self.title,
            "category": self.category,
            "content": self.content,
            "content_type": self.content_type,
            "vector_id": self.vector_id,
            "extra_data": self.extra_data or {},
            "source": self.source,
            "source_message_id": str(self.source_message_id) if self.source_message_id else None,
            "source_task_id": str(self.source_task_id) if self.source_task_id else None,
            "importance": self.importance,
            "usage_count": self.usage_count,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "status": self.status,
        }


class DirectorConversationContext(Base):
    """Контекст текущей сессии общения с директором"""
    __tablename__ = "director_conversation_contexts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    # Контекст сессии
    session_id = Column(String(100), nullable=False, index=True)  # Уникальный ID сессии
    current_topic = Column(String(200), nullable=True, index=True)  # Текущая тема разговора
    current_phase = Column(String(50), nullable=True, index=True)  # planning, execution, review

    # Контекстные данные
    context_data = Column(JSON, nullable=True, default=dict)  # Дополнительный контекст

    # Временные метки
    started_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    last_activity_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Время истечения сессии

    # Статус
    status = Column(String(50), nullable=False, default="active", index=True)  # active, expired

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "session_id": self.session_id,
            "current_topic": self.current_topic,
            "current_phase": self.current_phase,
            "context_data": self.context_data or {},
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "status": self.status,
        }
