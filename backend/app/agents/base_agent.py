from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import logging
from app.services.llm_service import llm_service
from app.services.vector_service import vector_service
from app.services.ai_core_runtime import AiCoreRuntime, generate_agent_text, get_ai_core_runtime


logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Базовый класс для AI агентов"""
    
    def __init__(self):
        self.llm = llm_service
        self.vector_db = vector_service
    
    @abstractmethod
    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Основной метод обработки запроса"""
        pass
    
    async def get_brand_context(
        self,
        query: str,
        limit: int = 3,
        score_threshold: float = 0.5,
        expand_query: bool = True
    ) -> List[Dict]:
        """
        Получение контекста бренда из Vector DB с улучшенным поиском
        
        Args:
            query: Поисковый запрос
            limit: Максимальное количество результатов
            score_threshold: Минимальный порог релевантности (0.0-1.0)
            expand_query: Расширять запрос для более точного поиска
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Расширяем запрос для более точного поиска
            if expand_query:
                # Добавляем ключевые слова бренда для улучшения поиска
                expanded_query = f"{query} GLAME бренд философия стиль украшения"
            else:
                expanded_query = query
            
            # Используем более низкий порог для получения большего количества результатов
            # Затем фильтруем по релевантности
            context = self.vector_db.get_brand_context(expanded_query, limit=limit * 2, score_threshold=0.3)
            
            # Фильтруем по порогу релевантности
            filtered_context = [
                ctx for ctx in context
                if ctx.get("score", 0) >= score_threshold
            ]
            
            # Сортируем по релевантности и берем топ результатов
            filtered_context.sort(key=lambda x: x.get("score", 0), reverse=True)
            filtered_context = filtered_context[:limit]
            
            logger.debug(
                f"BaseAgent.get_brand_context: запрос '{query[:50]}...' → "
                f"найдено {len(context)} фрагментов, отфильтровано {len(filtered_context)}"
            )
            return filtered_context
        except Exception as e:
            logger.warning(f"BaseAgent.get_brand_context: ошибка при получении контекста: {e}")
            return []
    
    async def get_collections_context(
        self,
        query: str,
        limit: int = 3,
        score_threshold: float = 0.3,
        expand_query: bool = True
    ) -> List[Dict]:
        """
        Получение контекста о коллекциях из Vector DB с улучшенным поиском
        
        Args:
            query: Поисковый запрос
            limit: Максимальное количество результатов
            score_threshold: Минимальный порог релевантности (0.0-1.0)
            expand_query: Расширять запрос для более точного поиска
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Расширяем запрос для более точного поиска
            if expand_query:
                expanded_query = f"{query} коллекция GLAME"
            else:
                expanded_query = query
            
            context = self.vector_db.get_context(
                "collections_info",
                expanded_query,
                limit=limit * 2,
                score_threshold=0.2  # Для коллекций используем более низкий порог
            )
            
            # Фильтруем по порогу релевантности
            filtered_context = [
                ctx for ctx in context
                if ctx.get("score", 0) >= score_threshold
            ]
            
            # Сортируем по релевантности
            filtered_context.sort(key=lambda x: x.get("score", 0), reverse=True)
            filtered_context = filtered_context[:limit]
            
            logger.debug(
                f"BaseAgent.get_collections_context: запрос '{query[:50]}...' → "
                f"найдено {len(context)} фрагментов, отфильтровано {len(filtered_context)}"
            )
            return filtered_context
        except Exception as e:
            logger.warning(f"BaseAgent.get_collections_context: ошибка при получении контекста: {e}")
            return []
    
    def format_brand_context_for_prompt(self, context: List[Dict]) -> str:
        """
        Форматирование бренд-контекста для использования в промптах
        
        Args:
            context: Список контекстных фрагментов из Vector DB
            
        Returns:
            Отформатированная строка для промпта
        """
        if not context:
            return "Контекст бренда не найден."
        
        formatted_parts = []
        for i, ctx in enumerate(context, 1):
            payload = ctx.get("payload", {})
            text = payload.get("text", "")
            category = payload.get("category", "")
            source = payload.get("source", "")
            score = ctx.get("score", 0)
            
            part = f"[Контекст {i}]"
            if category:
                part += f" Категория: {category}"
            if source:
                part += f" Источник: {source}"
            part += f" (релевантность: {score:.2f})\n{text}"
            formatted_parts.append(part)
        
        return "\n\n".join(formatted_parts)
    
    async def get_active_system_prompt(self, db: Any, agent_type: str, fallback_prompt: str) -> str:
        """
        Получение активного системного промпта из БД.
        
        Args:
            db: Сессия базы данных (AsyncSession)
            agent_type: Тип агента (content-agent, stylist, marketer, etc.)
            fallback_prompt: Промпт по умолчанию, если в БД ничего не найдено
        """
        from app.models.agent_system_prompt import AgentSystemPrompt
        from sqlalchemy import select, desc
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            query = select(AgentSystemPrompt).where(
                AgentSystemPrompt.agent_type == agent_type,
                AgentSystemPrompt.is_active == True
            ).order_by(desc(AgentSystemPrompt.version)).limit(1)
            result = await db.execute(query)
            prompt_obj = result.scalar_one_or_none()
            if prompt_obj and prompt_obj.system_prompt:
                logger.info(f"Используется системный промпт из БД для {agent_type} (версия {prompt_obj.version})")
                return prompt_obj.system_prompt
        except Exception as e:
            logger.warning(f"Ошибка при получении системного промпта для {agent_type} из БД: {e}. Используется fallback.")
            
        return fallback_prompt

    async def generate_response(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 3000,  # Увеличиваем лимит по умолчанию для более полных ответов
        **kwargs
    ) -> str:
        """Генерация ответа через выбранное AI core.

        openrouter: старый прямой путь через LLMService.
        hermes: профиль Hermes для конкретного агента.
        local: OpenAI-compatible локальный endpoint.
        """
        runtime, source = await get_ai_core_runtime()
        if runtime == AiCoreRuntime.HERMES:
            agent_id = self._resolve_runtime_agent_id()
            if agent_id:
                output = await generate_agent_text(
                    agent_id=agent_id,
                    prompt=prompt,
                    system_prompt=system_prompt or "",
                    max_tokens=max_tokens,
                    **kwargs,
                )
                logger.info(
                    "AI core hermes used for %s (source=%s)",
                    agent_id,
                    source,
                )
                return output
            logger.warning(
                "AI core hermes selected, but %s has no runtime agent id; falling back to OpenRouter",
                self.__class__.__name__,
            )

        if runtime == AiCoreRuntime.LOCAL:
            return await generate_agent_text(
                agent_id=self._resolve_runtime_agent_id() or self.__class__.__name__,
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                **kwargs,
            )

        return await self.llm.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            **kwargs
        )

    def _resolve_runtime_agent_id(self) -> Optional[str]:
        """Resolve this Python class to a canonical Hermes-capable agent id."""

        explicit = getattr(self, "AGENT_TYPE", None) or getattr(self, "PROMPT_AGENT_TYPE", None)
        if explicit:
            return str(explicit)

        by_class = {
            "DirectorAgent": "director-agent",
            "CommunicationAgent": "crm-agent",
            "ContentAgent": "brand-media-agent",
            "AdvancedContentAgent": "brand-media-agent",
            "MarketingAgent": "traffic-growth-agent",
            "MarketingInventoryAgent": "assortment-agent",
            "AssortmentMatrixAgent": "assortment-agent",
        }
        return by_class.get(self.__class__.__name__)
