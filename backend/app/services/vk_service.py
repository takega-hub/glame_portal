"""
Сервис для интеграции с ВКонтакте API
Получение статистики сообществ, постов, Stories и рекламных кампаний
"""
import httpx
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import os

logger = logging.getLogger(__name__)


class VKService:
    """Сервис для работы с VK API"""
    
    BASE_URL = "https://api.vk.com/method"
    API_VERSION = "5.131"
    
    def __init__(
        self,
        access_token: Optional[str] = None,
        group_id: Optional[str] = None
    ):
        self.access_token = access_token or os.getenv("VK_ACCESS_TOKEN")
        self.group_id = group_id or os.getenv("VK_GROUP_ID")
        
        if not self.access_token:
            raise ValueError("VK_ACCESS_TOKEN не настроен")
        if not self.group_id:
            raise ValueError("VK_GROUP_ID не настроен")
        
        self.client = httpx.AsyncClient(timeout=60.0)
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    async def close(self):
        await self.client.aclose()
    
    async def _make_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Базовый метод для запросов к API"""
        url = f"{self.BASE_URL}/{method}"
        
        request_params = {
            "access_token": self.access_token,
            "v": self.API_VERSION,
            **(params or {})
        }
        
        try:
            response = await self.client.get(url, params=request_params)
            response.raise_for_status()
            data = response.json()
            
            if "error" in data:
                raise Exception(f"VK API Error: {data['error']}")
            
            return data.get("response", {})
        except Exception as e:
            logger.error(f"Ошибка при запросе к VK API: {e}")
            raise
    
    async def get_group_info(self) -> Dict[str, Any]:
        """Получение информации о сообществе"""
        data = await self._make_request(
            "groups.getById",
            params={
                "group_id": self.group_id,
                "fields": "members_count,activity,description"
            }
        )
        
        if data and len(data) > 0:
            group = data[0]
            return {
                "id": group.get("id"),
                "name": group.get("name"),
                "screen_name": group.get("screen_name"),
                "members_count": group.get("members_count", 0),
                "activity": group.get("activity"),
                "description": group.get("description")
            }
        return {}
    
    async def get_wall_posts(self, count: int = 10) -> List[Dict[str, Any]]:
        """Получение постов со стены"""
        data = await self._make_request(
            "wall.get",
            params={
                "owner_id": f"-{self.group_id}",
                "count": count
            }
        )
        
        posts = []
        for item in data.get("items", []):
            posts.append({
                "id": item.get("id"),
                "date": datetime.fromtimestamp(item.get("date", 0)),
                "text": item.get("text", ""),
                "likes": item.get("likes", {}).get("count", 0),
                "comments": item.get("comments", {}).get("count", 0),
                "reposts": item.get("reposts", {}).get("count", 0),
                "views": item.get("views", {}).get("count", 0)
            })
        
        return posts
    
    async def get_stats(
        self,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Получение статистики сообщества"""
        if not date_from:
            date_from = datetime.now() - timedelta(days=7)
        if not date_to:
            date_to = datetime.now()
        
        data = await self._make_request(
            "stats.get",
            params={
                "group_id": self.group_id,
                "date_from": date_from.strftime("%Y-%m-%d"),
                "date_to": date_to.strftime("%Y-%m-%d")
            }
        )
        
        total_reach = 0
        total_visitors = 0
        
        for period in data:
            total_reach += period.get("reach", {}).get("reach", 0)
            total_visitors += period.get("visitors", {}).get("visitors", 0)
        
        return {
            "reach": total_reach,
            "visitors": total_visitors,
            "period_data": data
        }
    
    async def get_all_metrics(self, days: int = 7) -> Dict[str, Any]:
        """Получение всех метрик"""
        date_from = datetime.now() - timedelta(days=days)
        date_to = datetime.now()
        
        group_info = await self.get_group_info()
        posts = await self.get_wall_posts(10)
        stats = await self.get_stats(date_from, date_to)
        
        return {
            "period": {
                "start": date_from.isoformat(),
                "end": date_to.isoformat()
            },
            "group": group_info,
            "posts": posts,
            "stats": stats
        }
