from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, Text, Integer, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List

from app.database.connection import Base


class AgentSystemPrompt(Base):
    """Модель для хранения системных промптов агентов с версионностью"""
    
    __tablename__ = "agent_system_prompts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_type = Column(String(64), nullable=False, index=True)  # content_agent, marketing_agent, stylist_agent
    
    # Версия промпта
    version = Column(Integer, nullable=False, default=1)
    version_name = Column(String(255), nullable=True)  # Название версии (например, "Летняя кампания 2026")
    
    # Содержимое промпта
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    system_prompt = Column(Text, nullable=False)
    
    # Метаданные промпта
    meta_data = Column("metadata", JSON, nullable=True, default=dict)  # Дополнительные параметры: tone, style, constraints
    
    # Статус версии
    is_active = Column(Boolean, nullable=False, default=False)  # Только одна версия может быть активной
    is_default = Column(Boolean, nullable=False, default=False)  # Версия по умолчанию
    
    # Авторство и утверждение
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    
    # Связь с AI Маркетологом
    marketer_review_status = Column(String(50), nullable=True, default="pending")  # pending, approved, rejected, needs_revision
    marketer_feedback = Column(Text, nullable=True)
    marketer_reviewed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Таймстемпы
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Индексы для оптимизации
    __table_args__ = (
        Index('idx_agent_prompt_active', 'agent_type', 'is_active'),
        Index('idx_agent_prompt_version', 'agent_type', 'version'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертация модели в словарь"""
        return {
            "id": str(self.id),
            "agent_type": self.agent_type,
            "version": self.version,
            "version_name": self.version_name,
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "metadata": self.meta_data or {},
            "is_active": self.is_active,
            "is_default": self.is_default,
            "created_by": str(self.created_by) if self.created_by else None,
            "approved_by": str(self.approved_by) if self.approved_by else None,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "marketer_review_status": self.marketer_review_status,
            "marketer_feedback": self.marketer_feedback,
            "marketer_reviewed_at": self.marketer_reviewed_at.isoformat() if self.marketer_reviewed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AgentPromptVersionHistory(Base):
    """История изменений системных промптов - полный аудит"""
    
    __tablename__ = "agent_prompt_version_history"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prompt_id = Column(UUID(as_uuid=True), ForeignKey("agent_system_prompts.id"), nullable=False, index=True)
    
    # Кто и когда изменил
    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Тип изменения
    change_type = Column(String(50), nullable=False)  # create, update, activate, approve, reject, delete
    
    # Содержимое изменений
    previous_value = Column(JSON, nullable=True)  # Предыдущие значения полей
    new_value = Column(JSON, nullable=True)  # Новые значения полей
    
    # Комментарий к изменению
    change_comment = Column(Text, nullable=True)
    
    # diff промпта (для удобства просмотра изменений)
    prompt_diff = Column(Text, nullable=True)
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертация модели в словарь"""
        return {
            "id": str(self.id),
            "prompt_id": str(self.prompt_id),
            "changed_by": str(self.changed_by) if self.changed_by else None,
            "changed_at": self.changed_at.isoformat() if self.changed_at else None,
            "change_type": self.change_type,
            "previous_value": self.previous_value,
            "new_value": self.new_value,
            "change_comment": self.change_comment,
            "prompt_diff": self.prompt_diff,
        }


class AgentPromptGenerationRequest(Base):
    """Запросы на генерацию системного промпта из текстового описания"""
    
    __tablename__ = "agent_prompt_generation_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_type = Column(String(64), nullable=False, index=True)
    
    # Входное описание от пользователя
    user_description = Column(Text, nullable=False)
    
    # Дополнительные параметры
    target_tone = Column(String(100), nullable=True)  # Желаемый тон
    target_audience = Column(String(255), nullable=True)  # Целевая аудитория
    constraints = Column(JSON, nullable=True, default=list)  # Ограничения
    
    # Результат генерации
    generated_prompt = Column(Text, nullable=True)
    generation_metadata = Column("generation_metadata", JSON, nullable=True, default=dict)
    
    # Статус
    status = Column(String(50), nullable=False, default="pending")  # pending, processing, completed, failed
    error_message = Column(Text, nullable=True)
    
    # Связь с созданным промптом
    created_prompt_id = Column(UUID(as_uuid=True), ForeignKey("agent_system_prompts.id"), nullable=True)
    
    # Авторство
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертация модели в словарь"""
        return {
            "id": str(self.id),
            "agent_type": self.agent_type,
            "user_description": self.user_description,
            "target_tone": self.target_tone,
            "target_audience": self.target_audience,
            "constraints": self.constraints or [],
            "generated_prompt": self.generated_prompt,
            "generation_metadata": self.generation_metadata or {},
            "status": self.status,
            "error_message": self.error_message,
            "created_prompt_id": str(self.created_prompt_id) if self.created_prompt_id else None,
            "created_by": str(self.created_by) if self.created_by else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }