"""
Сервис для интеграции с Telegram Bot API
Получение статистики каналов и ботов
"""
import httpx
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import os

logger = logging.getLogger(__name__)


class TelegramService:
    """Сервис для работы с Telegram Bot API"""
    
    BASE_URL = "https://api.telegram.org/bot"
    
    def __init__(
        self,
        bot_token: Optional[str] = None,
        channel_username: Optional[str] = None
    ):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.channel_username = channel_username or os.getenv("TELEGRAM_CHANNEL_USERNAME")
        
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN не настроен")
        
        self.client = httpx.AsyncClient(timeout=60.0)
        self.api_url = f"{self.BASE_URL}{self.bot_token}"
    
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
        url = f"{self.api_url}/{method}"
        
        try:
            response = await self.client.get(url, params=params or {})
            response.raise_for_status()
            data = response.json()
            
            if not data.get("ok"):
                raise Exception(f"Telegram API Error: {data.get('description')}")
            
            return data.get("result", {})
        except Exception as e:
            logger.error(f"Ошибка при запросе к Telegram API: {e}")
            raise
    
    async def get_bot_info(self) -> Dict[str, Any]:
        """Получение информации о боте"""
        data = await self._make_request("getMe")
        
        return {
            "id": data.get("id"),
            "username": data.get("username"),
            "first_name": data.get("first_name"),
            "is_bot": data.get("is_bot")
        }
    
    async def get_channel_info(self) -> Dict[str, Any]:
        """Получение информации о канале"""
        if not self.channel_username:
            return {}
        
        chat_id = f"@{self.channel_username}" if not self.channel_username.startswith("@") else self.channel_username
        
        try:
            data = await self._make_request("getChat", params={"chat_id": chat_id})
            member_count = await self._make_request("getChatMemberCount", params={"chat_id": chat_id})
            
            return {
                "id": data.get("id"),
                "title": data.get("title"),
                "username": data.get("username"),
                "type": data.get("type"),
                "description": data.get("description"),
                "member_count": member_count
            }
        except Exception as e:
            logger.error(f"Ошибка получения информации о канале: {e}")
            return {}
    
    async def get_all_metrics(self) -> Dict[str, Any]:
        """Получение всех доступных метрик"""
        bot_info = await self.get_bot_info()
        channel_info = await self.get_channel_info()
        
        return {
            "bot": bot_info,
            "channel": channel_info,
            "timestamp": datetime.now().isoformat()
        }
