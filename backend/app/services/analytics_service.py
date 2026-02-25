from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Dict, Any, Optional, List
from datetime import datetime
from app.models.analytics_event import AnalyticsEvent
from uuid import UUID


class AnalyticsService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def track_event(
        self,
        session_id: UUID,
        event_type: str,
        event_data: Dict[str, Any] = None,
        user_id: Optional[UUID] = None,
        product_id: Optional[UUID] = None,
        look_id: Optional[UUID] = None,
        content_item_id: Optional[UUID] = None,
        channel: Optional[str] = None,
        utm_source: Optional[str] = None,
        utm_medium: Optional[str] = None,
        utm_campaign: Optional[str] = None,
    ):
        """Трекинг события с расширенными полями"""
        event = AnalyticsEvent(
            session_id=session_id,
            event_type=event_type,
            event_data=event_data or {},
            user_id=user_id,
            product_id=product_id,
            look_id=look_id,
            content_item_id=content_item_id,
            channel=channel,
            utm_source=utm_source,
            utm_medium=utm_medium,
            utm_campaign=utm_campaign,
        )
        self.db.add(event)
        await self.db.commit()
    
    async def get_events(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        event_type: Optional[str] = None,
        user_id: Optional[UUID] = None,
        channel: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Получить события с фильтрами"""
        query = select(AnalyticsEvent)
        
        conditions = []
        if start_date:
            conditions.append(AnalyticsEvent.timestamp >= start_date)
        if end_date:
            conditions.append(AnalyticsEvent.timestamp <= end_date)
        if event_type:
            conditions.append(AnalyticsEvent.event_type == event_type)
        if user_id:
            conditions.append(AnalyticsEvent.user_id == user_id)
        if channel:
            conditions.append(AnalyticsEvent.channel == channel)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        query = query.order_by(AnalyticsEvent.timestamp.desc()).limit(limit).offset(offset)
        
        result = await self.db.execute(query)
        events = result.scalars().all()
        
        return {
            "total": len(events),
            "events": [
                {
                    "id": str(e.id),
                    "session_id": str(e.session_id),
                    "user_id": str(e.user_id) if e.user_id else None,
                    "event_type": e.event_type,
                    "product_id": str(e.product_id) if e.product_id else None,
                    "look_id": str(e.look_id) if e.look_id else None,
                    "content_item_id": str(e.content_item_id) if e.content_item_id else None,
                    "channel": e.channel,
                    "utm_source": e.utm_source,
                    "utm_medium": e.utm_medium,
                    "utm_campaign": e.utm_campaign,
                    "event_data": e.event_data,
                    "timestamp": e.timestamp.isoformat() if e.timestamp else None
                }
                for e in events
            ]
        }
    
    async def get_session_metrics(self, session_id: UUID) -> Dict[str, Any]:
        """Получение метрик сессии"""
        result = await self.db.execute(
            select(AnalyticsEvent).where(AnalyticsEvent.session_id == session_id)
        )
        events = result.scalars().all()
        
        event_counts = {}
        for event in events:
            event_counts[event.event_type] = event_counts.get(event.event_type, 0) + 1
        
        return {
            "total_events": len(events),
            "event_counts": event_counts,
            "events": [
                {
                    "type": e.event_type,
                    "data": e.event_data,
                    "timestamp": e.timestamp.isoformat() if e.timestamp else None
                }
                for e in events
            ]
        }
