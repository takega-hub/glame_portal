from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from app.models.marketing_campaign import MarketingCampaign
from app.models.content_plan import ContentPlan
from app.services.metrics_service import MetricsService
from app.agents.marketing_agent import MarketingAgent
from uuid import UUID
import logging

logger = logging.getLogger(__name__)


class CampaignService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.metrics_service = MetricsService(db)
        self.marketing_agent = MarketingAgent(db)
    
    async def create_campaign(
        self,
        name: str,
        campaign_type: str,
        start_date: datetime,
        end_date: Optional[datetime],
        user_id: Optional[UUID] = None,
        budget: Optional[float] = None,
        target_audience: Optional[Dict[str, Any]] = None,
        channels: Optional[List[str]] = None,
        content_plan_id: Optional[UUID] = None
    ) -> MarketingCampaign:
        """Создание новой кампании"""
        campaign = MarketingCampaign(
            name=name,
            type=campaign_type,
            status="draft",
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
            budget=budget,
            target_audience=target_audience or {},
            channels=channels or [],
            content_plan_id=content_plan_id,
            metrics={}
        )
        self.db.add(campaign)
        await self.db.commit()
        await self.db.refresh(campaign)
        return campaign
    
    async def get_campaign(self, campaign_id: UUID) -> Optional[MarketingCampaign]:
        """Получение кампании по ID"""
        result = await self.db.execute(
            select(MarketingCampaign).where(MarketingCampaign.id == campaign_id)
        )
        return result.scalar_one_or_none()
    
    async def list_campaigns(
        self,
        user_id: Optional[UUID] = None,
        status: Optional[str] = None,
        campaign_type: Optional[str] = None,
        limit: int = 50
    ) -> List[MarketingCampaign]:
        """Список кампаний с фильтрами"""
        query = select(MarketingCampaign)
        
        if user_id:
            query = query.where(MarketingCampaign.user_id == user_id)
        if status:
            query = query.where(MarketingCampaign.status == status)
        if campaign_type:
            query = query.where(MarketingCampaign.type == campaign_type)
        
        query = query.order_by(MarketingCampaign.created_at.desc()).limit(limit)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())
    
    async def update_campaign_status(
        self,
        campaign_id: UUID,
        status: str
    ) -> MarketingCampaign:
        """Обновление статуса кампании"""
        campaign = await self.get_campaign(campaign_id)
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")
        
        valid_statuses = ["draft", "active", "paused", "completed", "archived"]
        if status not in valid_statuses:
            raise ValueError(f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
        
        campaign.status = status
        campaign.updated_at = datetime.now()
        await self.db.commit()
        await self.db.refresh(campaign)
        return campaign
    
    async def monitor_campaign(
        self,
        campaign_id: UUID
    ) -> Dict[str, Any]:
        """Мониторинг метрик кампании"""
        campaign = await self.get_campaign(campaign_id)
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")
        
        # Получаем метрики за период кампании
        start_date = campaign.start_date
        end_date = campaign.end_date or datetime.now()
        
        # Фильтруем по каналам кампании
        channel = campaign.channels[0] if campaign.channels else None
        
        conversion = await self.metrics_service.calculate_conversion(
            start_date, end_date, channel=channel
        )
        aov = await self.metrics_service.calculate_aov(
            start_date, end_date, channel=channel
        )
        engagement = await self.metrics_service.calculate_engagement(
            start_date, end_date
        )
        
        # Обновляем метрики в кампании
        campaign.metrics = {
            "conversion": conversion,
            "aov": aov,
            "engagement": engagement,
            "last_updated": datetime.now().isoformat()
        }
        await self.db.commit()
        
        return {
            "campaign_id": str(campaign_id),
            "status": campaign.status,
            "metrics": campaign.metrics
        }
    
    async def optimize_campaign(
        self,
        campaign_id: UUID
    ) -> Dict[str, Any]:
        """Автоматическая оптимизация кампании на основе результатов"""
        campaign = await self.get_campaign(campaign_id)
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")
        
        # Получаем анализ производительности
        analysis = await self.marketing_agent.analyze_campaign_performance(
            campaign_id=str(campaign_id),
            start_date=campaign.start_date,
            end_date=campaign.end_date or datetime.now(),
            channel=campaign.channels[0] if campaign.channels else None
        )
        
        # Если есть привязанный контент-план, оптимизируем его
        optimization = None
        if campaign.content_plan_id:
            optimization = await self.marketing_agent.optimize_content_plan(
                plan_id=str(campaign.content_plan_id),
                current_performance=analysis.get("metrics", {})
            )
        
        return {
            "campaign_id": str(campaign_id),
            "analysis": analysis,
            "optimization": optimization,
            "recommendations": analysis.get("analysis", "")
        }
    
    async def auto_start_campaigns(self):
        """Автоматический запуск кампаний, у которых наступила дата начала"""
        now = datetime.now()
        
        query = select(MarketingCampaign).where(
            and_(
                MarketingCampaign.status == "draft",
                MarketingCampaign.start_date <= now
            )
        )
        
        result = await self.db.execute(query)
        campaigns = result.scalars().all()
        
        started = []
        for campaign in campaigns:
            campaign.status = "active"
            started.append(campaign)
        
        if started:
            await self.db.commit()
            logger.info(f"Auto-started {len(started)} campaigns")
        
        return len(started)
    
    async def auto_stop_campaigns(self):
        """Автоматическая остановка кампаний, у которых прошла дата окончания"""
        now = datetime.now()
        
        query = select(MarketingCampaign).where(
            and_(
                MarketingCampaign.status == "active",
                MarketingCampaign.end_date.isnot(None),
                MarketingCampaign.end_date <= now
            )
        )
        
        result = await self.db.execute(query)
        campaigns = result.scalars().all()
        
        stopped = []
        for campaign in campaigns:
            campaign.status = "completed"
            stopped.append(campaign)
        
        if stopped:
            await self.db.commit()
            logger.info(f"Auto-stopped {len(stopped)} campaigns")
        
        return len(stopped)
