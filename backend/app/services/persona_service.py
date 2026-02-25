from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, distinct
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from app.models.analytics_event import AnalyticsEvent
from app.models.user import User
from uuid import UUID
import logging

logger = logging.getLogger(__name__)


class PersonaService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def analyze_user_behavior(
        self,
        user_id: UUID,
        days: int = 90
    ) -> Dict[str, Any]:
        """Анализ поведения пользователя для определения персоны"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Получаем все события пользователя
        events_query = select(AnalyticsEvent).where(
            and_(
                AnalyticsEvent.user_id == user_id,
                AnalyticsEvent.timestamp >= start_date,
                AnalyticsEvent.timestamp <= end_date
            )
        )
        
        result = await self.db.execute(events_query)
        events = result.scalars().all()
        
        # Анализируем типы событий
        event_counts = {}
        product_clicks = []
        look_views = []
        purchases = []
        
        for event in events:
            event_type = event.event_type
            event_counts[event_type] = event_counts.get(event_type, 0) + 1
            
            if event_type == 'product_click' and event.product_id:
                product_clicks.append(event.product_id)
            elif event_type == 'look_view' and event.look_id:
                look_views.append(event.look_id)
            elif event_type == 'purchase':
                purchases.append({
                    'product_id': event.product_id,
                    'look_id': event.look_id,
                    'amount': event.event_data.get('amount', 0) if event.event_data else 0,
                    'timestamp': event.timestamp
                })
        
        # Анализируем каналы
        channels = {}
        for event in events:
            if event.channel:
                channels[event.channel] = channels.get(event.channel, 0) + 1
        
        # Определяем активность
        total_events = len(events)
        avg_events_per_day = total_events / days if days > 0 else 0
        
        # Определяем предпочтения по времени активности
        hour_distribution = {}
        for event in events:
            if event.timestamp:
                hour = event.timestamp.hour
                hour_distribution[hour] = hour_distribution.get(hour, 0) + 1
        
        peak_hour = max(hour_distribution.items(), key=lambda x: x[1])[0] if hour_distribution else None
        
        return {
            "user_id": str(user_id),
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "days": days
            },
            "activity": {
                "total_events": total_events,
                "avg_events_per_day": round(avg_events_per_day, 2),
                "event_counts": event_counts,
                "channels": channels,
                "peak_hour": peak_hour
            },
            "interactions": {
                "product_clicks": len(product_clicks),
                "unique_products": len(set(product_clicks)),
                "look_views": len(look_views),
                "unique_looks": len(set(look_views)),
                "purchases": len(purchases),
                "total_spent": sum(p.get('amount', 0) for p in purchases)
            },
            "product_ids": list(set(product_clicks)),
            "look_ids": list(set(look_views))
        }
    
    async def determine_persona(
        self,
        user_id: UUID,
        behavior_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """Определение персоны на основе поведения"""
        if not behavior_data:
            behavior_data = await self.analyze_user_behavior(user_id)
        
        # Логика определения персоны на основе поведения
        purchases = behavior_data.get("interactions", {}).get("purchases", 0)
        total_spent = behavior_data.get("interactions", {}).get("total_spent", 0)
        product_clicks = behavior_data.get("interactions", {}).get("product_clicks", 0)
        look_views = behavior_data.get("interactions", {}).get("look_views", 0)
        avg_events = behavior_data.get("activity", {}).get("avg_events_per_day", 0)
        
        # Определяем персону по паттернам поведения
        if purchases > 5 and total_spent > 50000:
            # Активный покупатель с высоким чеком
            return "status_woman"
        elif purchases > 0 and total_spent > 20000:
            # Регулярный покупатель
            return "fashion_girl"
        elif look_views > product_clicks * 2:
            # Больше просматривает образы, чем кликает по товарам - исследователь
            return "explorer"
        elif avg_events > 5:
            # Высокая активность - вовлеченный пользователь
            return "engaged_user"
        elif product_clicks > 20:
            # Много кликов по товарам, но мало покупок - сравнение
            return "comparison_shopper"
        else:
            # По умолчанию
            return "fashion_girl"
    
    async def update_user_persona(
        self,
        user_id: UUID,
        persona: Optional[str] = None
    ) -> User:
        """Обновление персоны пользователя"""
        if not persona:
            behavior_data = await self.analyze_user_behavior(user_id)
            persona = await self.determine_persona(user_id, behavior_data)
        
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        user.persona = persona
        await self.db.commit()
        await self.db.refresh(user)
        
        return user
    
    async def get_user_preferences(
        self,
        user_id: UUID,
        days: int = 90
    ) -> Dict[str, Any]:
        """Получение предпочтений пользователя на основе истории"""
        behavior_data = await self.analyze_user_behavior(user_id, days)
        
        # Анализируем предпочтения по продуктам
        from app.models.product import Product
        from app.models.look import Look
        
        product_ids = behavior_data.get("product_ids", [])
        look_ids = behavior_data.get("look_ids", [])
        
        preferences = {
            "persona": await self.determine_persona(user_id, behavior_data),
            "favorite_categories": [],
            "favorite_styles": [],
            "price_range": {
                "min": None,
                "max": None
            },
            "preferred_channels": list(behavior_data.get("activity", {}).get("channels", {}).keys())
        }
        
        # Анализируем категории просмотренных товаров
        if product_ids:
            products_query = select(Product).where(Product.id.in_(product_ids))
            products_result = await self.db.execute(products_query)
            products = products_result.scalars().all()
            
            categories = {}
            prices = []
            
            for product in products:
                if product.category:
                    categories[product.category] = categories.get(product.category, 0) + 1
                if product.price:
                    prices.append(product.price)
            
            preferences["favorite_categories"] = sorted(
                categories.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]
            
            if prices:
                preferences["price_range"] = {
                    "min": min(prices),
                    "max": max(prices)
                }
        
        # Анализируем стили просмотренных образов
        if look_ids:
            looks_query = select(Look).where(Look.id.in_(look_ids))
            looks_result = await self.db.execute(looks_query)
            looks = looks_result.scalars().all()
            
            styles = {}
            moods = {}
            
            for look in looks:
                if look.style:
                    styles[look.style] = styles.get(look.style, 0) + 1
                if look.mood:
                    moods[look.mood] = moods.get(look.mood, 0) + 1
            
            preferences["favorite_styles"] = sorted(
                styles.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]
            preferences["favorite_moods"] = sorted(
                moods.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]
        
        return preferences
