from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime, timedelta
from app.database.connection import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.marketing_campaign import MarketingCampaign
from app.services.campaign_service import CampaignService
from app.agents.marketing_agent import MarketingAgent

router = APIRouter()


class CampaignCreate(BaseModel):
    name: str
    type: str
    start_date: str  # ISO datetime
    end_date: Optional[str] = None  # ISO datetime
    budget: Optional[float] = None
    target_audience: Optional[Dict[str, Any]] = None
    channels: Optional[List[str]] = None
    content_plan_id: Optional[str] = None


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    budget: Optional[float] = None
    target_audience: Optional[Dict[str, Any]] = None
    channels: Optional[List[str]] = None


class CampaignResponse(BaseModel):
    id: str
    name: str
    type: str
    status: str
    start_date: str
    end_date: Optional[str] = None
    budget: Optional[float] = None
    target_audience: Optional[Dict[str, Any]] = None
    channels: Optional[List[str]] = None
    content_plan_id: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


def _parse_iso_datetime(dt_str: str) -> datetime:
    """Парсинг ISO datetime строки"""
    try:
        return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid datetime format: {dt_str}")


@router.post("/campaigns", response_model=CampaignResponse)
async def create_campaign(
    campaign: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Создание новой маркетинговой кампании"""
    try:
        service = CampaignService(db)
        
        new_campaign = await service.create_campaign(
            name=campaign.name,
            campaign_type=campaign.type,
            start_date=_parse_iso_datetime(campaign.start_date),
            end_date=_parse_iso_datetime(campaign.end_date) if campaign.end_date else None,
            user_id=current_user.id if current_user else None,
            budget=campaign.budget,
            target_audience=campaign.target_audience,
            channels=campaign.channels,
            content_plan_id=UUID(campaign.content_plan_id) if campaign.content_plan_id else None
        )
        
        return CampaignResponse(
            id=str(new_campaign.id),
            name=new_campaign.name,
            type=new_campaign.type,
            status=new_campaign.status,
            start_date=new_campaign.start_date.isoformat(),
            end_date=new_campaign.end_date.isoformat() if new_campaign.end_date else None,
            budget=new_campaign.budget,
            target_audience=new_campaign.target_audience,
            channels=new_campaign.channels,
            content_plan_id=str(new_campaign.content_plan_id) if new_campaign.content_plan_id else None,
            metrics=new_campaign.metrics
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating campaign: {str(e)}")


@router.get("/campaigns", response_model=List[CampaignResponse])
async def list_campaigns(
    status: Optional[str] = None,
    campaign_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Список маркетинговых кампаний"""
    try:
        service = CampaignService(db)
        campaigns = await service.list_campaigns(
            user_id=current_user.id if current_user else None,
            status=status,
            campaign_type=campaign_type
        )
        
        return [
            CampaignResponse(
                id=str(c.id),
                name=c.name,
                type=c.type,
                status=c.status,
                start_date=c.start_date.isoformat(),
                end_date=c.end_date.isoformat() if c.end_date else None,
                budget=c.budget,
                target_audience=c.target_audience,
                channels=c.channels,
                content_plan_id=str(c.content_plan_id) if c.content_plan_id else None,
                metrics=c.metrics
            )
            for c in campaigns
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing campaigns: {str(e)}")


@router.get("/campaigns/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Получение кампании по ID"""
    try:
        service = CampaignService(db)
        campaign = await service.get_campaign(campaign_id)
        
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        
        # Проверка прав доступа
        if current_user and campaign.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        if not current_user and campaign.user_id is not None:
            raise HTTPException(status_code=403, detail="Access denied")
        
        return CampaignResponse(
            id=str(campaign.id),
            name=campaign.name,
            type=campaign.type,
            status=campaign.status,
            start_date=campaign.start_date.isoformat(),
            end_date=campaign.end_date.isoformat() if campaign.end_date else None,
            budget=campaign.budget,
            target_audience=campaign.target_audience,
            channels=campaign.channels,
            content_plan_id=str(campaign.content_plan_id) if campaign.content_plan_id else None,
            metrics=campaign.metrics
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting campaign: {str(e)}")


@router.put("/campaigns/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: UUID,
    campaign_update: CampaignUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Обновление кампании"""
    try:
        service = CampaignService(db)
        campaign = await service.get_campaign(campaign_id)
        
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        
        # Проверка прав доступа
        if current_user and campaign.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        if not current_user and campaign.user_id is not None:
            raise HTTPException(status_code=403, detail="Access denied")
        
        if campaign_update.name:
            campaign.name = campaign_update.name
        if campaign_update.status:
            await service.update_campaign_status(campaign_id, campaign_update.status)
        if campaign_update.budget is not None:
            campaign.budget = campaign_update.budget
        if campaign_update.target_audience:
            campaign.target_audience = campaign_update.target_audience
        if campaign_update.channels:
            campaign.channels = campaign_update.channels
        
        campaign.updated_at = datetime.now()
        await db.commit()
        await db.refresh(campaign)
        
        return CampaignResponse(
            id=str(campaign.id),
            name=campaign.name,
            type=campaign.type,
            status=campaign.status,
            start_date=campaign.start_date.isoformat(),
            end_date=campaign.end_date.isoformat() if campaign.end_date else None,
            budget=campaign.budget,
            target_audience=campaign.target_audience,
            channels=campaign.channels,
            content_plan_id=str(campaign.content_plan_id) if campaign.content_plan_id else None,
            metrics=campaign.metrics
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating campaign: {str(e)}")


@router.post("/campaigns/{campaign_id}/analyze")
async def analyze_campaign(
    campaign_id: UUID,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Анализ эффективности кампании"""
    try:
        service = CampaignService(db)
        campaign = await service.get_campaign(campaign_id)
        
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        
        # Проверка прав доступа
        if current_user and campaign.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        agent = MarketingAgent(db)
        
        start = _parse_iso_datetime(start_date) if start_date else campaign.start_date
        end = _parse_iso_datetime(end_date) if end_date else (campaign.end_date or datetime.now())
        
        analysis = await agent.analyze_campaign_performance(
            campaign_id=str(campaign_id),
            start_date=start,
            end_date=end,
            channel=campaign.channels[0] if campaign.channels else None
        )
        
        return analysis
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing campaign: {str(e)}")


@router.post("/campaigns/{campaign_id}/optimize")
async def optimize_campaign(
    campaign_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Оптимизация кампании"""
    try:
        service = CampaignService(db)
        optimization = await service.optimize_campaign(campaign_id)
        return optimization
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error optimizing campaign: {str(e)}")


@router.get("/campaigns/{campaign_id}/monitor")
async def monitor_campaign(
    campaign_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Мониторинг метрик кампании"""
    try:
        service = CampaignService(db)
        metrics = await service.monitor_campaign(campaign_id)
        return metrics
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error monitoring campaign: {str(e)}")


@router.post("/suggest-strategy")
async def suggest_strategy(
    goal: str,
    target_audience: Optional[str] = None,
    budget: Optional[float] = None,
    timeframe: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Предложение стратегии кампании"""
    try:
        agent = MarketingAgent(db)
        strategy = await agent.suggest_campaign_strategy(
            goal=goal,
            target_audience=target_audience,
            budget=budget,
            timeframe=timeframe
        )
        return strategy
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error suggesting strategy: {str(e)}")


@router.post("/predict-engagement")
async def predict_engagement(
    content_type: str,
    channel: str,
    topic: Optional[str] = None,
    persona: Optional[str] = None,
    cjm_stage: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Предсказание вовлеченности для контента"""
    try:
        agent = MarketingAgent(db)
        prediction = await agent.predict_engagement(
            content_type=content_type,
            channel=channel,
            topic=topic,
            persona=persona,
            cjm_stage=cjm_stage
        )
        return prediction
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error predicting engagement: {str(e)}")


@router.post("/optimize-plan")
async def optimize_content_plan(
    plan_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user)
):
    """Оптимизация контент-плана"""
    try:
        agent = MarketingAgent(db)
        optimization = await agent.optimize_content_plan(plan_id=plan_id)
        return optimization
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error optimizing plan: {str(e)}")


@router.post("/campaigns/auto-start")
async def auto_start_campaigns(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Автоматический запуск кампаний (фоновый процесс)"""
    try:
        service = CampaignService(db)
        background_tasks.add_task(service.auto_start_campaigns)
        return {"status": "accepted", "message": "Auto-start task started"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting auto-start task: {str(e)}")


@router.post("/campaigns/auto-stop")
async def auto_stop_campaigns(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Автоматическая остановка кампаний (фоновый процесс)"""
    try:
        service = CampaignService(db)
        background_tasks.add_task(service.auto_stop_campaigns)
        return {"status": "accepted", "message": "Auto-stop task started"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting auto-stop task: {str(e)}")
