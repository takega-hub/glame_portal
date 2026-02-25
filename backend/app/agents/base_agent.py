from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from app.services.llm_service import llm_service
from app.services.vector_service import vector_service


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
    
    async def generate_response(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 3000,  # Увеличиваем лимит по умолчанию для более полных ответов
        **kwargs
    ) -> str:
        """Генерация ответа через LLM"""
        return await self.llm.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            **kwargs
        )
