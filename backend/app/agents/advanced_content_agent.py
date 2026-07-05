from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, update
from datetime import datetime, timezone
import json
import logging

from app.agents.content_agent import ContentAgent
from app.models.agent_system_prompt import AgentSystemPrompt, AgentPromptVersionHistory, AgentPromptGenerationRequest
from app.models.agent_interaction import (
    AgentInteractionTask, 
    AgentInteractionLog, 
    AgentContentHandoff,
    InteractionStatus,
    TaskPriority
)
from app.models.content_item import ContentItem
from app.models.content_plan import ContentPlan

logger = logging.getLogger(__name__)


class AdvancedContentAgent(ContentAgent):
    """
    Расширенный AI Content Agent с функционалом:
    - Управление системными промптами с версионностью
    - Интеллектуальная генерация промптов
    - Межагентное взаимодействие
    - Интеграция с AI Маркетологом
    """
    
    AGENT_TYPE = "content-agent"
    
    def __init__(self, db: AsyncSession):
        super().__init__(db)
        self.db = db
    
    # ============================================================================
    # СИСТЕМНЫЕ ПРОМПТЫ И ВЕРСИОННОСТЬ
    # ============================================================================
    
    async def get_active_system_prompt(self) -> Optional[AgentSystemPrompt]:
        """Получение активного системного промпта"""
        result = await self.db.execute(
            select(AgentSystemPrompt).where(
                and_(
                    AgentSystemPrompt.agent_type == self.AGENT_TYPE,
                    AgentSystemPrompt.is_active == True
                )
            ).order_by(desc(AgentSystemPrompt.version)).limit(1)
        )
        return result.scalar_one_or_none()
    
    async def get_default_system_prompt_text(self) -> str:
        """Получение текста системного промпта (активного или дефолтного)"""
        active_prompt = await self.get_active_system_prompt()
        if active_prompt:
            return active_prompt.system_prompt
        return self.BRAND_SYSTEM_PROMPT
    
    async def create_prompt_version(
        self,
        name: str,
        system_prompt: str,
        description: Optional[str] = None,
        metadata: Optional[Dict] = None,
        created_by: Optional[str] = None,
        version_name: Optional[str] = None
    ) -> AgentSystemPrompt:
        """Создание новой версии системного промпта"""
        # Получаем следующую версию
        result = await self.db.execute(
            select(AgentSystemPrompt).where(
                AgentSystemPrompt.agent_type == self.AGENT_TYPE
            ).order_by(desc(AgentSystemPrompt.version)).limit(1)
        )
        latest = result.scalar_one_or_none()
        next_version = (latest.version + 1) if latest else 1
        
        # Создаем новую версию
        prompt = AgentSystemPrompt(
            agent_type=self.AGENT_TYPE,
            version=next_version,
            version_name=version_name or f"Версия {next_version}",
            name=name,
            description=description,
            system_prompt=system_prompt,
            meta_data=metadata or {},
            is_active=False,  # Новая версия неактивна по умолчанию
            is_default=False,
            created_by=created_by,
            marketer_review_status="pending"
        )
        
        self.db.add(prompt)
        await self.db.flush()
        
        # Логируем создание
        await self._log_prompt_change(
            prompt_id=prompt.id,
            change_type="create",
            new_value={"name": name, "version": next_version, "description": description},
            changed_by=created_by,
            change_comment=f"Создана версия {next_version}"
        )
        
        await self.db.commit()
        return prompt
    
    async def activate_prompt_version(
        self,
        prompt_id: str,
        activated_by: Optional[str] = None
    ) -> AgentSystemPrompt:
        """Активация версии системного промпта"""
        result = await self.db.execute(
            select(AgentSystemPrompt).where(
                and_(
                    AgentSystemPrompt.id == prompt_id,
                    AgentSystemPrompt.agent_type == self.AGENT_TYPE,
                )
            )
        )
        prompt = result.scalar_one_or_none()
        
        if not prompt:
            raise ValueError(f"Промпт с ID {prompt_id} не найден")
        
        # Сохраняем предыдущее состояние
        previous_value = {"is_active": prompt.is_active}

        # Деактивируем все текущие активные версии этого агента.
        await self.db.execute(
            update(AgentSystemPrompt)
            .where(
                and_(
                    AgentSystemPrompt.agent_type == self.AGENT_TYPE,
                    AgentSystemPrompt.id != prompt.id,
                    AgentSystemPrompt.is_active == True,
                )
            )
            .values(is_active=False, updated_at=datetime.now(timezone.utc))
        )
        
        # Активируем
        prompt.is_active = True
        prompt.updated_at = datetime.now(timezone.utc)
        
        # Логируем изменение
        await self._log_prompt_change(
            prompt_id=prompt.id,
            change_type="activate",
            previous_value=previous_value,
            new_value={"is_active": True},
            changed_by=activated_by,
            change_comment=f"Активирована версия {prompt.version}"
        )
        
        await self.db.commit()
        await self.db.refresh(prompt)
        return prompt
    
    async def submit_for_marketer_review(
        self,
        prompt_id: str,
        submitted_by: Optional[str] = None
    ) -> AgentSystemPrompt:
        """Отправка промпта на ревью AI Маркетологу"""
        result = await self.db.execute(
            select(AgentSystemPrompt).where(AgentSystemPrompt.id == prompt_id)
        )
        prompt = result.scalar_one_or_none()
        
        if not prompt:
            raise ValueError(f"Промпт с ID {prompt_id} не найден")
        
        prompt.marketer_review_status = "pending"
        prompt.updated_at = datetime.now(timezone.utc)
        
        await self._log_prompt_change(
            prompt_id=prompt.id,
            change_type="submit_for_review",
            changed_by=submitted_by,
            change_comment="Отправлено на ревью AI Маркетологу"
        )
        
        await self.db.commit()
        await self.db.refresh(prompt)
        return prompt
    
    async def review_prompt_as_marketer(
        self,
        prompt_id: str,
        status: str,  # approved, rejected, needs_revision
        feedback: Optional[str] = None,
        reviewed_by: Optional[str] = None
    ) -> AgentSystemPrompt:
        """Ревью промпта AI Маркетологом"""
        result = await self.db.execute(
            select(AgentSystemPrompt).where(AgentSystemPrompt.id == prompt_id)
        )
        prompt = result.scalar_one_or_none()
        
        if not prompt:
            raise ValueError(f"Промпт с ID {prompt_id} не найден")
        
        previous_status = prompt.marketer_review_status
        
        prompt.marketer_review_status = status
        prompt.marketer_feedback = feedback
        prompt.marketer_reviewed_at = datetime.now(timezone.utc)
        prompt.approved_by = reviewed_by if status == "approved" else prompt.approved_by
        prompt.approved_at = datetime.now(timezone.utc) if status == "approved" else prompt.approved_at
        
        await self._log_prompt_change(
            prompt_id=prompt.id,
            change_type="marketer_review",
            previous_value={"marketer_review_status": previous_status},
            new_value={"marketer_review_status": status, "feedback": feedback},
            changed_by=reviewed_by,
            change_comment=f"Ревью AI Маркетолога: {status}"
        )
        
        await self.db.commit()
        await self.db.refresh(prompt)
        return prompt
    
    async def get_prompt_versions(
        self,
        include_inactive: bool = True
    ) -> List[AgentSystemPrompt]:
        """Получение всех версий промптов"""
        query = select(AgentSystemPrompt).where(
            AgentSystemPrompt.agent_type == self.AGENT_TYPE
        ).order_by(desc(AgentSystemPrompt.version))
        
        if not include_inactive:
            query = query.where(AgentSystemPrompt.is_active == True)
        
        result = await self.db.execute(query)
        return result.scalars().all()
    
    async def get_prompt_history(
        self,
        prompt_id: str
    ) -> List[AgentPromptVersionHistory]:
        """Получение истории изменений промпта"""
        result = await self.db.execute(
            select(AgentPromptVersionHistory).where(
                AgentPromptVersionHistory.prompt_id == prompt_id
            ).order_by(desc(AgentPromptVersionHistory.changed_at))
        )
        return result.scalars().all()
    
    async def update_prompt_version(
        self,
        prompt_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        system_prompt: Optional[str] = None,
        version_name: Optional[str] = None,
        metadata: Optional[Dict] = None,
        updated_by: Optional[str] = None
    ) -> AgentSystemPrompt:
        """Обновление версии системного промпта"""
        result = await self.db.execute(
            select(AgentSystemPrompt).where(AgentSystemPrompt.id == prompt_id)
        )
        prompt = result.scalar_one_or_none()
        
        if not prompt:
            raise ValueError(f"Промпт с ID {prompt_id} не найден")
        
        # Сохраняем предыдущие значения для логирования
        previous_value = {
            "name": prompt.name,
            "description": prompt.description,
            "system_prompt": prompt.system_prompt,
            "version_name": prompt.version_name,
            "metadata": prompt.meta_data
        }
        
        # Обновляем поля
        if name is not None:
            prompt.name = name
        if description is not None:
            prompt.description = description
        if system_prompt is not None:
            prompt.system_prompt = system_prompt
        if version_name is not None:
            prompt.version_name = version_name
        if metadata is not None:
            prompt.meta_data = metadata
            
        prompt.updated_at = datetime.now(timezone.utc)
        
        # Логируем изменение
        new_value = {
            "name": prompt.name,
            "description": prompt.description,
            "system_prompt": prompt.system_prompt,
            "version_name": prompt.version_name,
            "metadata": prompt.meta_data
        }
        
        await self._log_prompt_change(
            prompt_id=prompt.id,
            change_type="update",
            previous_value=previous_value,
            new_value=new_value,
            changed_by=updated_by,
            change_comment="Обновление версии промпта"
        )
        
        await self.db.commit()
        await self.db.refresh(prompt)
        return prompt
    
    async def _log_prompt_change(
        self,
        prompt_id: str,
        change_type: str,
        previous_value: Optional[Dict] = None,
        new_value: Optional[Dict] = None,
        changed_by: Optional[str] = None,
        change_comment: Optional[str] = None,
        prompt_diff: Optional[str] = None
    ):
        """Логирование изменений промпта"""
        history = AgentPromptVersionHistory(
            prompt_id=prompt_id,
            change_type=change_type,
            previous_value=previous_value,
            new_value=new_value,
            changed_by=changed_by,
            change_comment=change_comment,
            prompt_diff=prompt_diff
        )
        self.db.add(history)
    
    # ============================================================================
    # ИНТЕЛЛЕКТУАЛЬНАЯ ГЕНЕРАЦИЯ ПРОМПТОВ
    # ============================================================================
    
    async def generate_system_prompt_from_description(
        self,
        user_description: str,
        target_tone: Optional[str] = None,
        target_audience: Optional[str] = None,
        constraints: Optional[List[str]] = None,
        created_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Генерация системного промпта на основе текстового описания задачи.
        Использует встроенный AI-ассистент для автоматической формализации требований.
        """
        # Создаем запрос на генерацию
        request = AgentPromptGenerationRequest(
            agent_type=self.AGENT_TYPE,
            user_description=user_description,
            target_tone=target_tone,
            target_audience=target_audience,
            constraints=constraints or [],
            status="processing",
            created_by=created_by
        )
        self.db.add(request)
        await self.db.flush()
        
        try:
            # Формируем промпт для генерации системного промпта
            generation_prompt = self._build_prompt_generation_prompt(
                user_description=user_description,
                target_tone=target_tone,
                target_audience=target_audience,
                constraints=constraints
            )
            
            # Генерируем системный промпт
            generated_content = await self.llm.generate(
                prompt=generation_prompt,
                system_prompt="Ты - эксперт по prompt engineering. Твоя задача - создавать эффективные системные промпты для AI-агентов.",
                temperature=0.7,
                max_tokens=2000
            )
            
            # Парсим результат
            generated_prompt = self._extract_system_prompt(generated_content)
            
            # Генерируем метаданные
            metadata = {
                "source_description": user_description,
                "generation_params": {
                    "target_tone": target_tone,
                    "target_audience": target_audience,
                    "constraints": constraints
                },
                "raw_generation": generated_content,
            }
            
            # Обновляем запрос
            request.generated_prompt = generated_prompt
            request.generation_metadata = metadata
            request.status = "completed"
            request.completed_at = datetime.now(timezone.utc)
            
            await self.db.commit()
            await self.db.refresh(request)
            
            return {
                "request_id": str(request.id),
                "generated_prompt": generated_prompt,
                "metadata": metadata,
                "status": "completed"
            }
            
        except Exception as e:
            logger.error(f"Ошибка генерации системного промпта: {e}")
            request.status = "failed"
            request.error_message = str(e)
            await self.db.commit()
            raise
    
    def _build_prompt_generation_prompt(
        self,
        user_description: str,
        target_tone: Optional[str] = None,
        target_audience: Optional[str] = None,
        constraints: Optional[List[str]] = None
    ) -> str:
        """Формирование промпта для генерации системного промпта"""
        prompt_parts = [
            "Создай системный промпт для AI Content Agent бренда GLAME.",
            "",
            f"Описание задачи от пользователя:\n{user_description}",
        ]
        
        if target_tone:
            prompt_parts.append(f"\nЖелаемый тон: {target_tone}")
        
        if target_audience:
            prompt_parts.append(f"\nЦелевая аудитория: {target_audience}")
        
        if constraints:
            prompt_parts.append(f"\nОграничения:\n" + "\n".join(f"- {c}" for c in constraints))
        
        prompt_parts.extend([
            "",
            "Требования к системному промпту:",
            "1. Определи роль агента ясно и четко",
            "2. Опиши философию бренда GLAME (премиальные украшения, авторский дизайн)",
            "3. Укажи ключевые задачи агента",
            "4. Определи стиль коммуникации",
            "5. Добавь инструкции по форматированию контента",
            "6. Укажи ограничения и запреты",
            "",
            "Верни ТОЛЬКО текст системного промпта без дополнительных комментариев."
        ])
        
        return "\n".join(prompt_parts)
    
    def _extract_system_prompt(self, generated_content: str) -> str:
        """Извлечение системного промпта из сгенерированного контента"""
        # Очистка от markdown code blocks
        content = generated_content.strip()
        
        if content.startswith("```"):
            lines = content.split("\n")
            # Убираем первую строку с ```
            if lines[0].startswith("```"):
                lines = lines[1:]
            # Убираем последнюю строку с ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)
        
        return content.strip()
    
    # ============================================================================
    # ПЕРЕОПРЕДЕЛЕНИЕ МЕТОДОВ ГЕНЕРАЦИИ С УЧЕТОМ СИСТЕМНОГО ПРОМПТА
    # ============================================================================
    
    async def process(
        self,
        persona: Optional[str] = None,
        cjm_stage: Optional[str] = None,
        channel: str = "website_main",
        goal: Optional[str] = None,
        use_custom_prompt: bool = True
    ) -> Dict[str, Any]:
        """Генерация контента с использованием активного системного промпта"""
        # Получаем активный системный промпт
        if use_custom_prompt:
            system_prompt = await self.get_default_system_prompt_text()
        else:
            system_prompt = self.BRAND_SYSTEM_PROMPT
        
        # Вызываем родительский метод с кастомным промптом
        result = await super().process(persona, cjm_stage, channel, goal)
        
        # Добавляем информацию о использованном промпте
        active_prompt = await self.get_active_system_prompt()
        result["system_prompt_info"] = {
            "used_custom_prompt": use_custom_prompt and active_prompt is not None,
            "prompt_version": active_prompt.version if active_prompt else None,
            "prompt_name": active_prompt.name if active_prompt else "default"
        }
        
        return result
    
    async def generate_calendar_plan(
        self,
        start_date: str,
        end_date: str,
        timezone: str,
        channels: List[str],
        frequency_rules: Optional[Dict[str, Any]] = None,
        persona: Optional[str] = None,
        goal: Optional[str] = None,
        campaign_context: Optional[str] = None,
        use_custom_prompt: bool = True
    ) -> Dict[str, Any]:
        """Генерация календарного плана с использованием активного системного промпта"""
        # Получаем активный системный промпт
        if use_custom_prompt:
            system_prompt = await self.get_default_system_prompt_text()
        else:
            system_prompt = self.BRAND_SYSTEM_PROMPT
        
        # Сохраняем оригинальный промпт
        original_prompt = self.BRAND_SYSTEM_PROMPT
        self.BRAND_SYSTEM_PROMPT = system_prompt
        
        try:
            result = await super().generate_calendar_plan(
                start_date=start_date,
                end_date=end_date,
                timezone=timezone,
                channels=channels,
                frequency_rules=frequency_rules,
                persona=persona,
                goal=goal,
                campaign_context=campaign_context
            )
            
            # Добавляем информацию о использованном промпте
            active_prompt = await self.get_active_system_prompt()
            if isinstance(result, dict):
                result["system_prompt_info"] = {
                    "used_custom_prompt": use_custom_prompt and active_prompt is not None,
                    "prompt_version": active_prompt.version if active_prompt else None,
                    "prompt_name": active_prompt.name if active_prompt else "default"
                }
            
            return result
        finally:
            # Восстанавливаем оригинальный промпт
            self.BRAND_SYSTEM_PROMPT = original_prompt
    
    # ============================================================================
    # МЕЖАГЕНТНОЕ ВЗАИМОДЕЙСТВИЕ
    # ============================================================================
    
    async def receive_task_from_agent(
        self,
        source_agent: str,
        task_type: str,
        task_context: Dict[str, Any],
        input_data: Dict[str, Any],
        target_metrics: Optional[Dict[str, Any]] = None,
        requirements: Optional[Dict[str, Any]] = None,
        constraints: Optional[Dict[str, Any]] = None,
        priority: int = TaskPriority.NORMAL.value,
        deadline_at: Optional[datetime] = None
    ) -> AgentInteractionTask:
        """
        Получение структурированного задания от другого AI-агента.
        """
        # Создаем задачу
        task = AgentInteractionTask(
            source_agent=source_agent,
            target_agent=self.AGENT_TYPE,
            task_type=task_type,
            task_context=task_context,
            input_data=input_data,
            target_metrics=target_metrics or {},
            requirements=requirements or {},
            constraints=constraints or {},
            priority=priority,
            status=InteractionStatus.PENDING.value,
            deadline_at=deadline_at
        )
        
        self.db.add(task)
        await self.db.flush()
        
        # Логируем получение
        await self._log_interaction(
            task_id=task.id,
            event_type="task_received",
            message=f"Получена задача типа '{task_type}' от агента '{source_agent}'",
            event_data={
                "source_agent": source_agent,
                "task_type": task_type,
                "priority": priority
            }
        )
        
        await self.db.commit()
        return task
    
    async def process_agent_task(self, task_id: str) -> Dict[str, Any]:
        """Обработка задачи от другого агента"""
        # Получаем задачу
        result = await self.db.execute(
            select(AgentInteractionTask).where(AgentInteractionTask.id == task_id)
        )
        task = result.scalar_one_or_none()
        
        if not task:
            raise ValueError(f"Задача с ID {task_id} не найдена")
        
        # Обновляем статус
        task.status = InteractionStatus.PROCESSING.value
        task.started_at = datetime.now(timezone.utc)
        await self.db.commit()
        
        # Логируем начало обработки
        await self._log_interaction(
            task_id=task.id,
            event_type="processing_started",
            message="Начата обработка задачи",
            event_data={"task_type": task.task_type}
        )
        
        try:
            # Выполняем задачу в зависимости от типа
            if task.task_type == "content_generation":
                result_data = await self._handle_content_generation_task(task)
            elif task.task_type == "content_review":
                result_data = await self._handle_content_review_task(task)
            elif task.task_type == "calendar_plan_generation":
                result_data = await self._handle_calendar_plan_task(task)
            else:
                raise ValueError(f"Неизвестный тип задачи: {task.task_type}")
            
            # Обновляем задачу
            task.status = InteractionStatus.COMPLETED.value
            task.output_data = result_data
            task.output_metadata = {
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "agent_version": "advanced_content_agent_v1",
                "processing_duration_seconds": (
                    datetime.now(timezone.utc) - task.started_at
                ).total_seconds() if task.started_at else None
            }
            task.completed_at = datetime.now(timezone.utc)
            
            # Логируем успешное завершение
            await self._log_interaction(
                task_id=task.id,
                event_type="processing_completed",
                message="Задача успешно выполнена",
                event_data={"result_summary": self._summarize_result(result_data)}
            )
            
            await self.db.commit()
            
            # Передаем результат инициатору
            await self._handoff_result_to_agent(task)
            
            return result_data
            
        except Exception as e:
            logger.error(f"Ошибка обработки задачи {task_id}: {e}")
            task.status = InteractionStatus.FAILED.value
            task.error_message = str(e)
            task.error_details = {"exception_type": type(e).__name__}
            
            await self._log_interaction(
                task_id=task.id,
                event_type="processing_failed",
                message=f"Ошибка обработки: {str(e)}",
                event_data={"error": str(e)},
                is_error=True
            )
            
            await self.db.commit()
            raise
    
    async def _handle_content_generation_task(self, task: AgentInteractionTask) -> Dict[str, Any]:
        """Обработка задачи генерации контента"""
        input_data = task.input_data or {}
        
        result = await self.generate_item_content(
            channel=input_data.get("channel", "instagram"),
            content_type=input_data.get("content_type", "post"),
            topic=input_data.get("topic"),
            hook=input_data.get("hook"),
            cta=input_data.get("cta"),
            persona=input_data.get("persona"),
            cjm_stage=input_data.get("cjm_stage"),
            goal=input_data.get("goal"),
            spec=input_data.get("spec", {})
        )
        
        return result
    
    async def _handle_content_review_task(self, task: AgentInteractionTask) -> Dict[str, Any]:
        """Обработка задачи ревью контента"""
        input_data = task.input_data or {}
        content = input_data.get("content", {})
        requirements = task.requirements or {}
        
        # Формируем промпт для ревью
        review_prompt = f"""Проанализируй контент на соответствие требованиям:

Контент:
{json.dumps(content, ensure_ascii=False, indent=2)}

Требования:
{json.dumps(requirements, ensure_ascii=False, indent=2)}

Целевые метрики:
{json.dumps(task.target_metrics or {}, ensure_ascii=False, indent=2)}

Предоставь:
1. Оценку соответствия (0-100)
2. Соответствие каждому требованию (да/частично/нет)
3. Рекомендации по улучшению
4. Прогноз по целевым метрикам
"""
        
        review_result = await self.generate_response(
            prompt=review_prompt,
            system_prompt="Ты - эксперт по контент-анализу. Оценивай объективно и конструктивно.",
            temperature=0.5
        )
        
        return {
            "review_result": review_result,
            "content_analyzed": content,
            "requirements_checked": list(requirements.keys()),
            "review_timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    async def _handle_calendar_plan_task(self, task: AgentInteractionTask) -> Dict[str, Any]:
        """Обработка задачи генерации календарного плана"""
        input_data = task.input_data or {}
        
        result = await self.generate_calendar_plan(
            start_date=input_data.get("start_date"),
            end_date=input_data.get("end_date"),
            timezone=input_data.get("timezone", "Europe/Moscow"),
            channels=input_data.get("channels", ["instagram"]),
            frequency_rules=input_data.get("frequency_rules"),
            persona=input_data.get("persona"),
            goal=input_data.get("goal"),
            campaign_context=input_data.get("campaign_context")
        )
        
        return result
    
    async def _handoff_result_to_agent(self, task: AgentInteractionTask):
        """Передача результата инициирующему агенту"""
        handoff = AgentContentHandoff(
            task_id=task.id,
            from_agent=self.AGENT_TYPE,
            to_agent=task.source_agent,
            content_type=task.task_type,
            content_data=task.output_data or {},
            content_metadata=task.output_metadata or {} if hasattr(task, 'output_metadata') else {},
            status="delivered"
        )
        
        self.db.add(handoff)
        
        await self._log_interaction(
            task_id=task.id,
            event_type="result_handoff",
            message=f"Результат передан агенту '{task.source_agent}'",
            event_data={
                "target_agent": task.source_agent,
                "handoff_id": str(handoff.id)
            }
        )
        
        await self.db.commit()
    
    async def _log_interaction(
        self,
        task_id: str,
        event_type: str,
        message: Optional[str] = None,
        event_data: Optional[Dict] = None,
        execution_context: Optional[Dict] = None,
        is_error: bool = False
    ):
        """Логирование взаимодействия"""
        log = AgentInteractionLog(
            task_id=task_id,
            agent_name=self.AGENT_TYPE,
            event_type=event_type,
            message=message,
            event_data=event_data or {},
            execution_context=execution_context or {}
        )
        self.db.add(log)
    
    def _summarize_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Создание краткого summaries результата для логирования"""
        if not isinstance(result, dict):
            return {"type": "unknown", "size": len(str(result))}
        
        summary = {}
        for key, value in result.items():
            if isinstance(value, (str, int, float, bool)):
                summary[key] = value
            elif isinstance(value, list):
                summary[key] = f"[list of {len(value)} items]"
            elif isinstance(value, dict):
                summary[key] = f"[dict with {len(value)} keys]"
            else:
                summary[key] = str(type(value))
        return summary
