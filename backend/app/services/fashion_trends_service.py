import os
import httpx
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from dotenv import load_dotenv, find_dotenv
from app.services.llm_service import llm_service
import logging

load_dotenv(find_dotenv(usecwd=True), override=False)

logger = logging.getLogger(__name__)

FASHION_TRENDS_API_KEY = os.getenv("FASHION_TRENDS_API_KEY")
FASHION_TRENDS_API_URL = os.getenv("FASHION_TRENDS_API_URL", "https://api.fashiontrends.com/v1")


class FashionTrendsService:
    """Сервис для работы с модными трендами"""
    
    def __init__(self):
        self.api_key = FASHION_TRENDS_API_KEY
        self.api_url = FASHION_TRENDS_API_URL
        self._cache: Dict[str, Dict] = {}
        self._cache_ttl = timedelta(hours=24)
    
    def _get_cache_key(self, style: Optional[str] = None, season: Optional[str] = None) -> str:
        """Генерация ключа кэша"""
        return f"trends_{style or 'all'}_{season or 'all'}"
    
    def _is_cache_valid(self, cache_entry: Dict) -> bool:
        """Проверка валидности кэша"""
        if not cache_entry:
            return False
        cached_at = cache_entry.get("cached_at")
        if not cached_at:
            return False
        if isinstance(cached_at, str):
            cached_at = datetime.fromisoformat(cached_at)
        return datetime.now() - cached_at < self._cache_ttl
    
    async def get_current_trends(self) -> List[Dict]:
        """
        Получение актуальных модных трендов
        
        Returns:
            List[Dict]: Список трендов с полями: name, description, category, season
        """
        cache_key = self._get_cache_key()
        
        # Проверяем кэш
        if cache_key in self._cache and self._is_cache_valid(self._cache[cache_key]):
            logger.debug("Возвращаем тренды из кэша")
            return self._cache[cache_key]["data"]
        
        # Пытаемся получить из API
        if self.api_key:
            try:
                trends = await self._fetch_trends_from_api()
                if trends:
                    self._cache[cache_key] = {
                        "data": trends,
                        "cached_at": datetime.now()
                    }
                    return trends
            except Exception as e:
                logger.warning(f"Ошибка при получении трендов из API: {e}")
        
        # Fallback на LLM
        logger.info("Используем LLM для получения трендов")
        trends = await self._get_trends_from_llm()
        
        # Кэшируем результат LLM тоже
        self._cache[cache_key] = {
            "data": trends,
            "cached_at": datetime.now()
        }
        
        return trends
    
    async def get_trends_for_style(self, style: str) -> List[Dict]:
        """
        Получение трендов для конкретного стиля
        
        Args:
            style: Стиль (романтичный, деловой, повседневный, etc.)
        
        Returns:
            List[Dict]: Список трендов для указанного стиля
        """
        cache_key = self._get_cache_key(style=style)
        
        # Проверяем кэш
        if cache_key in self._cache and self._is_cache_valid(self._cache[cache_key]):
            logger.debug(f"Возвращаем тренды для стиля '{style}' из кэша")
            return self._cache[cache_key]["data"]
        
        # Пытаемся получить из API
        if self.api_key:
            try:
                trends = await self._fetch_trends_from_api(style=style)
                if trends:
                    self._cache[cache_key] = {
                        "data": trends,
                        "cached_at": datetime.now()
                    }
                    return trends
            except Exception as e:
                logger.warning(f"Ошибка при получении трендов для стиля '{style}' из API: {e}")
        
        # Fallback на LLM
        logger.info(f"Используем LLM для получения трендов стиля '{style}'")
        trends = await self._get_trends_from_llm(style=style)
        
        self._cache[cache_key] = {
            "data": trends,
            "cached_at": datetime.now()
        }
        
        return trends
    
    async def get_trends_for_season(self, season: str) -> List[Dict]:
        """
        Получение сезонных трендов
        
        Args:
            season: Сезон (весна, лето, осень, зима, или spring, summer, fall, winter)
        
        Returns:
            List[Dict]: Список сезонных трендов
        """
        cache_key = self._get_cache_key(season=season)
        
        # Проверяем кэш
        if cache_key in self._cache and self._is_cache_valid(self._cache[cache_key]):
            logger.debug(f"Возвращаем тренды для сезона '{season}' из кэша")
            return self._cache[cache_key]["data"]
        
        # Пытаемся получить из API
        if self.api_key:
            try:
                trends = await self._fetch_trends_from_api(season=season)
                if trends:
                    self._cache[cache_key] = {
                        "data": trends,
                        "cached_at": datetime.now()
                    }
                    return trends
            except Exception as e:
                logger.warning(f"Ошибка при получении трендов для сезона '{season}' из API: {e}")
        
        # Fallback на LLM
        logger.info(f"Используем LLM для получения трендов сезона '{season}'")
        trends = await self._get_trends_from_llm(season=season)
        
        self._cache[cache_key] = {
            "data": trends,
            "cached_at": datetime.now()
        }
        
        return trends
    
    async def _fetch_trends_from_api(
        self,
        style: Optional[str] = None,
        season: Optional[str] = None
    ) -> List[Dict]:
        """
        Получение трендов из внешнего API
        
        Это заглушка для реального API. В реальной реализации здесь будет
        запрос к конкретному API модных трендов.
        """
        # Пример структуры запроса (адаптируйте под реальный API)
        params = {}
        if style:
            params["style"] = style
        if season:
            params["season"] = season
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.api_url}/trends",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    params=params
                )
                response.raise_for_status()
                data = response.json()
                
                # Преобразуем ответ API в стандартный формат
                return self._normalize_api_response(data)
        except Exception as e:
            logger.error(f"Ошибка при запросе к API трендов: {e}")
            raise
    
    def _normalize_api_response(self, api_data: Dict) -> List[Dict]:
        """
        Нормализация ответа API в стандартный формат
        
        Args:
            api_data: Данные от API
        
        Returns:
            List[Dict]: Нормализованный список трендов
        """
        # Адаптируйте под формат вашего API
        if isinstance(api_data, list):
            return api_data
        elif isinstance(api_data, dict) and "trends" in api_data:
            return api_data["trends"]
        elif isinstance(api_data, dict) and "data" in api_data:
            return api_data["data"]
        else:
            return []
    
    async def _get_trends_from_llm(
        self,
        style: Optional[str] = None,
        season: Optional[str] = None
    ) -> List[Dict]:
        """
        Получение трендов через LLM (fallback)
        
        Args:
            style: Опциональный стиль
            season: Опциональный сезон
        
        Returns:
            List[Dict]: Список трендов
        """
        # Определяем текущий сезон, если не указан
        if not season:
            current_month = datetime.now().month
            if current_month in [12, 1, 2]:
                season = "зима"
            elif current_month in [3, 4, 5]:
                season = "весна"
            elif current_month in [6, 7, 8]:
                season = "лето"
            else:
                season = "осень"
        
        prompt = f"""Ты эксперт по модным трендам в области украшений и аксессуаров.

Текущий сезон: {season}
{"Стиль: " + style if style else ""}

Предоставь список из 5-7 актуальных модных трендов в украшениях и аксессуарах для {season if not style else f"{style} стиля в {season}"}.

Для каждого тренда укажи:
- name: название тренда
- description: краткое описание (2-3 предложения)
- category: категория (кольца, серьги, браслеты, колье, etc.)
- season: сезон
- style: стиль (если применимо)

Ответь ТОЛЬКО валидным JSON массивом без дополнительного текста.
Формат:
[
  {{
    "name": "название тренда",
    "description": "описание",
    "category": "категория",
    "season": "{season}",
    "style": "{style or 'универсальный'}"
  }}
]"""

        try:
            response = await llm_service.generate(
                prompt=prompt,
                system_prompt="Ты эксперт по модным трендам. Отвечай только валидным JSON.",
                temperature=0.7,
                max_tokens=2000
            )
            
            # Парсим JSON из ответа
            import json
            import re
            
            # Извлекаем JSON из ответа (может быть в markdown блоке)
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = response
            
            trends = json.loads(json_str)
            
            # Убеждаемся, что это список
            if isinstance(trends, dict):
                trends = [trends]
            
            return trends
        except Exception as e:
            logger.error(f"Ошибка при получении трендов через LLM: {e}")
            # Возвращаем базовые тренды
            return self._get_default_trends(season, style)
    
    def _get_default_trends(
        self,
        season: Optional[str] = None,
        style: Optional[str] = None
    ) -> List[Dict]:
        """
        Возвращает базовые тренды, если все остальное не сработало
        """
        return [
            {
                "name": "Минимализм",
                "description": "Лаконичные украшения простых форм, акцент на качество материалов",
                "category": "универсальный",
                "season": season or "универсальный",
                "style": style or "универсальный"
            },
            {
                "name": "Смелые акценты",
                "description": "Крупные украшения с яркими элементами, привлекающие внимание",
                "category": "универсальный",
                "season": season or "универсальный",
                "style": style or "универсальный"
            }
        ]


# Singleton instance
fashion_trends_service = FashionTrendsService()
