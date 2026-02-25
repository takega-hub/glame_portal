"""
Сервис для интеграции с Instagram Graph API
Получение статистики постов, Stories, подписчиков и инсайтов
"""
import httpx
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import os

logger = logging.getLogger(__name__)


class InstagramService:
    """Сервис для работы с Instagram Graph API"""
    
    BASE_URL = "https://graph.facebook.com/v18.0"
    
    def __init__(
        self,
        access_token: Optional[str] = None,
        account_id: Optional[str] = None
    ):
        self.access_token = access_token or os.getenv("INSTAGRAM_ACCESS_TOKEN")
        self.account_id = account_id or os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
        
        if not self.access_token:
            raise ValueError("INSTAGRAM_ACCESS_TOKEN не настроен")
        if not self.account_id:
            raise ValueError("INSTAGRAM_BUSINESS_ACCOUNT_ID не настроен")
        
        self.client = httpx.AsyncClient(
            timeout=60.0,
            params={"access_token": self.access_token}
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
        endpoint: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Базовый метод для запросов к API"""
        url = f"{self.BASE_URL}/{endpoint}"
        
        try:
            logger.info(f"Запрос к Instagram API: {endpoint}")
            response = await self.client.get(url, params=params or {})
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Ошибка HTTP при запросе к Instagram API: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Ошибка при запросе к Instagram API: {e}")
            raise
    
    async def get_account_info(self) -> Dict[str, Any]:
        """
        Получение информации об аккаунте
        
        Returns:
            {
                "id": str,
                "username": str,
                "name": str,
                "followers_count": int,
                "follows_count": int,
                "media_count": int
            }
        """
        fields = "id,username,name,followers_count,follows_count,media_count,profile_picture_url"
        data = await self._make_request(
            self.account_id,
            params={"fields": fields}
        )
        
        return {
            "id": data.get("id"),
            "username": data.get("username"),
            "name": data.get("name"),
            "followers_count": data.get("followers_count", 0),
            "follows_count": data.get("follows_count", 0),
            "media_count": data.get("media_count", 0),
            "profile_picture_url": data.get("profile_picture_url")
        }
    
    async def get_media_list(
        self,
        limit: int = 25
    ) -> List[Dict[str, Any]]:
        """
        Получение списка медиа (постов)
        
        Returns:
            [
                {
                    "id": str,
                    "media_type": str,  # IMAGE, VIDEO, CAROUSEL_ALBUM
                    "media_url": str,
                    "caption": str,
                    "timestamp": str
                }
            ]
        """
        fields = "id,media_type,media_url,caption,timestamp,permalink"
        data = await self._make_request(
            f"{self.account_id}/media",
            params={
                "fields": fields,
                "limit": limit
            }
        )
        
        media_list = []
        for item in data.get("data", []):
            media_list.append({
                "id": item.get("id"),
                "media_type": item.get("media_type"),
                "media_url": item.get("media_url"),
                "caption": item.get("caption", ""),
                "timestamp": item.get("timestamp"),
                "permalink": item.get("permalink")
            })
        
        return media_list
    
    async def get_media_insights(
        self,
        media_id: str
    ) -> Dict[str, Any]:
        """
        Получение инсайтов для конкретного поста
        
        Returns:
            {
                "engagement": int,
                "impressions": int,
                "reach": int,
                "saved": int,
                "likes": int,
                "comments": int
            }
        """
        # Для постов (IMAGE, VIDEO, CAROUSEL_ALBUM)
        metrics = "engagement,impressions,reach,saved"
        
        try:
            data = await self._make_request(
                f"{media_id}/insights",
                params={"metric": metrics}
            )
            
            insights = {}
            for item in data.get("data", []):
                metric_name = item.get("name")
                metric_value = item.get("values", [{}])[0].get("value", 0)
                insights[metric_name] = metric_value
            
            # Получаем лайки и комментарии отдельно
            media_data = await self._make_request(
                media_id,
                params={"fields": "like_count,comments_count"}
            )
            
            insights["likes"] = media_data.get("like_count", 0)
            insights["comments"] = media_data.get("comments_count", 0)
            
            return insights
            
        except Exception as e:
            logger.warning(f"Не удалось получить инсайты для медиа {media_id}: {e}")
            return {
                "engagement": 0,
                "impressions": 0,
                "reach": 0,
                "saved": 0,
                "likes": 0,
                "comments": 0
            }
    
    async def get_stories_insights(
        self,
        story_id: str
    ) -> Dict[str, Any]:
        """
        Получение инсайтов для Stories
        
        Returns:
            {
                "impressions": int,
                "reach": int,
                "replies": int,
                "exits": int,
                "taps_forward": int,
                "taps_back": int
            }
        """
        # Для Stories метрики отличаются
        metrics = "impressions,reach,replies,exits,taps_forward,taps_back"
        
        try:
            data = await self._make_request(
                f"{story_id}/insights",
                params={"metric": metrics}
            )
            
            insights = {}
            for item in data.get("data", []):
                metric_name = item.get("name")
                metric_value = item.get("values", [{}])[0].get("value", 0)
                insights[metric_name] = metric_value
            
            return insights
            
        except Exception as e:
            logger.warning(f"Не удалось получить инсайты для Stories {story_id}: {e}")
            return {
                "impressions": 0,
                "reach": 0,
                "replies": 0,
                "exits": 0,
                "taps_forward": 0,
                "taps_back": 0
            }
    
    async def get_account_insights(
        self,
        period: str = "day",
        since: Optional[datetime] = None,
        until: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Получение общих инсайтов аккаунта
        
        Args:
            period: 'day', 'week', 'days_28', 'lifetime'
            since: Начальная дата
            until: Конечная дата
        
        Returns:
            {
                "impressions": int,
                "reach": int,
                "profile_views": int,
                "website_clicks": int,
                "follower_count": int
            }
        """
        if not since:
            since = datetime.now() - timedelta(days=7)
        if not until:
            until = datetime.now()
        
        metrics = "impressions,reach,profile_views,website_clicks,follower_count"
        
        params = {
            "metric": metrics,
            "period": period
        }
        
        # Добавляем даты для некоторых метрик
        if period == "day":
            params["since"] = int(since.timestamp())
            params["until"] = int(until.timestamp())
        
        try:
            data = await self._make_request(
                f"{self.account_id}/insights",
                params=params
            )
            
            insights = {}
            for item in data.get("data", []):
                metric_name = item.get("name")
                values = item.get("values", [])
                
                # Суммируем значения за период
                if values:
                    if period == "day":
                        # Для daily - суммируем все дни
                        total = sum(v.get("value", 0) for v in values)
                        insights[metric_name] = total
                    else:
                        # Для других периодов берем последнее значение
                        insights[metric_name] = values[-1].get("value", 0)
                else:
                    insights[metric_name] = 0
            
            return insights
            
        except Exception as e:
            logger.error(f"Ошибка получения инсайтов аккаунта: {e}")
            return {
                "impressions": 0,
                "reach": 0,
                "profile_views": 0,
                "website_clicks": 0,
                "follower_count": 0
            }
    
    async def get_audience_demographics(self) -> Dict[str, Any]:
        """
        Получение демографии аудитории
        
        Returns:
            {
                "by_gender": {...},
                "by_age": {...},
                "by_country": {...},
                "by_city": {...}
            }
        """
        metrics = "audience_gender_age,audience_country,audience_city"
        
        try:
            data = await self._make_request(
                f"{self.account_id}/insights",
                params={
                    "metric": metrics,
                    "period": "lifetime"
                }
            )
            
            demographics = {
                "by_gender_age": {},
                "by_country": {},
                "by_city": {}
            }
            
            for item in data.get("data", []):
                metric_name = item.get("name")
                values = item.get("values", [{}])[0].get("value", {})
                
                if metric_name == "audience_gender_age":
                    demographics["by_gender_age"] = values
                elif metric_name == "audience_country":
                    demographics["by_country"] = values
                elif metric_name == "audience_city":
                    demographics["by_city"] = values
            
            return demographics
            
        except Exception as e:
            logger.error(f"Ошибка получения демографии: {e}")
            return {
                "by_gender_age": {},
                "by_country": {},
                "by_city": {}
            }
    
    async def get_all_metrics(
        self,
        days: int = 7,
        include_posts: bool = True,
        posts_limit: int = 10
    ) -> Dict[str, Any]:
        """
        Получение всех метрик одним запросом
        
        Returns:
            {
                "account": {...},
                "insights": {...},
                "posts": [...],
                "demographics": {...}
            }
        """
        since = datetime.now() - timedelta(days=days)
        until = datetime.now()
        
        # Получаем базовую информацию об аккаунте
        account = await self.get_account_info()
        
        # Получаем общие инсайты
        insights = await self.get_account_insights("day", since, until)
        
        # Получаем демографию
        demographics = await self.get_audience_demographics()
        
        # Получаем посты с инсайтами
        posts = []
        if include_posts:
            media_list = await self.get_media_list(posts_limit)
            
            for media in media_list:
                media_insights = await self.get_media_insights(media["id"])
                posts.append({
                    **media,
                    "insights": media_insights
                })
        
        return {
            "period": {
                "start": since.isoformat(),
                "end": until.isoformat(),
                "days": days
            },
            "account": account,
            "insights": insights,
            "posts": posts,
            "demographics": demographics
        }
