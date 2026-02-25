from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, case, Numeric, cast, String, text, literal
from sqlalchemy.dialects.postgresql import aggregate_order_by
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from app.models.analytics_event import AnalyticsEvent
from app.models.analytics_metric import AnalyticsMetric
from uuid import UUID
import logging

logger = logging.getLogger(__name__)


class MetricsService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def calculate_conversion(
        self,
        start_date: datetime,
        end_date: datetime,
        cjm_stage: Optional[str] = None,
        channel: Optional[str] = None
    ) -> Dict[str, Any]:
        """Расчет конверсии по этапам CJM"""
        # Подсчитываем события по типам
        query = select(
            AnalyticsEvent.event_type,
            func.count(AnalyticsEvent.id).label('count')
        ).where(
            and_(
                AnalyticsEvent.timestamp >= start_date,
                AnalyticsEvent.timestamp <= end_date
            )
        )
        
        if cjm_stage:
            # Если указан CJM этап, фильтруем по нему в event_data
            # Используем правильный синтаксис для JSONB в SQLAlchemy 2.0 через text()
            query = query.where(
                text("event_data->>'cjm_stage' = :cjm_stage").bindparams(cjm_stage=cjm_stage)
            )
        
        if channel:
            query = query.where(AnalyticsEvent.channel == channel)
        
        query = query.group_by(AnalyticsEvent.event_type)
        
        result = await self.db.execute(query)
        event_counts = {row.event_type: row.count for row in result}
        
        # Определяем конверсию на основе типов событий
        # chat_message -> product_click -> look_view -> purchase
        total_chats = event_counts.get('chat_message', 0)
        total_product_clicks = event_counts.get('product_click', 0)
        total_look_views = event_counts.get('look_view', 0)
        total_purchases = event_counts.get('purchase', 0)
        
        conversion_rates = {}
        if total_chats > 0:
            conversion_rates['chat_to_product'] = (total_product_clicks / total_chats) * 100
            conversion_rates['chat_to_look'] = (total_look_views / total_chats) * 100
            conversion_rates['chat_to_purchase'] = (total_purchases / total_chats) * 100
        
        if total_product_clicks > 0:
            conversion_rates['product_to_purchase'] = (total_purchases / total_product_clicks) * 100
        
        if total_look_views > 0:
            conversion_rates['look_to_purchase'] = (total_purchases / total_look_views) * 100
        
        return {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "events": {
                "chat_message": total_chats,
                "product_click": total_product_clicks,
                "look_view": total_look_views,
                "purchase": total_purchases
            },
            "conversion_rates": conversion_rates
        }
    
    async def calculate_aov(
        self,
        start_date: datetime,
        end_date: datetime,
        user_id: Optional[UUID] = None,
        channel: Optional[str] = None
    ) -> Dict[str, Any]:
        """Расчет среднего чека (Average Order Value)"""
        # Ищем события покупок
        # Используем правильный синтаксис для JSONB в SQLAlchemy 2.0 через text()
        query = select(
            func.sum(
                cast(text("(event_data->>'amount')::numeric"), Numeric)
            ).label('total_revenue'),
            func.count(AnalyticsEvent.id).label('order_count')
        ).where(
            and_(
                AnalyticsEvent.event_type == 'purchase',
                AnalyticsEvent.timestamp >= start_date,
                AnalyticsEvent.timestamp <= end_date
            )
        )
        
        if user_id:
            query = query.where(AnalyticsEvent.user_id == user_id)
        
        if channel:
            query = query.where(AnalyticsEvent.channel == channel)
        
        result = await self.db.execute(query)
        row = result.first()
        
        total_revenue = float(row.total_revenue) if row.total_revenue else 0.0
        order_count = row.order_count if row.order_count else 0
        
        aov = total_revenue / order_count if order_count > 0 else 0.0
        
        return {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "total_revenue": total_revenue,
            "order_count": order_count,
            "aov": aov
        }
    
    async def calculate_engagement(
        self,
        start_date: datetime,
        end_date: datetime,
        user_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Расчет вовлеченности (время на сайте, глубина просмотра)"""
        # Подсчитываем события по пользователю/сессии
        query = select(
            AnalyticsEvent.session_id,
            func.count(AnalyticsEvent.id).label('event_count'),
            func.min(AnalyticsEvent.timestamp).label('first_event'),
            func.max(AnalyticsEvent.timestamp).label('last_event')
        ).where(
            and_(
                AnalyticsEvent.timestamp >= start_date,
                AnalyticsEvent.timestamp <= end_date
            )
        )
        
        if user_id:
            query = query.where(AnalyticsEvent.user_id == user_id)
        
        query = query.group_by(AnalyticsEvent.session_id)
        
        result = await self.db.execute(query)
        sessions = result.all()
        
        total_sessions = len(sessions)
        total_events = sum(s.event_count for s in sessions)
        
        # Рассчитываем среднее время на сайте
        durations = []
        for session in sessions:
            if session.first_event and session.last_event:
                duration = (session.last_event - session.first_event).total_seconds()
                if duration > 0:
                    durations.append(duration)
        
        avg_session_duration = sum(durations) / len(durations) if durations else 0.0
        avg_events_per_session = total_events / total_sessions if total_sessions > 0 else 0.0
        
        # Глубина просмотра (количество уникальных страниц/товаров)
        unique_products_query = select(
            func.count(func.distinct(AnalyticsEvent.product_id))
        ).where(
            and_(
                AnalyticsEvent.event_type == 'product_click',
                AnalyticsEvent.timestamp >= start_date,
                AnalyticsEvent.timestamp <= end_date
            )
        )
        
        if user_id:
            unique_products_query = unique_products_query.where(AnalyticsEvent.user_id == user_id)
        
        result = await self.db.execute(unique_products_query)
        unique_products = result.scalar() or 0
        
        return {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "total_sessions": total_sessions,
            "total_events": total_events,
            "avg_session_duration_seconds": avg_session_duration,
            "avg_events_per_session": avg_events_per_session,
            "unique_products_viewed": unique_products
        }
    
    async def save_metric(
        self,
        metric_type: str,
        period: str,
        period_start: datetime,
        period_end: datetime,
        value: float,
        dimensions: Optional[Dict[str, Any]] = None
    ) -> AnalyticsMetric:
        """Сохранение предрасчитанной метрики"""
        metric = AnalyticsMetric(
            metric_type=metric_type,
            period=period,
            period_start=period_start,
            period_end=period_end,
            value=value,
            dimensions=dimensions or {}
        )
        self.db.add(metric)
        await self.db.commit()
        await self.db.refresh(metric)
        return metric
    
    async def get_metrics(
        self,
        metric_type: Optional[str] = None,
        period: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[AnalyticsMetric]:
        """Получение предрасчитанных метрик"""
        query = select(AnalyticsMetric)
        
        conditions = []
        if metric_type:
            conditions.append(AnalyticsMetric.metric_type == metric_type)
        if period:
            conditions.append(AnalyticsMetric.period == period)
        if start_date:
            conditions.append(AnalyticsMetric.period_start >= start_date)
        if end_date:
            conditions.append(AnalyticsMetric.period_end <= end_date)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        query = query.order_by(AnalyticsMetric.period_start.desc()).limit(limit)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def calculate_offline_online_comparison(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Сравнение онлайн и офлайн метрик"""
        from app.models.store_visit import StoreVisit
        from sqlalchemy import func, and_
        
        # Офлайн метрики
        offline_query = select(
            func.sum(StoreVisit.visitor_count).label('total_visitors'),
            func.sum(StoreVisit.sales_count).label('total_sales'),
            func.sum(StoreVisit.revenue).label('total_revenue')
        ).where(
            and_(
                StoreVisit.date >= start_date,
                StoreVisit.date <= end_date
            )
        )
        
        result = await self.db.execute(offline_query)
        offline_stats = result.first()
        
        offline_visitors = offline_stats.total_visitors or 0
        offline_sales = offline_stats.total_sales or 0
        offline_revenue = float(offline_stats.total_revenue) if offline_stats.total_revenue else 0.0
        
        # Онлайн метрики (из analytics_events)
        online_query = select(
            func.count(func.distinct(AnalyticsEvent.session_id)).label('unique_sessions'),
            func.sum(
                case((AnalyticsEvent.event_type == 'purchase', literal(1)), else_=literal(0))
            ).label('purchases')
        ).where(
            and_(
                AnalyticsEvent.timestamp >= start_date,
                AnalyticsEvent.timestamp <= end_date
            )
        )
        
        result = await self.db.execute(online_query)
        online_stats = result.first()
        
        online_sessions = online_stats.unique_sessions or 0
        online_purchases = online_stats.purchases or 0
        
        # Получаем онлайн revenue из событий покупок
        # Используем правильный синтаксис для JSONB в SQLAlchemy 2.0 через text()
        online_revenue_query = select(
            func.sum(
                cast(text("(event_data->>'amount')::numeric"), Numeric)
            )
        ).where(
            and_(
                AnalyticsEvent.event_type == 'purchase',
                AnalyticsEvent.timestamp >= start_date,
                AnalyticsEvent.timestamp <= end_date
            )
        )
        
        result = await self.db.execute(online_revenue_query)
        online_revenue = float(result.scalar()) if result.scalar() else 0.0
        
        total_visitors = offline_visitors + online_sessions
        total_sales = offline_sales + online_purchases
        total_revenue = offline_revenue + online_revenue
        
        return {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "offline": {
                "visitors": offline_visitors,
                "sales": offline_sales,
                "revenue": offline_revenue
            },
            "online": {
                "sessions": online_sessions,
                "purchases": online_purchases,
                "revenue": online_revenue
            },
            "total": {
                "visitors": total_visitors,
                "sales": total_sales,
                "revenue": total_revenue
            },
            "offline_share": {
                "visitors": (offline_visitors / total_visitors * 100) if total_visitors > 0 else 0.0,
                "sales": (offline_sales / total_sales * 100) if total_sales > 0 else 0.0,
                "revenue": (offline_revenue / total_revenue * 100) if total_revenue > 0 else 0.0
            }
        }
