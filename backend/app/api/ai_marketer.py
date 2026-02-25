"""
API AI маркетолога
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID

from app.database.connection import get_db
from app.models.user import User
from app.models.customer_segment import CustomerSegment
from app.models.user_segment import UserSegment
from app.api.dependencies import require_marketer
from app.services.ai_segmentation_service import AISegmentationService
from app.services.customer_analytics_service import CustomerAnalyticsService

logger = logging.getLogger(__name__)

router = APIRouter()


class CampaignGenerateRequest(BaseModel):
    segment_id: Optional[str] = None
    campaign_type: str  # discount, new_product, re-engagement, birthday
    campaign_goal: Optional[str] = None


@router.get("/dashboard")
async def get_dashboard(
    current_user: User = Depends(require_marketer()),
    db: AsyncSession = Depends(get_db)
):
    """Дашборд с основными метриками"""
    try:
        analytics_service = CustomerAnalyticsService(db)
        
        # Статистика по сегментам (с обработкой ошибок)
        try:
            segments_stats = await analytics_service.get_customer_segments_stats()
        except Exception as e:
            logger.error(f"Ошибка получения статистики сегментов: {e}", exc_info=True)
            segments_stats = {}
        
        # Риски оттока (с обработкой ошибок)
        try:
            churn_risk = await analytics_service.get_churn_risk()
        except Exception as e:
            logger.error(f"Ошибка получения рисков оттока: {e}", exc_info=True)
            churn_risk = {}
        
        # Топ покупатели (с обработкой ошибок)
        try:
            top_customers = await analytics_service.get_top_customers(limit=10)
        except Exception as e:
            logger.error(f"Ошибка получения топ покупателей: {e}", exc_info=True)
            top_customers = []
        
        return {
            "segments_overview": segments_stats,
            "churn_risk": churn_risk,
            "top_customers": top_customers
        }
    except Exception as e:
        logger.error(f"Ошибка получения дашборда: {e}", exc_info=True)
        # Возвращаем базовую структуру даже при ошибке
        return {
            "segments_overview": {},
            "churn_risk": {},
            "top_customers": []
        }


@router.get("/segments/analysis")
async def get_segments_analysis(
    current_user: User = Depends(require_marketer()),
    db: AsyncSession = Depends(get_db)
):
    """Детальный анализ сегментов"""
    ai_service = AISegmentationService(db)
    analytics_service = CustomerAnalyticsService(db)
    
    stmt = select(CustomerSegment).where(CustomerSegment.is_active == True)
    result = await db.execute(stmt)
    segments = result.scalars().all()
    
    analysis = []
    for segment in segments:
        # Получаем пользователей сегмента
        stmt = (
            select(User)
            .join(UserSegment)
            .where(UserSegment.segment_id == segment.id)
        )
        result = await db.execute(stmt)
        users = result.scalars().all()
        
        # Генерируем AI инсайты
        insights = await ai_service.generate_segment_insights(segment.id)
        
        # Статистика
        if users:
            avg_ltv = sum(u.total_spent for u in users) / len(users) / 100
            avg_purchases = sum(u.total_purchases for u in users) / len(users)
        else:
            avg_ltv = 0
            avg_purchases = 0
        
        analysis.append({
            "segment_id": str(segment.id),
            "name": segment.name,
            "description": segment.description,
            "size": len(users),
            "average_ltv": avg_ltv,
            "average_purchases": avg_purchases,
            "insights": insights
        })
    
    return {"segments": analysis}


@router.post("/segments/auto-generate")
async def auto_generate_segments(
    current_user: User = Depends(require_marketer()),
    db: AsyncSession = Depends(get_db)
):
    """Автоматическая сегментация AI"""
    ai_service = AISegmentationService(db)
    stats = await ai_service.auto_segment_customers()
    
    return {
        "success": True,
        "stats": stats
    }


@router.get("/customers/{user_id}/insights")
async def get_customer_insights(
    user_id: str,
    current_user: User = Depends(require_marketer()),
    db: AsyncSession = Depends(get_db)
):
    """AI инсайты по покупателю"""
    try:
        uid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат user_id")
    
    stmt = select(User).where(User.id == uid)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="Покупатель не найден")
    
    analytics_service = CustomerAnalyticsService(db)
    ai_service = AISegmentationService(db)
    
    # Предсказание следующей покупки
    next_purchase = await ai_service.predict_next_purchase(uid)
    
    # Риск оттока
    churn_risk = await analytics_service.get_churn_risk(uid)
    
    return {
        "user_id": user_id,
        "persona": user.persona,
        "customer_segment": user.customer_segment,
        "rfm_score": user.rfm_score,
        "purchase_preferences": user.purchase_preferences,
        "next_purchase_prediction": next_purchase,
        "churn_risk": churn_risk
    }


@router.post("/campaigns/generate")
async def generate_campaign(
    request: CampaignGenerateRequest,
    current_user: User = Depends(require_marketer()),
    db: AsyncSession = Depends(get_db)
):
    """Генерация персонализированной кампании"""
    # TODO: Реализовать генерацию кампаний через LLM
    # Пока возвращаем заглушку
    
    return {
        "success": True,
        "message": "Генерация кампаний будет реализована в следующей версии",
        "campaign_type": request.campaign_type
    }


@router.get("/opportunities")
async def get_opportunities(
    current_user: User = Depends(require_marketer()),
    db: AsyncSession = Depends(get_db)
):
    """AI поиск возможностей"""
    try:
        analytics_service = CustomerAnalyticsService(db)
        
        # Находим покупателей с высоким риском оттока
        churn_risk = await analytics_service.get_churn_risk()
        
        opportunities = []
        
        # Проверяем, что churn_risk не пустой и содержит нужные ключи
        if churn_risk and isinstance(churn_risk, dict):
            high_risk = churn_risk.get("high_risk", 0)
            if high_risk and high_risk > 0:
                opportunities.append({
                    "type": "re-engagement",
                    "description": f"{high_risk} VIP клиентов не покупали 90+ дней - возможна программа реактивации",
                    "customer_count": high_risk,
                    "potential_revenue": high_risk * 5000,  # Примерная оценка
                    "recommended_actions": ["Специальные скидки", "Персональные предложения"]
                })
        
        return {
            "opportunities": opportunities,
            "total": len(opportunities)
        }
    except Exception as e:
        logger.error(f"Ошибка получения возможностей: {e}", exc_info=True)
        # Возвращаем пустой список вместо ошибки 500
        return {
            "opportunities": [],
            "total": 0
        }
