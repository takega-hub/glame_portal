from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, case, distinct
from sqlalchemy.sql import literal
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from app.models.website_visit import WebsiteVisit
from app.models.analytics_event import AnalyticsEvent
from uuid import UUID
import logging

logger = logging.getLogger(__name__)


class WebsiteAnalyticsService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def track_visit(
        self,
        session_id: UUID,
        page_url: str,
        user_id: Optional[UUID] = None,
        referrer: Optional[str] = None,
        device_type: Optional[str] = None,
        browser: Optional[str] = None,
        duration: Optional[float] = None
    ) -> WebsiteVisit:
        """Трекинг визита на страницу"""
        # Определяем, является ли это bounce (только один просмотр страницы в сессии)
        is_bounce = 'unknown'
        if duration is not None:
            # Если длительность меньше 30 секунд и это единственный визит в сессии, считаем bounce
            visit_count_query = select(func.count(WebsiteVisit.id)).where(
                WebsiteVisit.session_id == session_id
            )
            result = await self.db.execute(visit_count_query)
            visit_count = result.scalar() or 0
            
            if visit_count == 0 and duration < 30:
                is_bounce = 'yes'
            elif visit_count > 0 or duration >= 30:
                is_bounce = 'no'
        
        visit = WebsiteVisit(
            session_id=session_id,
            user_id=user_id,
            page_url=page_url,
            referrer=referrer,
            device_type=device_type,
            browser=browser,
            duration=duration,
            is_bounce=is_bounce
        )
        self.db.add(visit)
        await self.db.commit()
        await self.db.refresh(visit)
        return visit
    
    async def analyze_visitors(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Анализ посетителей: новые/возвращающиеся"""
        # Подсчитываем уникальных пользователей
        unique_users_query = select(
            func.count(func.distinct(WebsiteVisit.user_id))
        ).where(
            and_(
                WebsiteVisit.created_at >= start_date,
                WebsiteVisit.created_at <= end_date,
                WebsiteVisit.user_id.isnot(None)
            )
        )
        result = await self.db.execute(unique_users_query)
        unique_users = result.scalar() or 0
        
        # Подсчитываем уникальные сессии
        unique_sessions_query = select(
            func.count(func.distinct(WebsiteVisit.session_id))
        ).where(
            and_(
                WebsiteVisit.created_at >= start_date,
                WebsiteVisit.created_at <= end_date
            )
        )
        result = await self.db.execute(unique_sessions_query)
        unique_sessions = result.scalar() or 0
        
        # Определяем новых и возвращающихся пользователей
        # Новый пользователь - тот, у кого первый визит в этом периоде
        new_users_query = select(
            func.count(func.distinct(WebsiteVisit.user_id))
        ).where(
            and_(
                WebsiteVisit.created_at >= start_date,
                WebsiteVisit.created_at <= end_date,
                WebsiteVisit.user_id.isnot(None)
            )
        )
        # Проверяем, есть ли у пользователя визиты до этого периода
        subquery = select(WebsiteVisit.user_id).where(
            WebsiteVisit.created_at < start_date
        ).distinct()
        
        new_users_query = select(
            func.count(func.distinct(WebsiteVisit.user_id))
        ).where(
            and_(
                WebsiteVisit.created_at >= start_date,
                WebsiteVisit.created_at <= end_date,
                WebsiteVisit.user_id.isnot(None),
                ~WebsiteVisit.user_id.in_(subquery)
            )
        )
        result = await self.db.execute(new_users_query)
        new_users = result.scalar() or 0
        
        returning_users = unique_users - new_users
        
        return {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "unique_users": unique_users,
            "unique_sessions": unique_sessions,
            "new_users": new_users,
            "returning_users": returning_users,
            "returning_rate": (returning_users / unique_users * 100) if unique_users > 0 else 0.0
        }
    
    async def analyze_pages(
        self,
        start_date: datetime,
        end_date: datetime,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Анализ страниц: популярные страницы, время на странице, bounce rate"""
        # Популярные страницы
        popular_pages_query = select(
            WebsiteVisit.page_url,
            func.count(WebsiteVisit.id).label('visits'),
            func.avg(WebsiteVisit.duration).label('avg_duration'),
            func.sum(case((WebsiteVisit.is_bounce == 'yes', literal(1)), else_=literal(0))).label('bounces')
        ).where(
            and_(
                WebsiteVisit.created_at >= start_date,
                WebsiteVisit.created_at <= end_date
            )
        ).group_by(WebsiteVisit.page_url).order_by(func.count(WebsiteVisit.id).desc()).limit(limit)
        
        result = await self.db.execute(popular_pages_query)
        pages = result.all()
        
        page_stats = []
        for page in pages:
            visits = page.visits or 0
            bounces = page.bounces or 0
            bounce_rate = (bounces / visits * 100) if visits > 0 else 0.0
            
            page_stats.append({
                "page_url": page.page_url,
                "visits": visits,
                "avg_duration_seconds": float(page.avg_duration) if page.avg_duration else 0.0,
                "bounces": bounces,
                "bounce_rate": bounce_rate
            })
        
        # Общая статистика
        total_visits_query = select(
            func.count(WebsiteVisit.id).label('total_visits'),
            func.avg(WebsiteVisit.duration).label('avg_duration'),
            func.sum(case((WebsiteVisit.is_bounce == 'yes', literal(1)), else_=literal(0))).label('total_bounces')
        ).where(
            and_(
                WebsiteVisit.created_at >= start_date,
                WebsiteVisit.created_at <= end_date
            )
        )
        
        result = await self.db.execute(total_visits_query)
        total_stats = result.first()
        
        total_visits = total_stats.total_visits or 0
        total_bounces = total_stats.total_bounces or 0
        overall_bounce_rate = (total_bounces / total_visits * 100) if total_visits > 0 else 0.0
        
        return {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "total_visits": total_visits,
            "overall_avg_duration_seconds": float(total_stats.avg_duration) if total_stats.avg_duration else 0.0,
            "overall_bounce_rate": overall_bounce_rate,
            "popular_pages": page_stats
        }
    
    async def get_visitor_segmentation(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Сегментация посетителей по поведению"""
        # По устройствам
        device_stats_query = select(
            WebsiteVisit.device_type,
            func.count(func.distinct(WebsiteVisit.session_id)).label('sessions')
        ).where(
            and_(
                WebsiteVisit.created_at >= start_date,
                WebsiteVisit.created_at <= end_date,
                WebsiteVisit.device_type.isnot(None)
            )
        ).group_by(WebsiteVisit.device_type)
        
        result = await self.db.execute(device_stats_query)
        device_stats = {row.device_type: row.sessions for row in result}
        
        # По браузерам
        browser_stats_query = select(
            WebsiteVisit.browser,
            func.count(func.distinct(WebsiteVisit.session_id)).label('sessions')
        ).where(
            and_(
                WebsiteVisit.created_at >= start_date,
                WebsiteVisit.created_at <= end_date,
                WebsiteVisit.browser.isnot(None)
            )
        ).group_by(WebsiteVisit.browser).order_by(func.count(func.distinct(WebsiteVisit.session_id)).desc()).limit(5)
        
        result = await self.db.execute(browser_stats_query)
        browser_stats = {row.browser: row.sessions for row in result}
        
        return {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "by_device": device_stats,
            "by_browser": browser_stats
        }
