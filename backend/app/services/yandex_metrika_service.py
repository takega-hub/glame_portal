"""
Сервис для интеграции с Яндекс.Метрикой через Reporting API v1
Получение метрик о посещаемости, источниках трафика, поведении и e-commerce
"""
import httpx
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import os

logger = logging.getLogger(__name__)


class YandexMetrikaService:
    """Сервис для работы с Яндекс.Метрикой API"""
    
    BASE_URL = "https://api-metrika.yandex.net/stat/v1/data"
    
    def __init__(
        self,
        counter_id: Optional[str] = None,
        oauth_token: Optional[str] = None
    ):
        self.counter_id = counter_id or os.getenv("YANDEX_METRIKA_COUNTER_ID")
        self.oauth_token = oauth_token or os.getenv("YANDEX_METRIKA_OAUTH_TOKEN")
        
        if not self.counter_id:
            raise ValueError("YANDEX_METRIKA_COUNTER_ID не настроен")
        if not self.oauth_token:
            raise ValueError("YANDEX_METRIKA_OAUTH_TOKEN не настроен")
        
        self.client = httpx.AsyncClient(
            timeout=60.0,
            headers={
                "Authorization": f"OAuth {self.oauth_token}",
                "Content-Type": "application/json"
            }
        )
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    async def close(self):
        """Закрыть клиент"""
        await self.client.aclose()
    
    async def _make_request(
        self,
        metrics: str,
        dimensions: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        filters: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Базовый метод для запросов к API
        
        Args:
            metrics: Метрики для получения (например, "ym:s:visits,ym:s:users")
            dimensions: Измерения (например, "ym:s:date")
            start_date: Начальная дата
            end_date: Конечная дата
            filters: Фильтры
            limit: Максимальное количество результатов
        """
        if not start_date:
            start_date = datetime.now() - timedelta(days=30)
        if not end_date:
            end_date = datetime.now()
        
        params = {
            "id": self.counter_id,
            "metrics": metrics,
            "date1": start_date.strftime("%Y-%m-%d"),
            "date2": end_date.strftime("%Y-%m-%d"),
            "limit": limit
        }
        
        if dimensions:
            params["dimensions"] = dimensions
        if filters:
            params["filters"] = filters
        
        try:
            logger.info(f"Запрос к Яндекс.Метрике: {params}")
            response = await self.client.get(self.BASE_URL, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Ошибка HTTP при запросе к Яндекс.Метрике: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Ошибка при запросе к Яндекс.Метрике: {e}")
            raise
    
    async def get_visits_metrics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Получение метрик посещаемости
        
        Returns:
            {
                "visits": int,
                "users": int,
                "pageviews": int,
                "bounce_rate": float,
                "avg_visit_duration": float
            }
        """
        metrics = "ym:s:visits,ym:s:users,ym:s:pageviews,ym:s:bounceRate,ym:s:avgVisitDurationSeconds"
        
        data = await self._make_request(
            metrics=metrics,
            start_date=start_date,
            end_date=end_date
        )
        
        # Парсим ответ
        if data.get("data") and len(data["data"]) > 0:
            metrics_data = data["data"][0]["metrics"]
            return {
                "visits": int(metrics_data[0]),
                "users": int(metrics_data[1]),
                "pageviews": int(metrics_data[2]),
                "bounce_rate": float(metrics_data[3]),
                "avg_visit_duration": float(metrics_data[4])
            }
        
        return {
            "visits": 0,
            "users": 0,
            "pageviews": 0,
            "bounce_rate": 0.0,
            "avg_visit_duration": 0.0
        }
    
    async def get_traffic_sources(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Получение источников трафика
        
        Returns:
            [
                {
                    "source": str,
                    "visits": int,
                    "users": int
                }
            ]
        """
        metrics = "ym:s:visits,ym:s:users"
        dimensions = "ym:s:lastTrafficSource"
        
        data = await self._make_request(
            metrics=metrics,
            dimensions=dimensions,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )
        
        sources = []
        for row in data.get("data", []):
            sources.append({
                "source": row["dimensions"][0]["name"],
                "visits": int(row["metrics"][0]),
                "users": int(row["metrics"][1])
            })
        
        return sources
    
    async def get_behavior_metrics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Получение метрик поведения
        
        Returns:
            {
                "depth": float,
                "time_on_site": float,
                "bounce_rate": float,
                "new_users_rate": float
            }
        """
        metrics = "ym:s:pageDepth,ym:s:avgVisitDurationSeconds,ym:s:bounceRate,ym:s:percentNewVisitors"
        
        data = await self._make_request(
            metrics=metrics,
            start_date=start_date,
            end_date=end_date
        )
        
        if data.get("data") and len(data["data"]) > 0:
            metrics_data = data["data"][0]["metrics"]
            return {
                "depth": float(metrics_data[0]),
                "time_on_site": float(metrics_data[1]),
                "bounce_rate": float(metrics_data[2]),
                "new_users_rate": float(metrics_data[3])
            }
        
        return {
            "depth": 0.0,
            "time_on_site": 0.0,
            "bounce_rate": 0.0,
            "new_users_rate": 0.0
        }
    
    async def get_ecommerce_metrics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Получение метрик электронной коммерции
        
        Returns:
            {
                "transactions": int,
                "revenue": float,
                "avg_order_value": float,
                "ecommerce_conversion_rate": float
            }
        """
        # Используем только базовые метрики, которые точно существуют
        metrics = "ym:s:ecommercePurchases,ym:s:ecommerceRevenue"
        
        data = await self._make_request(
            metrics=metrics,
            start_date=start_date,
            end_date=end_date
        )
        
        if data.get("data") and len(data["data"]) > 0:
            metrics_data = data["data"][0]["metrics"]
            transactions = int(metrics_data[0])
            revenue = float(metrics_data[1])
            avg_order_value = revenue / transactions if transactions > 0 else 0.0
            
            # Для конверсии получим количество визитов отдельно
            visits_data = await self.get_visits_metrics(start_date, end_date)
            visits = visits_data.get('visits', 0)
            conversion_rate = (transactions / visits * 100) if visits > 0 else 0.0
            
            return {
                "transactions": transactions,
                "revenue": revenue,
                "avg_order_value": avg_order_value,
                "ecommerce_conversion_rate": conversion_rate
            }
        
        return {
            "transactions": 0,
            "revenue": 0.0,
            "avg_order_value": 0.0,
            "ecommerce_conversion_rate": 0.0
        }
    
    async def get_demographics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Получение демографических данных
        
        Returns:
            {
                "by_gender": [...],
                "by_age": [...]
            }
        """
        # Пол
        gender_data = await self._make_request(
            metrics="ym:s:users",
            dimensions="ym:s:gender",
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )
        
        by_gender = []
        for row in gender_data.get("data", []):
            by_gender.append({
                "gender": row["dimensions"][0]["name"],
                "users": int(row["metrics"][0])
            })
        
        # Возраст
        age_data = await self._make_request(
            metrics="ym:s:users",
            dimensions="ym:s:ageInterval",
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )
        
        by_age = []
        for row in age_data.get("data", []):
            by_age.append({
                "age_interval": row["dimensions"][0]["name"],
                "users": int(row["metrics"][0])
            })
        
        return {
            "by_gender": by_gender,
            "by_age": by_age
        }
    
    async def get_all_metrics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Получение всех метрик одним запросом
        
        Returns:
            {
                "visits": {...},
                "traffic_sources": [...],
                "behavior": {...},
                "ecommerce": {...},
                "demographics": {...}
            }
        """
        visits = await self.get_visits_metrics(start_date, end_date)
        sources = await self.get_traffic_sources(start_date, end_date)
        behavior = await self.get_behavior_metrics(start_date, end_date)
        ecommerce = await self.get_ecommerce_metrics(start_date, end_date)
        demographics = await self.get_demographics(start_date, end_date)
        
        return {
            "period": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None
            },
            "visits": visits,
            "traffic_sources": sources,
            "behavior": behavior,
            "ecommerce": ecommerce,
            "demographics": demographics
        }
