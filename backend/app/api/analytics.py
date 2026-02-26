from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime, timedelta, date
import logging
from app.database.connection import get_db
from app.services.analytics_service import AnalyticsService
from app.services.metrics_service import MetricsService
from app.services.website_analytics_service import WebsiteAnalyticsService
from app.services.yandex_metrika_service import YandexMetrikaService
from app.services.ftp_service import FTPService
from app.services.instagram_service import InstagramService
from app.services.vk_service import VKService
from app.services.telegram_service import TelegramService
from app.services.onec_sales_service import OneCSalesService
from app.services.onec_customers_service import OneCCustomersService
from app.services.onec_sales_sync_service import OneCSalesSyncService
from app.services.product_analytics_service import ProductAnalyticsService
from app.services.product_turnover_service import ProductTurnoverService
from app.services.channel_analytics_service import ChannelAnalyticsService
from app.services.website_priority_service import WebsitePriorityService
from app.services.purchase_recommendation_service import PurchaseRecommendationService
from app.services.inventory_management_service import InventoryManagementService
from app.services.purchase_recommendation_service import PurchaseRecommendationService
from app.services.demand_forecasting_service import DemandForecastingService
from app.services.onec_stock_service import OneCStockService
from app.services.stock_transfer_service import StockTransferService
from app.models.sales_record import SalesRecord

router = APIRouter()
logger = logging.getLogger(__name__)


def get_period_dates(period: str) -> tuple:
    """
    Получение дат начала и конца периода
    
    Args:
        period: Период (today, yesterday, week, month, quarter, year, custom)
    
    Returns:
        (start_date, end_date)
    """
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    if period == "today":
        return (today_start, now)
    
    elif period == "yesterday":
        yesterday_start = today_start - timedelta(days=1)
        yesterday_end = today_start - timedelta(seconds=1)
        return (yesterday_start, yesterday_end)
    
    elif period == "week":
        # Текущая неделя (понедельник - сегодня)
        days_since_monday = now.weekday()
        week_start = today_start - timedelta(days=days_since_monday)
        return (week_start, now)
    
    elif period == "month":
        # Текущий месяц
        month_start = today_start.replace(day=1)
        return (month_start, now)
    
    elif period == "quarter":
        # Текущий квартал
        current_quarter = (now.month - 1) // 3
        quarter_start_month = current_quarter * 3 + 1
        quarter_start = today_start.replace(month=quarter_start_month, day=1)
        return (quarter_start, now)
    
    elif period == "year":
        # Текущий год
        year_start = today_start.replace(month=1, day=1)
        return (year_start, now)
    
    else:
        # По умолчанию - последние 30 дней
        return (today_start - timedelta(days=30), now)


class TrackEventRequest(BaseModel):
    session_id: str
    event_type: str
    event_data: Dict[str, Any] = {}
    user_id: Optional[str] = None
    product_id: Optional[str] = None
    look_id: Optional[str] = None
    content_item_id: Optional[str] = None
    channel: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None


@router.post("/track")
async def track_event(request: TrackEventRequest, db: AsyncSession = Depends(get_db)):
    """Трекинг события с расширенными полями"""
    try:
        service = AnalyticsService(db)
        await service.track_event(
            session_id=UUID(request.session_id),
            event_type=request.event_type,
            event_data=request.event_data,
            user_id=UUID(request.user_id) if request.user_id else None,
            product_id=UUID(request.product_id) if request.product_id else None,
            look_id=UUID(request.look_id) if request.look_id else None,
            content_item_id=UUID(request.content_item_id) if request.content_item_id else None,
            channel=request.channel,
            utm_source=request.utm_source,
            utm_medium=request.utm_medium,
            utm_campaign=request.utm_campaign,
        )
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid UUID format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error tracking event: {str(e)}")


@router.get("/events")
async def get_events(
    start_date: Optional[str] = Query(None, description="ISO datetime format"),
    end_date: Optional[str] = Query(None, description="ISO datetime format"),
    event_type: Optional[str] = None,
    user_id: Optional[str] = None,
    channel: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """Получить события с фильтрами"""
    try:
        service = AnalyticsService(db)
        events = await service.get_events(
            start_date=datetime.fromisoformat(start_date.replace('Z', '+00:00')) if start_date else None,
            end_date=datetime.fromisoformat(end_date.replace('Z', '+00:00')) if end_date else None,
            event_type=event_type,
            user_id=UUID(user_id) if user_id else None,
            channel=channel,
            limit=limit,
            offset=offset
        )
        return events
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date or UUID format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting events: {str(e)}")


@router.get("/session/{session_id}")
async def get_session_metrics(session_id: str, db: AsyncSession = Depends(get_db)):
    """Получить метрики сессии"""
    try:
        service = AnalyticsService(db)
        metrics = await service.get_session_metrics(UUID(session_id))
        return metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting metrics: {str(e)}")


@router.get("/dashboard")
async def get_dashboard(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    db: AsyncSession = Depends(get_db)
):
    """Основные метрики для dashboard"""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        metrics_service = MetricsService(db)
        analytics_service = AnalyticsService(db)
        
        # Получаем основные метрики
        conversion = await metrics_service.calculate_conversion(start_date, end_date)
        aov = await metrics_service.calculate_aov(start_date, end_date)
        engagement = await metrics_service.calculate_engagement(start_date, end_date)
        
        # Подсчитываем общее количество событий
        events_result = await analytics_service.get_events(
            start_date=start_date,
            end_date=end_date,
            limit=1
        )
        
        # Получаем события по типам для статистики
        events_by_type = {}
        events = await analytics_service.get_events(
            start_date=start_date,
            end_date=end_date,
            limit=10000
        )
        
        for event in events.get("events", []):
            event_type = event.get("event_type")
            if event_type:
                events_by_type[event_type] = events_by_type.get(event_type, 0) + 1
        
        return {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "days": days
            },
            "conversion": conversion,
            "aov": aov,
            "engagement": engagement,
            "events_by_type": events_by_type,
            "total_events": sum(events_by_type.values())
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting dashboard metrics: {str(e)}")


@router.get("/conversion")
async def get_conversion(
    start_date: Optional[str] = Query(None, description="ISO datetime format"),
    end_date: Optional[str] = Query(None, description="ISO datetime format"),
    days: int = Query(30, ge=1, le=365),
    cjm_stage: Optional[str] = None,
    channel: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Конверсия по этапам CJM"""
    try:
        if start_date and end_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end = datetime.now()
            start = end - timedelta(days=days)
        
        metrics_service = MetricsService(db)
        result = await metrics_service.calculate_conversion(start, end, cjm_stage, channel)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating conversion: {str(e)}")


@router.get("/aov")
async def get_aov(
    start_date: Optional[str] = Query(None, description="ISO datetime format"),
    end_date: Optional[str] = Query(None, description="ISO datetime format"),
    days: int = Query(30, ge=1, le=365),
    user_id: Optional[str] = None,
    channel: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Средний чек (Average Order Value)"""
    try:
        if start_date and end_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end = datetime.now()
            start = end - timedelta(days=days)
        
        metrics_service = MetricsService(db)
        result = await metrics_service.calculate_aov(
            start, end,
            user_id=UUID(user_id) if user_id else None,
            channel=channel
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date or UUID format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating AOV: {str(e)}")


@router.get("/engagement")
async def get_engagement(
    start_date: Optional[str] = Query(None, description="ISO datetime format"),
    end_date: Optional[str] = Query(None, description="ISO datetime format"),
    days: int = Query(30, ge=1, le=365),
    user_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Вовлеченность (время на сайте, глубина просмотра)"""
    try:
        if start_date and end_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end = datetime.now()
            start = end - timedelta(days=days)
        
        metrics_service = MetricsService(db)
        result = await metrics_service.calculate_engagement(
            start, end,
            user_id=UUID(user_id) if user_id else None
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date or UUID format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating engagement: {str(e)}")


@router.get("/content-performance")
async def get_content_performance(
    start_date: Optional[str] = Query(None, description="ISO datetime format"),
    end_date: Optional[str] = Query(None, description="ISO datetime format"),
    days: int = Query(30, ge=1, le=365),
    content_item_id: Optional[str] = None,
    channel: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Анализ результатов постинга контент-агентом"""
    try:
        if start_date and end_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end = datetime.now()
            start = end - timedelta(days=days)
        
        analytics_service = AnalyticsService(db)
        
        # Получаем события, связанные с контентом
        query_conditions = {
            "start_date": start,
            "end_date": end
        }
        
        if content_item_id:
            query_conditions["content_item_id"] = UUID(content_item_id)
        
        # Получаем все события за период
        events = await analytics_service.get_events(
            start_date=start,
            end_date=end,
            channel=channel,
            limit=10000
        )
        
        # Фильтруем события, связанные с контентом
        content_events = []
        for event in events.get("events", []):
            if event.get("content_item_id"):
                if not content_item_id or event.get("content_item_id") == content_item_id:
                    content_events.append(event)
        
        # Группируем по content_item_id
        performance_by_item = {}
        for event in content_events:
            item_id = event.get("content_item_id")
            if item_id:
                if item_id not in performance_by_item:
                    performance_by_item[item_id] = {
                        "content_item_id": item_id,
                        "events": [],
                        "event_counts": {},
                        "channels": set()
                    }
                performance_by_item[item_id]["events"].append(event)
                event_type = event.get("event_type")
                performance_by_item[item_id]["event_counts"][event_type] = \
                    performance_by_item[item_id]["event_counts"].get(event_type, 0) + 1
                if event.get("channel"):
                    performance_by_item[item_id]["channels"].add(event.get("channel"))
        
        # Преобразуем sets в lists для JSON
        for item_id, data in performance_by_item.items():
            data["channels"] = list(data["channels"])
            data["total_events"] = len(data["events"])
        
        return {
            "period": {
                "start": start.isoformat(),
                "end": end.isoformat()
            },
            "total_content_events": len(content_events),
            "performance_by_item": list(performance_by_item.values())
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date or UUID format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting content performance: {str(e)}")


@router.post("/track-visit")
async def track_visit(
    session_id: str,
    page_url: str,
    user_id: Optional[str] = None,
    referrer: Optional[str] = None,
    device_type: Optional[str] = None,
    browser: Optional[str] = None,
    duration: Optional[float] = None,
    db: AsyncSession = Depends(get_db)
):
    """Трекинг визита на страницу"""
    try:
        service = WebsiteAnalyticsService(db)
        visit = await service.track_visit(
            session_id=UUID(session_id),
            page_url=page_url,
            user_id=UUID(user_id) if user_id else None,
            referrer=referrer,
            device_type=device_type,
            browser=browser,
            duration=duration
        )
        return {
            "status": "success",
            "visit_id": str(visit.id)
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid UUID format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error tracking visit: {str(e)}")


@router.get("/visitors")
async def get_visitor_analysis(
    start_date: Optional[str] = Query(None, description="ISO datetime format"),
    end_date: Optional[str] = Query(None, description="ISO datetime format"),
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db)
):
    """Анализ посетителей: новые/возвращающиеся"""
    try:
        if start_date and end_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end = datetime.now()
            start = end - timedelta(days=days)
        
        service = WebsiteAnalyticsService(db)
        result = await service.analyze_visitors(start, end)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing visitors: {str(e)}")


@router.get("/pages")
async def get_page_analysis(
    start_date: Optional[str] = Query(None, description="ISO datetime format"),
    end_date: Optional[str] = Query(None, description="ISO datetime format"),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """Анализ страниц: популярные страницы, время на странице, bounce rate"""
    try:
        if start_date and end_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end = datetime.now()
            start = end - timedelta(days=days)
        
        service = WebsiteAnalyticsService(db)
        result = await service.analyze_pages(start, end, limit)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing pages: {str(e)}")


@router.get("/offline-online-comparison")
async def get_offline_online_comparison(
    start_date: Optional[str] = Query(None, description="ISO datetime format"),
    end_date: Optional[str] = Query(None, description="ISO datetime format"),
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db)
):
    """Сравнение онлайн и офлайн метрик"""
    try:
        if start_date and end_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end = datetime.now()
            start = end - timedelta(days=days)
        
        metrics_service = MetricsService(db)
        result = await metrics_service.calculate_offline_online_comparison(start, end)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error comparing offline/online metrics: {str(e)}")


# =========================
# Яндекс.Метрика endpoints
# =========================

@router.post("/yandex-metrika/sync")
async def sync_yandex_metrika(
    days: int = Query(30, ge=1, le=365, description="Количество дней для синхронизации"),
    db: AsyncSession = Depends(get_db)
):
    """
    Синхронизация данных из Яндекс.Метрики
    
    Получает метрики за указанный период и сохраняет в БД
    """
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        async with YandexMetrikaService() as ym_service:
            # Получаем все метрики
            metrics = await ym_service.get_all_metrics(start_date, end_date)
            
            # Сохраняем в analytics_events
            analytics_service = AnalyticsService(db)
            
            # Создаем сессию для метрик (или используем существующую)
            # Для упрощения создаем UUID сессии на основе даты
            import uuid
            session_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"yandex_metrika_{start_date.date()}")
            
            # Сохраняем основные метрики как события
            await analytics_service.track_event(
                session_id=session_id,
                event_type="yandex_metrika_sync",
                event_data=metrics,
                channel="yandex_metrika",
                utm_source="yandex_metrika"
            )
            
            return {
                "status": "success",
                "message": "Данные успешно синхронизированы",
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                },
                "metrics": metrics
            }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Ошибка конфигурации: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка синхронизации: {str(e)}")


@router.get("/yandex-metrika/metrics")
async def get_yandex_metrika_metrics(
    start_date: Optional[str] = Query(None, description="ISO datetime format"),
    end_date: Optional[str] = Query(None, description="ISO datetime format"),
    days: int = Query(30, ge=1, le=365, description="Количество дней (если не указаны даты)"),
    metric_type: Optional[str] = Query(None, description="Тип метрики: visits, sources, behavior, ecommerce, demographics")
):
    """
    Получение метрик из Яндекс.Метрики
    
    Параметры:
    - start_date, end_date: Период для получения метрик
    - days: Количество дней (альтернатива датам)
    - metric_type: Тип метрики для получения (опционально, по умолчанию все)
    """
    try:
        if start_date and end_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end = datetime.now()
            start = end - timedelta(days=days)
        
        async with YandexMetrikaService() as ym_service:
            if metric_type == "visits":
                result = await ym_service.get_visits_metrics(start, end)
            elif metric_type == "sources":
                result = await ym_service.get_traffic_sources(start, end)
            elif metric_type == "behavior":
                result = await ym_service.get_behavior_metrics(start, end)
            elif metric_type == "ecommerce":
                result = await ym_service.get_ecommerce_metrics(start, end)
            elif metric_type == "demographics":
                result = await ym_service.get_demographics(start, end)
            else:
                # Получаем все метрики
                result = await ym_service.get_all_metrics(start, end)
            
            return {
                "status": "success",
                "period": {
                    "start": start.isoformat(),
                    "end": end.isoformat()
                },
                "data": result
            }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Ошибка конфигурации или неверный формат даты: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения метрик: {str(e)}")


# =========================
# FTP счетчики магазинов endpoints
# =========================

class FTPSyncRequest(BaseModel):
    filename: Optional[str] = None
    pattern: Optional[str] = None
    format_hint: Optional[str] = None
    ftp_host: str
    ftp_username: str
    ftp_password: str
    ftp_directory: str = "/"


@router.post("/ftp/sync")
async def sync_ftp_store_visits(
    request: FTPSyncRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Синхронизация данных счетчиков магазинов через FTP
    
    Параметры:
    - filename: Конкретный файл для загрузки (опционально)
    - pattern: Паттерн для поиска файлов (например, "visits_*.csv")
    - format_hint: Подсказка о формате ('csv', 'json', 'xml', 'text')
    - ftp_host: Хост FTP сервера
    - ftp_username: Имя пользователя
    - ftp_password: Пароль
    - ftp_directory: Директория на FTP сервере
    """
    from app.models.store_visit import StoreVisit
    from app.models.store import Store
    from sqlalchemy import select
    
    try:
        # Подключаемся к FTP
        ftp_service = FTPService(
            host=request.ftp_host,
            username=request.ftp_username,
            password=request.ftp_password,
            directory=request.ftp_directory
        )
        
        # Получаем данные
        visits_data = ftp_service.sync_store_visits_from_ftp(
            filename=request.filename,
            pattern=request.pattern,
            format_hint=request.format_hint
        )
        
        ftp_service.disconnect()
        
        # Сохраняем в БД
        created_count = 0
        updated_count = 0
        errors = []
        
        for visit_data in visits_data:
            try:
                store_id = visit_data.get('store_id')
                date = visit_data.get('date')
                
                # Ищем магазин по названию или external_id
                store = None
                if store_id:
                    # Сначала пробуем найти по названию (YALTA, CENTRUM и т.д.)
                    result = await db.execute(
                        select(Store).where(Store.name == str(store_id))
                    )
                    store = result.scalar_one_or_none()
                    
                    # Если не нашли по названию, пробуем по external_id (UUID из 1С)
                    if not store:
                        result = await db.execute(
                            select(Store).where(Store.external_id == str(store_id))
                        )
                        store = result.scalar_one_or_none()
                
                if not store:
                    # Создаем placeholder для магазина
                    store = Store(
                        name=str(store_id),
                        is_active=True
                    )
                    db.add(store)
                    await db.flush()
                
                # Проверяем существующую запись
                result = await db.execute(
                    select(StoreVisit).where(
                        StoreVisit.store_id == store.id,
                        StoreVisit.date == date
                    )
                )
                existing_visit = result.scalar_one_or_none()
                
                if existing_visit:
                    # Обновляем
                    existing_visit.visitor_count = visit_data.get('visitor_count', 0)
                    existing_visit.sales_count = visit_data.get('sales_count', 0)
                    existing_visit.revenue = visit_data.get('revenue', 0.0)
                    updated_count += 1
                else:
                    # Создаем новую запись
                    new_visit = StoreVisit(
                        store_id=store.id,
                        date=date,
                        visitor_count=visit_data.get('visitor_count', 0),
                        sales_count=visit_data.get('sales_count', 0),
                        revenue=visit_data.get('revenue', 0.0)
                    )
                    db.add(new_visit)
                    created_count += 1
                
            except Exception as e:
                errors.append(f"Ошибка обработки записи {visit_data}: {str(e)}")
                continue
        
        await db.commit()
        
        return {
            "status": "success",
            "message": "Данные успешно синхронизированы",
            "stats": {
                "total_records": len(visits_data),
                "created": created_count,
                "updated": updated_count,
                "errors": len(errors)
            },
            "errors": errors if errors else None
        }
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка синхронизации: {str(e)}")


def _run_store_visits_sync() -> tuple[bool, str]:
    """
    Запуск синхронизации данных счетчиков посещаемости с FTP и запись в БД.
    Возвращает (success, message).
    """
    import subprocess
    import sys
    from pathlib import Path

    project_root = Path(__file__).parent.parent.parent.parent
    script_path = project_root / "sync_ftp_stores.py"
    if not script_path.exists():
        return False, f"Скрипт синхронизации не найден: {script_path}"

    try:
        logger.info("Starting store visits sync from FTP")
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
        if result.returncode == 0:
            logger.info("Store visits sync finished successfully")
            return True, result.stdout or "Синхронизация посещаемости выполнена"
        error_msg = result.stderr or "Неизвестная ошибка"
        logger.warning(f"Store visits sync failed: {error_msg}")
        return False, error_msg
    except subprocess.TimeoutExpired:
        logger.warning("Store visits sync timed out")
        return False, "Синхронизация посещаемости превысила время ожидания"
    except Exception as e:
        logger.warning(f"Store visits sync error: {e}", exc_info=True)
        return False, str(e)


@router.post("/store-visits/sync")
async def sync_store_visits_manual(db: AsyncSession = Depends(get_db)):
    """
    Принудительная синхронизация данных счетчиков магазинов с FTP
    
    Запускает синхронизацию посещаемости вручную
    """
    success, message = _run_store_visits_sync()
    if success:
        return {"status": "success", "message": "Синхронизация посещаемости выполнена успешно", "output": message}
    raise HTTPException(status_code=500, detail=message)


@router.get("/stores")
async def get_stores(
    include_warehouse: bool = Query(False, description="Включать основной склад"),
    db: AsyncSession = Depends(get_db)
):
    """
    Получение списка магазинов для продаж
    
    Args:
        include_warehouse: Если True, включает "Основной склад" в список
    
    Returns:
        Список магазинов с их ID, external_id (UUID из 1С) и названиями
        Исключает склады и дубликаты (показывает только магазины с external_id)
    """
    from app.models.store import Store
    
    try:
        # Получаем только активные магазины с external_id (UUID из 1С)
        conditions = [
            Store.is_active == True,
            Store.external_id.isnot(None),  # Только магазины с UUID из 1С
        ]
        
        if not include_warehouse:
            # Исключаем склады (названия содержат "склад" или "Основной склад")
            conditions.append(~Store.name.ilike("%склад%"))
            conditions.append(~Store.name.ilike("%Основной%"))
        
        result = await db.execute(
            select(Store)
            .where(and_(*conditions))
            .order_by(Store.name)
        )
        stores = result.scalars().all()
        
        # Убираем дубликаты по external_id (оставляем первую запись)
        seen_external_ids = set()
        unique_stores = []
        for store in stores:
            if store.external_id not in seen_external_ids:
                seen_external_ids.add(store.external_id)
                unique_stores.append(store)
        
        return {
            "status": "success",
            "stores": [
                {
                    "id": str(store.id),
                    "external_id": store.external_id,  # UUID из 1С
                    "name": store.name,
                    "city": store.city,
                    "is_active": store.is_active
                }
                for store in unique_stores
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения магазинов: {str(e)}")


@router.get("/ftp/status")
async def get_ftp_sync_status(
    store_id: Optional[str] = Query(None, description="ID магазина (опционально)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Получение статуса синхронизации данных счетчиков магазинов
    
    Args:
        store_id: ID конкретного магазина (если не указан - все магазины)
    
    Returns:
        Статистика по магазинам и посещениям
    """
    from app.models.store_visit import StoreVisit
    from app.models.store import Store
    from sqlalchemy import func, select, and_
    
    try:
        # Базовый запрос для посещений
        visit_query = select(StoreVisit)
        if store_id:
            visit_query = visit_query.where(StoreVisit.store_id == store_id)
        
        # Общее количество магазинов
        total_stores = (await db.execute(
            select(func.count()).select_from(Store)
        )).scalar_one()
        
        # Активные магазины
        active_stores = (await db.execute(
            select(func.count()).select_from(Store).where(Store.is_active == True)
        )).scalar_one()
        
        # Всего записей о посещениях
        total_visits = (await db.execute(
            select(func.count()).select_from(visit_query.subquery())
        )).scalar_one()
        
        # Последняя синхронизация
        last_visit_query = select(StoreVisit).order_by(StoreVisit.created_at.desc()).limit(1)
        if store_id:
            last_visit_query = last_visit_query.where(StoreVisit.store_id == store_id)
        
        last_visit = (await db.execute(last_visit_query)).scalar_one_or_none()
        
        # Статистика за последние 30 дней
        thirty_days_ago = datetime.now() - timedelta(days=30)
        stats_query = select(
            func.sum(StoreVisit.visitor_count).label('total_visitors'),
            func.sum(StoreVisit.sales_count).label('total_sales'),
            func.sum(StoreVisit.revenue).label('total_revenue')
        ).where(StoreVisit.date >= thirty_days_ago)
        
        if store_id:
            stats_query = stats_query.where(StoreVisit.store_id == store_id)
        
        recent_stats = (await db.execute(stats_query)).first()
        
        return {
            "total_stores": total_stores,
            "active_stores": active_stores,
            "total_visit_records": total_visits,
            "last_sync": last_visit.created_at.isoformat() if last_visit else None,
            "store_id": store_id,
            "last_30_days": {
                "total_visitors": int(recent_stats.total_visitors or 0),
                "total_sales": int(recent_stats.total_sales or 0),
                "total_revenue": float(recent_stats.total_revenue or 0.0)
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения статуса: {str(e)}")


@router.get("/store-visits/daily")
async def get_store_visits_daily(
    days: int = Query(30, ge=1, le=90, description="Количество дней"),
    store_id: Optional[str] = Query(None, description="ID магазина (опционально)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Получение статистики посещений магазинов по дням
    
    Args:
        days: Количество дней для анализа
        store_id: ID конкретного магазина (если не указан - все магазины)
    
    Returns:
        Детальная статистика по дням с сравнением
    """
    from app.models.store_visit import StoreVisit
    from app.models.store import Store
    from sqlalchemy import func, and_
    
    try:
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        
        # Для сравнения берем предыдущий период
        comparison_start = start_date - timedelta(days=days)
        comparison_end = start_date - timedelta(days=1)
        
        # Базовый запрос
        query = select(
            StoreVisit.date,
            Store.name.label('store_name'),
            func.sum(StoreVisit.visitor_count).label('visitors'),
            func.sum(StoreVisit.sales_count).label('sales'),
            func.sum(StoreVisit.revenue).label('revenue')
        ).join(Store, StoreVisit.store_id == Store.id)
        
        # Фильтр по магазину: та же логика, что в метриках (1c-sales) — по имени и алиасам FTP (CENTRUM, YALTA),
        # чтобы график посещаемости показывал те же данные, что и карточка «Посещаемость»
        selected_store_name = None
        if store_id and store_id != "all":
            try:
                if isinstance(store_id, str) and len(store_id) == 36 and store_id.count("-") == 4:
                    store_by_id = await db.execute(select(Store.name).where(Store.id == UUID(store_id)).limit(1))
                    row = store_by_id.scalar_one_or_none()
                    if row is not None:
                        selected_store_name = row if isinstance(row, str) else row[0]
            except (ValueError, TypeError):
                pass
            if selected_store_name is None:
                store_query = await db.execute(
                    select(Store.name).where(
                        or_(Store.external_id == store_id, Store.name == store_id)
                    ).limit(1)
                )
                row = store_query.scalar_one_or_none()
                if row is not None:
                    selected_store_name = row if isinstance(row, str) else row[0]
            if selected_store_name:
                names_to_match = [selected_store_name]
                store_name_lower = selected_store_name.lower()
                if "центрум" in store_name_lower or "centrum" in store_name_lower:
                    names_to_match.append("CENTRUM")
                if "ялта" in store_name_lower or "yalta" in store_name_lower:
                    names_to_match.append("YALTA")
                query = query.where(Store.name.in_(names_to_match))
        
        # Текущий период
        current_query = query.where(
            and_(StoreVisit.date >= start_date, StoreVisit.date <= end_date)
        ).group_by(StoreVisit.date, Store.name).order_by(StoreVisit.date)
        
        current_result = await db.execute(current_query)
        current_data = current_result.all()
        
        # Предыдущий период для сравнения
        comparison_query = query.where(
            and_(StoreVisit.date >= comparison_start, StoreVisit.date <= comparison_end)
        ).group_by(StoreVisit.date, Store.name).order_by(StoreVisit.date)
        
        comparison_result = await db.execute(comparison_query)
        comparison_data = comparison_result.all()
        
        # Агрегируем данные по дням (все магазины вместе)
        daily_stats = {}
        for row in current_data:
            date_str = row.date.isoformat()
            if date_str not in daily_stats:
                daily_stats[date_str] = {
                    'date': date_str,
                    'visitors': 0,
                    'sales': 0,
                    'revenue': 0.0,
                    'stores': []
                }
            daily_stats[date_str]['visitors'] += int(row.visitors or 0)
            daily_stats[date_str]['sales'] += int(row.sales or 0)
            daily_stats[date_str]['revenue'] += float(row.revenue or 0.0)
            daily_stats[date_str]['stores'].append({
                'name': row.store_name,
                'visitors': int(row.visitors or 0),
                'sales': int(row.sales or 0),
                'revenue': float(row.revenue or 0.0)
            })
        
        # Статистика предыдущего периода
        comparison_total = sum(int(row.visitors or 0) for row in comparison_data)
        current_total = sum(int(row.visitors or 0) for row in current_data)
        
        # Процент изменения
        change_percent = 0
        if comparison_total > 0:
            change_percent = ((current_total - comparison_total) / comparison_total) * 100
        
        return {
            "status": "success",
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "days": days
            },
            "comparison_period": {
                "start": comparison_start.isoformat(),
                "end": comparison_end.isoformat()
            },
            "summary": {
                "current_total": current_total,
                "previous_total": comparison_total,
                "change": current_total - comparison_total,
                "change_percent": round(change_percent, 2)
            },
            "daily_data": sorted(daily_stats.values(), key=lambda x: x['date']),
            "stores": list(set(row.store_name for row in current_data))
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения статистики: {str(e)}")


# =========================
# Instagram endpoints
# =========================

@router.post("/instagram/sync")
async def sync_instagram(
    days: int = Query(7, ge=1, le=30, description="Количество дней для синхронизации"),
    include_posts: bool = Query(True, description="Включить статистику постов"),
    posts_limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db)
):
    """Синхронизация данных из Instagram"""
    from app.models.social_media_metric import SocialMediaMetric
    
    try:
        async with InstagramService() as ig_service:
            metrics = await ig_service.get_all_metrics(days, include_posts, posts_limit)
            
            # Сохраняем метрики аккаунта
            account_metric = SocialMediaMetric(
                platform="instagram",
                metric_type="account",
                date=datetime.now(),
                value=metrics["account"]["followers_count"],
                likes=None,
                comments=None,
                meta_data={
                    "account": metrics["account"],
                    "insights": metrics["insights"],
                    "demographics": metrics["demographics"]
                }
            )
            db.add(account_metric)
            
            # Сохраняем метрики постов
            for post in metrics.get("posts", []):
                post_metric = SocialMediaMetric(
                    platform="instagram",
                    metric_type="post",
                    post_id=post["id"],
                    date=datetime.fromisoformat(post["timestamp"].replace("Z", "+00:00")),
                    value=post["insights"].get("engagement", 0),
                    likes=post["insights"].get("likes", 0),
                    comments=post["insights"].get("comments", 0),
                    views=post["insights"].get("impressions", 0),
                    reach=post["insights"].get("reach", 0),
                    engagement=post["insights"].get("engagement", 0),
                    meta_data={
                        "caption": post.get("caption", "")[:500],
                        "media_type": post.get("media_type"),
                        "permalink": post.get("permalink")
                    }
                )
                db.add(post_metric)
            
            await db.commit()
            
            return {
                "status": "success",
                "message": "Instagram данные синхронизированы",
                "stats": {
                    "account_metrics": 1,
                    "post_metrics": len(metrics.get("posts", []))
                },
                "data": metrics
            }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Ошибка конфигурации: {str(e)}")
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка синхронизации: {str(e)}")


@router.get("/instagram/metrics")
async def get_instagram_metrics(
    days: int = Query(7, ge=1, le=90),
    metric_type: Optional[str] = Query(None, description="account, post, story"),
    db: AsyncSession = Depends(get_db)
):
    """Получение метрик Instagram из БД"""
    from app.models.social_media_metric import SocialMediaMetric
    from sqlalchemy import select, and_
    
    try:
        since = datetime.now() - timedelta(days=days)
        
        query = select(SocialMediaMetric).where(
            and_(
                SocialMediaMetric.platform == "instagram",
                SocialMediaMetric.date >= since
            )
        )
        
        if metric_type:
            query = query.where(SocialMediaMetric.metric_type == metric_type)
        
        query = query.order_by(SocialMediaMetric.date.desc())
        
        result = await db.execute(query)
        metrics = result.scalars().all()
        
        return {
            "status": "success",
            "period": {"start": since.isoformat(), "end": datetime.now().isoformat()},
            "total": len(metrics),
            "metrics": [
                {
                    "id": str(m.id),
                    "metric_type": m.metric_type,
                    "post_id": m.post_id,
                    "date": m.date.isoformat(),
                    "value": m.value,
                    "likes": m.likes,
                    "comments": m.comments,
                    "views": m.views,
                    "reach": m.reach,
                    "engagement": m.engagement,
                    "metadata": m.meta_data
                }
                for m in metrics
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения метрик: {str(e)}")


# =========================
# ВКонтакте endpoints
# =========================

@router.post("/vk/sync")
async def sync_vk(days: int = Query(7, ge=1, le=30), db: AsyncSession = Depends(get_db)):
    """Синхронизация данных из ВКонтакте"""
    from app.models.social_media_metric import SocialMediaMetric
    
    try:
        async with VKService() as vk_service:
            metrics = await vk_service.get_all_metrics(days)
            
            # Сохраняем метрики сообщества
            group_metric = SocialMediaMetric(
                platform="vk",
                metric_type="group",
                date=datetime.now(),
                value=metrics["group"]["members_count"],
                reach=metrics["stats"].get("reach", 0),
                meta_data=metrics
            )
            db.add(group_metric)
            
            # Сохраняем метрики постов
            for post in metrics.get("posts", []):
                post_metric = SocialMediaMetric(
                    platform="vk",
                    metric_type="post",
                    post_id=str(post["id"]),
                    date=post["date"],
                    likes=post["likes"],
                    comments=post["comments"],
                    shares=post["reposts"],
                    views=post["views"],
                    meta_data={"text": post["text"][:500]}
                )
                db.add(post_metric)
            
            await db.commit()
            
            return {"status": "success", "data": metrics}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vk/metrics")
async def get_vk_metrics(days: int = Query(7), db: AsyncSession = Depends(get_db)):
    """Получение метрик ВКонтакте из БД"""
    from app.models.social_media_metric import SocialMediaMetric
    from sqlalchemy import select, and_
    
    since = datetime.now() - timedelta(days=days)
    result = await db.execute(
        select(SocialMediaMetric).where(
            and_(
                SocialMediaMetric.platform == "vk",
                SocialMediaMetric.date >= since
            )
        ).order_by(SocialMediaMetric.date.desc())
    )
    metrics = result.scalars().all()
    
    return {
        "status": "success",
        "total": len(metrics),
        "metrics": [
            {
                "id": str(m.id),
                "metric_type": m.metric_type,
                "date": m.date.isoformat(),
                "likes": m.likes,
                "comments": m.comments,
                "shares": m.shares,
                "views": m.views,
                "reach": m.reach
            }
            for m in metrics
        ]
    }


# =========================
# Telegram endpoints
# =========================

@router.post("/telegram/sync")
async def sync_telegram(db: AsyncSession = Depends(get_db)):
    """Синхронизация данных из Telegram"""
    from app.models.social_media_metric import SocialMediaMetric
    
    try:
        async with TelegramService() as tg_service:
            metrics = await tg_service.get_all_metrics()
            
            # Сохраняем метрики канала
            if metrics.get("channel"):
                channel_metric = SocialMediaMetric(
                    platform="telegram",
                    metric_type="channel",
                    date=datetime.now(),
                    value=metrics["channel"].get("member_count", 0),
                    meta_data=metrics
                )
                db.add(channel_metric)
                await db.commit()
            
            return {"status": "success", "data": metrics}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/telegram/metrics")
async def get_telegram_metrics(days: int = Query(7), db: AsyncSession = Depends(get_db)):
    """Получение метрик Telegram из БД"""
    from app.models.social_media_metric import SocialMediaMetric
    from sqlalchemy import select, and_
    
    since = datetime.now() - timedelta(days=days)
    result = await db.execute(
        select(SocialMediaMetric).where(
            and_(
                SocialMediaMetric.platform == "telegram",
                SocialMediaMetric.date >= since
            )
        ).order_by(SocialMediaMetric.date.desc())
    )
    metrics = result.scalars().all()
    
    return {
        "status": "success",
        "total": len(metrics),
        "metrics": [{"id": str(m.id), "metric_type": m.metric_type, "date": m.date.isoformat(), "value": m.value} for m in metrics]
    }


# =========================
# 1С Статистика продаж endpoints
# =========================

class OneCUploadRequest(BaseModel):
    file_content: str
    file_format: str = "json"

@router.post("/1c-sales/sync")
async def sync_1c_sales(
    period: Optional[str] = Query(None, description="Период: today, yesterday, week, month, quarter, year"),
    start_date: Optional[str] = Query(None, description="Начальная дата (ISO format)"),
    end_date: Optional[str] = Query(None, description="Конечная дата (ISO format)"),
    days: int = Query(30, ge=1, le=365, description="Количество дней назад (если не указан период)"),
    incremental: bool = Query(True, description="Инкрементальная синхронизация (только новые данные)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Синхронизация продаж из 1С в БД.
    После синхронизации продаж автоматически обновляет данные счетчиков посещаемости по всем магазинам (FTP) и записывает их в БД.

    Поддерживает:
    - Периоды: today, yesterday, week, month, quarter, year
    - Индивидуальный диапазон дат (start_date, end_date)
    - Инкрементальную синхронизацию (только новые данные)
    - Полную синхронизацию (перезапись существующих)
    """
    import asyncio
    try:
        # Определяем период
        if period:
            start, end = get_period_dates(period)
        elif start_date and end_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end = datetime.now()
            start = end - timedelta(days=days)

        # Используем новый сервис синхронизации
        async with OneCSalesSyncService(db) as sync_service:
            result = await sync_service.sync_period(
                start_date=start,
                end_date=end,
                incremental=incremental
            )

            logger.info(f"Синхронизация продаж завершена: {result}")

            # При каждой синхронизации продаж обновляем данные счетчиков посещаемости по всем магазинам и пишем в БД
            visits_ok, visits_msg = await asyncio.get_event_loop().run_in_executor(
                None, _run_store_visits_sync
            )
            result["store_visits_synced"] = visits_ok
            result["store_visits_message"] = visits_msg
            if not visits_ok:
                logger.warning(f"Синхронизация посещаемости после продаж: {visits_msg}")

            return {
                "status": "success",
                "message": "Синхронизация успешно завершена" + (
                    "; посещаемость обновлена." if visits_ok else "; посещаемость не обновлена (см. store_visits_message)."
                ),
                **result
            }
    except Exception as e:
        await db.rollback()
        logger.error(f"Ошибка синхронизации продаж: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/1c-sales/sync/file")
async def sync_1c_sales_file(
    request: OneCUploadRequest,
    db: AsyncSession = Depends(get_db)
):
    """Синхронизация статистики продаж из файла"""
    from app.models.sales_metric import SalesMetric
    
    try:
        content = request.file_content.encode('utf-8')
        
        sales_service = OneCSalesService()
        sales_data = sales_service.parse_sales_from_file(content, request.file_format)
        metrics = sales_service.calculate_metrics(sales_data)
        
        # Сохраняем метрики
        sales_metric = SalesMetric(
            date=datetime.now(),
            revenue=metrics["total_revenue"],
            order_count=metrics["order_count"],
            items_sold=metrics["items_sold"],
            average_order_value=metrics["average_order_value"],
            meta_data={
                "by_channel": metrics["by_channel"],
                "by_store": metrics["by_store"]
            }
        )
        db.add(sales_metric)
        await db.commit()
        
        return {"status": "success", "metrics": metrics}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/1c-sales/by-store")
async def get_1c_sales_by_store(
    period: Optional[str] = Query(None, description="Период: today, yesterday, week, month, quarter, year"),
    start_date: Optional[str] = Query(None, description="Начальная дата (ISO format)"),
    end_date: Optional[str] = Query(None, description="Конечная дата (ISO format)"),
    days: int = Query(30, ge=1, le=365),
    include_today_online: bool = Query(True, description="Включать онлайн данные за сегодня"),
    db: AsyncSession = Depends(get_db)
):
    """Получение статистики продаж по магазинам с поддержкой периодов"""
    from app.models.sales_metric import SalesMetric
    from app.models.store import Store
    
    # Определяем период
    if period:
        start, end = get_period_dates(period)
    elif start_date and end_date:
        start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
    else:
        end = datetime.now()
        start = end - timedelta(days=days)
    
    # Получаем данные из БД
    query_end = end
    today_online_data = None
    if include_today_online and end.date() == datetime.now().date():
        query_end = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)
        try:
            async with OneCSalesSyncService(db) as sync_service:
                today_online_data = await sync_service.sync_today_online()
        except Exception as e:
            logger.warning(f"Не удалось получить онлайн данные за сегодня: {e}")
    
    result = await db.execute(
        select(SalesMetric)
        .where(
            and_(
                SalesMetric.date >= start,
                SalesMetric.date <= query_end
            )
        )
        .order_by(SalesMetric.date.desc())
    )
    metrics = result.scalars().all()
    
    # Получаем названия магазинов из базы данных
    stores_query = await db.execute(select(Store.external_id, Store.name))
    store_names = {row[0]: row[1] for row in stores_query.all() if row[0]}
    
    # Группируем по магазинам
    stores = {}
    total_revenue = 0.0
    total_orders = 0
    total_items = 0
    
    for m in metrics:
        if m.meta_data and "by_store" in m.meta_data:
            store_data = m.meta_data["by_store"]
            for store_id, store_metrics in store_data.items():
                if store_id == "unknown" or not store_id:
                    continue
                if store_id not in stores:
                    stores[store_id] = {
                        "store_id": store_id,
                        "store_name": store_names.get(store_id, store_id),  # Используем название из БД или UUID
                        "revenue": 0.0,
                        "orders": 0,
                        "items_sold": 0,
                        "average_order_value": 0.0
                    }
                stores[store_id]["revenue"] += store_metrics.get("revenue", 0.0)
                stores[store_id]["orders"] += store_metrics.get("orders", 0)
                stores[store_id]["items_sold"] += store_metrics.get("items_sold", 0)
                total_revenue += store_metrics.get("revenue", 0.0)
                total_orders += store_metrics.get("orders", 0)
                total_items += store_metrics.get("items_sold", 0)
    
    # Добавляем данные из онлайн запроса за сегодня
    if today_online_data:
        today_by_store = today_online_data.get("metrics", {}).get("by_store", {})
        for store_id, store_data in today_by_store.items():
            if store_id not in stores:
                stores[store_id] = {
                    "store_id": store_id,
                    "store_name": store_names.get(store_id, store_id),  # Используем название из БД или UUID
                    "revenue": 0.0,
                    "orders": 0,
                    "items_sold": 0,
                    "average_order_value": 0.0
                }
            stores[store_id]["revenue"] += store_data.get("revenue", 0.0)
            stores[store_id]["orders"] += store_data.get("orders", 0)
            stores[store_id]["items_sold"] += store_data.get("items_sold", 0)
            total_revenue += store_data.get("revenue", 0.0)
            total_orders += store_data.get("orders", 0)
            total_items += store_data.get("items_sold", 0)
    
    # Рассчитываем средний чек для каждого магазина
    for store_id, store_data in stores.items():
        if store_data["orders"] > 0:
            store_data["average_order_value"] = store_data["revenue"] / store_data["orders"]
    
    # Сортируем по выручке
    stores_list = sorted(stores.values(), key=lambda x: x["revenue"], reverse=True)
    
    return {
        "status": "success",
        "period": {
            "start": start.isoformat(),
            "end": end.isoformat()
        },
        "total_stores": len(stores_list),
        "total_revenue": total_revenue,
        "total_orders": total_orders,
        "total_items": total_items,
        "stores": stores_list
    }


async def _check_missing_sales_data(
    db: AsyncSession,
    start: datetime,
    end: datetime,
    store_1c_key: Optional[str] = None
) -> bool:
    """
    Проверяет, есть ли данные о продажах в БД за указанный период
    
    Returns:
        True если данных нет (нужна синхронизация), False если данные есть
    """
    from app.models.sales_record import SalesRecord
    
    query = select(func.count(SalesRecord.id)).where(
        and_(
            SalesRecord.sale_date >= start,
            SalesRecord.sale_date <= end
        )
    )
    
    if store_1c_key:
        query = query.where(SalesRecord.store_id == store_1c_key)
    
    result = await db.execute(query)
    count = result.scalar() or 0
    
    # Если данных нет или очень мало (меньше 1 записи на день в среднем), считаем что данных нет
    days_diff = (end - start).days + 1
    return count < days_diff


@router.get("/1c-sales/daily")
async def get_1c_sales_daily(
    period: Optional[str] = Query(None, description="Период: today, yesterday, week, month, quarter, year"),
    start_date: Optional[str] = Query(None, description="Начальная дата (ISO format)"),
    end_date: Optional[str] = Query(None, description="Конечная дата (ISO format)"),
    days: int = Query(30, ge=1, le=365),
    store_id: Optional[str] = Query(None, description="ID магазина (UUID) для фильтрации"),
    include_today_online: bool = Query(True, description="Включать онлайн данные за сегодня"),
    auto_sync: bool = Query(True, description="Автоматически синхронизировать если данных нет"),
    db: AsyncSession = Depends(get_db)
):
    """
    Получение статистики продаж по дням для графика
    
    Получает данные из детальных записей SalesRecord с группировкой по дням.
    Поддерживает фильтрацию по магазину.
    
    Для сегодняшних данных делает онлайн запрос к 1С, если include_today_online=True
    """
    from app.models.sales_record import SalesRecord
    from app.models.store import Store
    from collections import defaultdict
    
    # Определяем период
    if period:
        start, end = get_period_dates(period)
    elif start_date and end_date:
        start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
    else:
        end = datetime.now()
        start = end - timedelta(days=days)
    
    # Если указан store_id, получаем его 1C ключ (external_id) из таблицы stores
    store_1c_key = None
    if store_id:
        try:
            from app.models.store import Store
            store_result = await db.execute(
                select(Store).where(Store.id == store_id)
            )
            store = store_result.scalar_one_or_none()
            if store and store.external_id:
                # Используем external_id (1C ключ) для фильтрации
                store_1c_key = store.external_id
            elif store:
                # Если external_id не задан, пробуем использовать UUID как строку
                # (на случай, если в 1С используется UUID магазина)
                store_1c_key = str(store.id)
        except Exception as e:
            logger.warning(f"Не удалось получить магазин {store_id}: {e}")
    
    # Проверяем наличие данных и синхронизируем при необходимости
    if auto_sync:
        # Для проверки используем период без сегодня (если сегодня включен, он будет получен онлайн)
        check_end = end
        if include_today_online and end.date() == datetime.now().date():
            check_end = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)
        
        is_missing = await _check_missing_sales_data(db, start, check_end, store_1c_key)
        if is_missing:
            logger.info(f"Данные за период {start.date()} - {check_end.date()} отсутствуют, запускаем синхронизацию...")
            try:
                # Используем отдельную сессию для синхронизации, чтобы не нарушать текущую транзакцию
                from app.database.connection import AsyncSessionLocal
                async with AsyncSessionLocal() as sync_db:
                    try:
                        async with OneCSalesSyncService(sync_db) as sync_service:
                            await sync_service.sync_period(
                                start_date=start,
                                end_date=check_end,
                                incremental=True
                            )
                        await sync_db.commit()
                        logger.info("Синхронизация завершена")
                    except Exception as sync_error:
                        await sync_db.rollback()
                        raise sync_error
            except Exception as e:
                logger.warning(f"Ошибка при автоматической синхронизации: {e}", exc_info=True)
                # Продолжаем работу даже если синхронизация не удалась
    
    # Получаем данные из детальных записей SalesRecord (исключая сегодня, если нужны онлайн данные)
    query_end = end
    if include_today_online and end.date() == datetime.now().date():
        # Исключаем сегодня из запроса к БД, получим онлайн
        query_end = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)
    
    # Запрос к SalesRecord с группировкой по дням
    query = select(
        func.date(SalesRecord.sale_date).label('sale_date'),
        func.sum(SalesRecord.revenue).label('revenue'),
        func.count(func.distinct(SalesRecord.document_id)).label('orders'),
        func.sum(SalesRecord.quantity).label('items_sold')
    ).where(
        and_(
            SalesRecord.sale_date >= start,
            SalesRecord.sale_date <= query_end
        )
    )
    
    # Фильтр по магазину, если указан
    # В SalesRecord store_id - это строка (1C ключ Склад_Key)
    if store_1c_key:
        query = query.where(SalesRecord.store_id == store_1c_key)
    
    query = query.group_by(func.date(SalesRecord.sale_date)).order_by(func.date(SalesRecord.sale_date).asc())
    
    result = await db.execute(query)
    sales_rows = result.all()
    
    # Группируем по дням
    daily_sales = defaultdict(lambda: {"revenue": 0.0, "orders": 0, "items_sold": 0.0})
    
    for row in sales_rows:
        date_key = row.sale_date.isoformat()
        daily_sales[date_key]["revenue"] += float(row.revenue or 0.0)
        daily_sales[date_key]["orders"] += int(row.orders or 0)
        daily_sales[date_key]["items_sold"] += float(row.items_sold or 0.0)
    
    # Если нужны онлайн данные за сегодня
    if include_today_online and end.date() == datetime.now().date():
        try:
            async with OneCSalesSyncService(db) as sync_service:
                today_data = await sync_service.sync_today_online()
                today_orders = today_data.get("orders", [])
                
                # Фильтруем по магазину, если указан
                if store_1c_key:
                    today_orders = [
                        order for order in today_orders 
                        if order.get("store_id") == store_1c_key
                    ]
                
                # Группируем по дням
                today_key = datetime.now().date().isoformat()
                today_revenue = sum(order.get("revenue", 0.0) for order in today_orders)
                today_orders_count = len(set(order.get("external_id") or order.get("id") for order in today_orders))
                today_items = sum(order.get("items_count", 0.0) for order in today_orders)
                
                daily_sales[today_key] = {
                    "revenue": today_revenue,
                    "orders": today_orders_count,
                    "items_sold": today_items
                }
        except Exception as e:
            logger.warning(f"Не удалось получить онлайн данные за сегодня: {e}")
    
    # Формируем массив данных для графика
    daily_data = []
    current_date = start.date()
    end_date_obj = end.date()
    
    while current_date <= end_date_obj:
        date_key = current_date.isoformat()
        day_data = daily_sales.get(date_key, {"revenue": 0.0, "orders": 0, "items_sold": 0.0})
        daily_data.append({
            "date": date_key,
            "revenue": round(day_data["revenue"], 2),
            "orders": day_data["orders"],
            "items_sold": round(day_data["items_sold"], 0)
        })
        current_date += timedelta(days=1)
    
    return {
        "status": "success",
        "period": {
            "start": start.isoformat(),
            "end": end.isoformat()
        },
        "daily_data": daily_data
    }


async def _check_missing_sales_metrics(
    db: AsyncSession,
    start: datetime,
    end: datetime,
    use_detailed_records: bool
) -> bool:
    """
    Проверяет, есть ли данные о продажах в БД за указанный период
    
    Returns:
        True если данных нет (нужна синхронизация), False если данные есть
    """
    from app.models.sales_record import SalesRecord
    from app.models.sales_metric import SalesMetric
    
    if use_detailed_records:
        # Проверяем SalesRecord
        result = await db.execute(
            select(func.count(SalesRecord.id)).where(
                and_(
                    SalesRecord.sale_date >= start,
                    SalesRecord.sale_date <= end
                )
            )
        )
        count = result.scalar() or 0
    else:
        # Проверяем SalesMetric
        result = await db.execute(
            select(func.count(SalesMetric.id)).where(
                and_(
                    SalesMetric.date >= start,
                    SalesMetric.date <= end
                )
            )
        )
        count = result.scalar() or 0
    
    # Если данных нет, считаем что нужна синхронизация
    return count == 0


@router.get("/1c-sales/metrics")
async def get_1c_sales_metrics(
    period: Optional[str] = Query(None, description="Период: today, yesterday, week, month, quarter, year"),
    start_date: Optional[str] = Query(None, description="Начальная дата (ISO format)"),
    end_date: Optional[str] = Query(None, description="Конечная дата (ISO format)"),
    days: int = Query(30, ge=1, le=365),
    store_id: Optional[str] = Query(None, description="Фильтр по магазину (UUID)"),
    auto_sync: bool = Query(True, description="Автоматически синхронизировать если данных нет"),
    db: AsyncSession = Depends(get_db)
):
    """
    Получение статистики продаж из БД с поддержкой периодов
    
    Все данные берутся из таблицы SalesRecord (синхронизируются из 1С API отдельно)
    """
    from app.models.sales_record import SalesRecord
    from app.models.sales_metric import SalesMetric
    from app.models.store import Store
    
    # Определяем период
    if period:
        start, end = get_period_dates(period)
    elif start_date and end_date:
        start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
    else:
        end = datetime.now()
        start = end - timedelta(days=days)
    
    # Для длительных периодов и прошлых периодов (месяц, квартал, год, вчера) используем SalesRecord для точности
    # Для "today" также используем SalesRecord, чтобы получить актуальные данные
    # Для "yesterday" используем SalesRecord, так как данные должны быть уже синхронизированы
    use_detailed_records = period in ["month", "quarter", "year", "yesterday", "today"] or (start_date and end_date)
    
    # Проверяем наличие данных и синхронизируем при необходимости
    if auto_sync:
        is_missing = await _check_missing_sales_metrics(db, start, end, use_detailed_records)
        if is_missing:
            logger.info(f"Данные за период {start.date()} - {end.date()} отсутствуют, запускаем синхронизацию...")
            try:
                # Используем отдельную сессию для синхронизации, чтобы не нарушать текущую транзакцию
                from app.database.connection import AsyncSessionLocal
                async with AsyncSessionLocal() as sync_db:
                    try:
                        async with OneCSalesSyncService(sync_db) as sync_service:
                            await sync_service.sync_period(
                                start_date=start,
                                end_date=end,
                                incremental=True
                            )
                        await sync_db.commit()
                        logger.info("Синхронизация завершена")
                    except Exception as sync_error:
                        await sync_db.rollback()
                        raise sync_error
            except Exception as e:
                logger.warning(f"Ошибка при автоматической синхронизации: {e}", exc_info=True)
                # Продолжаем работу даже если синхронизация не удалась
    
    if use_detailed_records:
        # Базовое условие для фильтрации
        base_where = and_(
            SalesRecord.sale_date >= start,
            SalesRecord.sale_date <= end
        )
        
        # Фильтр по магазину
        if store_id and store_id != "all":
            base_where = and_(base_where, SalesRecord.store_id == store_id)
        
        # Получаем общие данные (включая упаковку для выручки)
        # Важно: исключаем NULL document_id при подсчете чеков
        orders_where = and_(base_where, SalesRecord.document_id.isnot(None))
        result = await db.execute(
            select(
                func.sum(SalesRecord.revenue).label('total_revenue'),
                func.count(func.distinct(SalesRecord.document_id)).label('total_orders'),  # Исправлено: используем document_id для подсчета чеков
                func.sum(SalesRecord.quantity).label('total_items')
            )
            .where(base_where)
        )
        # Отдельный запрос для подсчета чеков (без NULL)
        orders_result = await db.execute(
            select(
                func.count(func.distinct(SalesRecord.document_id)).label('total_orders')
            )
            .where(orders_where)
        )
        row = result.first()
        orders_row = orders_result.first()
        
        # Получаем количество товаров без упаковки (цена за единицу >= 3 рубля)
        items_without_packaging_where = and_(
            base_where,
            SalesRecord.quantity > 0,
            SalesRecord.revenue / SalesRecord.quantity >= 3.0
        )
        
        items_result = await db.execute(
            select(
                func.sum(SalesRecord.quantity).label('items_without_packaging')
            )
            .where(items_without_packaging_where)
        )
        items_row = items_result.first()
        
        total_revenue = float(row.total_revenue or 0.0)
        total_orders = int(orders_row.total_orders or 0)  # Используем подсчет без NULL
        total_items_without_packaging = int(float(items_row.items_without_packaging or 0.0))
        avg_order_value = total_revenue / total_orders if total_orders > 0 else 0.0
        
        aggregated = {
            "total_revenue": total_revenue,
            "total_orders": total_orders,
            "total_items": total_items_without_packaging,  # Без упаковки
            "average_order_value": avg_order_value
        }
        
        # Получаем названия магазинов из базы данных
        stores_query = await db.execute(select(Store.external_id, Store.name))
        store_names = {row[0]: row[1] for row in stores_query.all() if row[0]}
        
        # Получаем данные по магазинам из SalesRecord
        by_store = {}
        store_base_where = and_(
            SalesRecord.sale_date >= start,
            SalesRecord.sale_date <= end,
            SalesRecord.store_id.isnot(None)
        )
        
        # Если фильтр по магазину, применяем его
        if store_id and store_id != "all":
            store_base_where = and_(store_base_where, SalesRecord.store_id == store_id)
        
        # Общие метрики по магазинам (включая упаковку для выручки)
        # Исключаем NULL document_id при подсчете чеков
        store_orders_where = and_(store_base_where, SalesRecord.document_id.isnot(None))
        store_result = await db.execute(
            select(
                SalesRecord.store_id,
                func.sum(SalesRecord.revenue).label('revenue'),
                func.count(func.distinct(SalesRecord.document_id)).label('orders')  # Исправлено: используем document_id для подсчета чеков
            )
            .where(store_orders_where)
            .group_by(SalesRecord.store_id)
        )
        
        # Метрики по товарам без упаковки
        items_without_packaging_where = and_(
            store_base_where,
            SalesRecord.quantity > 0,
            SalesRecord.revenue / SalesRecord.quantity >= 3.0
        )
        
        items_by_store_result = await db.execute(
            select(
                SalesRecord.store_id,
                func.sum(SalesRecord.quantity).label('items_sold')
            )
            .where(items_without_packaging_where)
            .group_by(SalesRecord.store_id)
        )
        
        # Создаем словарь для быстрого доступа к количеству товаров
        items_by_store = {row.store_id: int(float(row.items_sold or 0.0)) for row in items_by_store_result.all()}
        
        for store_row in store_result.all():
            if store_row.store_id and store_row.store_id != "unknown":
                store_revenue = float(store_row.revenue or 0.0)
                store_orders = int(store_row.orders or 0)
                store_items = items_by_store.get(store_row.store_id, 0)
                store_avg_order = store_revenue / store_orders if store_orders > 0 else 0.0
                
                by_store[store_row.store_id] = {
                    "store_name": store_names.get(store_row.store_id, store_row.store_id),
                    "revenue": store_revenue,
                    "orders": store_orders,
                    "items_sold": store_items,  # Без упаковки
                    "average_order_value": store_avg_order
                }
        
        # Получаем данные по каналам из SalesRecord
        by_channel = {}
        channel_base_where = and_(
            SalesRecord.sale_date >= start,
            SalesRecord.sale_date <= end
        )
        if store_id and store_id != "all":
            channel_base_where = and_(channel_base_where, SalesRecord.store_id == store_id)
        # Исключаем NULL document_id при подсчете чеков
        channel_orders_where = and_(channel_base_where, SalesRecord.document_id.isnot(None))
        channel_result = await db.execute(
            select(
                SalesRecord.channel,
                func.sum(SalesRecord.revenue).label('revenue'),
                func.count(func.distinct(SalesRecord.document_id)).label('orders'),  # Исправлено: используем document_id для подсчета чеков
                func.sum(SalesRecord.quantity).label('items_sold')
            )
            .where(
                and_(
                    SalesRecord.sale_date >= start,
                    SalesRecord.sale_date <= end,
                    SalesRecord.channel.isnot(None)
                )
            )
            .group_by(SalesRecord.channel)
        )
        for channel_row in channel_result.all():
            if channel_row.channel and channel_row.channel != "unknown":
                by_channel[channel_row.channel] = {
                    "revenue": float(channel_row.revenue or 0.0),
                    "orders": int(channel_row.orders or 0),
                    "items_sold": int(float(channel_row.items_sold or 0.0))
                }
        
        metrics = []  # Для детальных записей не используем SalesMetric
    else:
        # Используем агрегированные метрики из SalesMetric для коротких периодов
        result = await db.execute(
            select(SalesMetric)
            .where(
                and_(
                    SalesMetric.date >= start,
                    SalesMetric.date <= end
                )
            )
            .order_by(SalesMetric.date.desc())
        )
        metrics = result.scalars().all()
        
        # Получаем названия магазинов из базы данных
        stores_query = await db.execute(select(Store.external_id, Store.name))
        store_names = {row[0]: row[1] for row in stores_query.all() if row[0]}
        
        # Группируем по магазинам из meta_data
        by_store = {}
        for m in metrics:
            if m.meta_data and "by_store" in m.meta_data:
                store_data = m.meta_data["by_store"]
                for store_id_key, store_metrics in store_data.items():
                    if store_id_key == "unknown" or not store_id_key:
                        continue
                    # Фильтр по магазину
                    if store_id and store_id != "all" and store_id_key != store_id:
                        continue
                    if store_id_key not in by_store:
                        by_store[store_id_key] = {
                            "store_name": store_names.get(store_id_key, store_id_key),  # Используем название из БД или UUID
                            "revenue": 0.0,
                            "orders": 0,
                            "items_sold": 0
                        }
                    by_store[store_id_key]["revenue"] += store_metrics.get("revenue", 0.0)
                    by_store[store_id_key]["orders"] += store_metrics.get("orders", 0)
                    by_store[store_id_key]["items_sold"] += store_metrics.get("items_sold", 0)
        
        # Если фильтр по магазину, используем данные только этого магазина
        if store_id and store_id != "all":
            if store_id in by_store:
                store_data = by_store[store_id]
                # Исправление: значения перепутаны в meta_data, поэтому меняем местами
                aggregated = {
                    "total_revenue": store_data["revenue"],
                    "total_orders": store_data["items_sold"],  # В meta_data items_sold на самом деле количество чеков
                    "total_items": store_data["orders"],  # В meta_data orders на самом деле количество товаров
                    "average_order_value": 0.0
                }
            else:
                # Магазин не найден в метриках, получаем из SalesRecord
                base_where = and_(
                    SalesRecord.sale_date >= start,
                    SalesRecord.sale_date <= end,
                    SalesRecord.store_id == store_id
                )
                
                result = await db.execute(
                    select(
                        func.sum(SalesRecord.revenue).label('total_revenue'),
                        func.count(func.distinct(SalesRecord.document_id)).label('total_orders'),  # Исправлено: используем document_id для подсчета чеков
                        func.sum(SalesRecord.quantity).label('total_items')
                    )
                    .where(base_where)
                )
                row = result.first()
                
                # Получаем количество товаров без упаковки
                items_without_packaging_where = and_(
                    base_where,
                    SalesRecord.quantity > 0,
                    SalesRecord.revenue / SalesRecord.quantity >= 3.0
                )
                
                items_result = await db.execute(
                    select(
                        func.sum(SalesRecord.quantity).label('items_without_packaging')
                    )
                    .where(items_without_packaging_where)
                )
                items_row = items_result.first()
                
                total_revenue = float(row.total_revenue or 0.0)
                total_orders = int(row.total_orders or 0)
                total_items_without_packaging = int(float(items_row.items_without_packaging or 0.0))
                avg_order_value = total_revenue / total_orders if total_orders > 0 else 0.0
                
                aggregated = {
                    "total_revenue": total_revenue,
                    "total_orders": total_orders,
                    "total_items": total_items_without_packaging,
                    "average_order_value": avg_order_value
                }
        else:
            # Агрегируем метрики за период из БД (все магазины)
            aggregated = {
                "total_revenue": sum(m.revenue for m in metrics),
                "total_orders": sum(m.order_count for m in metrics),
                "total_items": sum(m.items_sold for m in metrics),
                "average_order_value": 0.0
            }
            
            # Пересчитываем количество товаров без упаковки из SalesRecord
            base_where = and_(
                SalesRecord.sale_date >= start,
                SalesRecord.sale_date <= end
            )
            
            items_without_packaging_where = and_(
                base_where,
                SalesRecord.quantity > 0,
                SalesRecord.revenue / SalesRecord.quantity >= 3.0
            )
            
            items_result = await db.execute(
                select(
                    func.sum(SalesRecord.quantity).label('items_without_packaging')
                )
                .where(items_without_packaging_where)
            )
            items_row = items_result.first()
            aggregated["total_items"] = int(float(items_row.items_without_packaging or 0.0))
        
        # Группируем по каналам из meta_data
        by_channel = {}
        for m in metrics:
            if m.meta_data and "by_channel" in m.meta_data:
                channel_data = m.meta_data["by_channel"]
                for channel_id, channel_metrics in channel_data.items():
                    if channel_id == "unknown" or not channel_id:
                        continue
                    if channel_id not in by_channel:
                        by_channel[channel_id] = {
                            "revenue": 0.0,
                            "orders": 0,
                            "items_sold": 0
                        }
                    by_channel[channel_id]["revenue"] += channel_metrics.get("revenue", 0.0)
                    by_channel[channel_id]["orders"] += channel_metrics.get("orders", 0)
                    by_channel[channel_id]["items_sold"] += channel_metrics.get("items_sold", 0)
    
    if aggregated["total_orders"] > 0:
        aggregated["average_order_value"] = aggregated["total_revenue"] / aggregated["total_orders"]
    
    # Получаем данные о посещаемости магазинов
    from app.models.store_visit import StoreVisit
    from sqlalchemy.orm import aliased
    
    total_visitors = 0
    visitors_by_store = {}
    
    try:
        # Определяем даты для запроса посещаемости (только дата, без времени)
        start_date_only = start.date() if isinstance(start, datetime) else start
        end_date_only = end.date() if isinstance(end, datetime) else end
        
        # Используем JOIN с таблицей stores для получения названий магазинов
        # Счетчики привязаны к названиям магазинов (YALTA, CENTRUM), а не к UUID из 1С
        visit_query = select(
            Store.name.label('store_name'),
            Store.external_id,
            func.sum(StoreVisit.visitor_count).label('total_visitors')
        ).join(
            Store, StoreVisit.store_id == Store.id
        ).where(
            and_(
                func.date(StoreVisit.date) >= start_date_only,
                func.date(StoreVisit.date) <= end_date_only
            )
        )
        
        # Фильтр по магазину (если указан external_id из 1С, находим магазин и учитываем альясные названия из FTP)
        selected_store_name = None
        if store_id and store_id != "all":
            store_query = await db.execute(
                select(Store.name).where(
                    or_(
                        Store.external_id == store_id,
                        Store.name == store_id
                    )
                )
            )
            selected_store_name = store_query.scalar()
            if selected_store_name:
                # Счетчики FTP пишутся под именами CENTRUM, YALTA; в 1С магазины могут называться "Центрум 2", "Ялта" и т.д.
                # Добавляем альясные названия, чтобы при выборе магазина из списка показывалась посещаемость
                names_to_match = [selected_store_name]
                store_name_lower = selected_store_name.lower()
                if "центрум" in store_name_lower or "centrum" in store_name_lower:
                    names_to_match.append("CENTRUM")
                if "ялта" in store_name_lower or "yalta" in store_name_lower:
                    names_to_match.append("YALTA")
                visit_query = visit_query.where(Store.name.in_(names_to_match))
        
        visit_query = visit_query.group_by(Store.name, Store.external_id)
        visit_result = await db.execute(visit_query)
        visit_rows = visit_result.all()
        
        logger.info(f"Найдено записей о посещаемости: {len(visit_rows)}")
        for row in visit_rows:
            store_name = row.store_name
            store_external_id = row.external_id
            visitors_count = int(row.total_visitors or 0)
            total_visitors += visitors_count
            
            logger.info(f"Store Name: {store_name}, External ID: {store_external_id}, Visitors: {visitors_count}")
            
            # Маппим по external_id, если он есть, иначе по названию
            # Счетчики привязаны к названиям магазинов (YALTA, CENTRUM), а не к UUID из 1С
            if store_external_id:
                visitors_by_store[store_external_id] = {
                    "visitor_count": visitors_count,
                    "store_name": store_name
                }
            # Всегда добавляем по названию (для магазинов без external_id)
            if store_name:
                visitors_by_store[store_name] = {
                    "visitor_count": visitors_count,
                    "store_name": store_name
                }
            
            # Если фильтр по магазину и нет external_id, добавляем в общую сумму
            if store_id and store_id != "all" and not store_external_id:
                # Проверяем, совпадает ли название магазина с фильтром
                if store_name == store_id or store_name.upper() == store_id.upper():
                    # Данные уже учтены в total_visitors, но нужно убедиться, что они в visitors_by_store
                    pass
        
        # При фильтре по одному магазину показываем в разбивке только его название (из 1С), без дубликата CENTRUM/Ялта
        if store_id and store_id != "all" and selected_store_name and total_visitors > 0:
            visitors_by_store[store_id] = {
                "visitor_count": total_visitors,
                "store_name": selected_store_name
            }
            visitors_by_store[selected_store_name] = {
                "visitor_count": total_visitors,
                "store_name": selected_store_name
            }
            # Убираем альясные названия из разбивки, чтобы не показывать "CENTRUM: 33" и "Центрум 2: 33" одновременно
            store_name_lower = selected_store_name.lower()
            if "центрум" in store_name_lower or "centrum" in store_name_lower:
                visitors_by_store.pop("CENTRUM", None)
            if "ялта" in store_name_lower or "yalta" in store_name_lower:
                visitors_by_store.pop("YALTA", None)

        logger.info(f"Общая посещаемость: {total_visitors}, по магазинам: {visitors_by_store}")
    except Exception as e:
        logger.warning(f"Ошибка получения данных о посещаемости: {e}", exc_info=True)

    # Добавляем посещаемость в aggregated
    aggregated["total_visitors"] = total_visitors
    
    # Рассчитываем выручку на входящего (выручка / посещаемость)
    if total_visitors > 0:
        aggregated["revenue_per_visitor"] = aggregated["total_revenue"] / total_visitors
    else:
        aggregated["revenue_per_visitor"] = 0.0
    
    logger.info(f"Получено метрик из БД: {len(metrics)}, агрегировано: {aggregated}, магазинов: {len(by_store)}, посетителей: {total_visitors}")
    
    return {
        "status": "success",
        "period": {
            "start": start.isoformat(),
            "end": end.isoformat()
        },
        "total": len(metrics),
        "aggregated": aggregated,
        "by_store": by_store,
        "by_channel": by_channel,
        "visitors_by_store": visitors_by_store,
        "metrics": [
            {
                "id": str(m.id),
                "date": m.date.isoformat(),
                "revenue": m.revenue,
                "order_count": m.order_count,
                "average_order_value": m.average_order_value,
                "items_sold": m.items_sold
            }
            for m in metrics
        ]
    }


@router.get("/1c-sales/details")
async def get_1c_sales_details(
    period: Optional[str] = Query(None, description="Период: today, yesterday, week, month, quarter, year"),
    start_date: Optional[str] = Query(None, description="Начальная дата (ISO format)"),
    end_date: Optional[str] = Query(None, description="Конечная дата (ISO format)"),
    days: int = Query(30, ge=1, le=365),
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    limit: int = Query(100, ge=1, le=1000, description="Лимит записей"),
    offset: int = Query(0, ge=0, description="Смещение для пагинации"),
    db: AsyncSession = Depends(get_db)
):
    """
    Получение детальных данных о продажах (список товаров)
    
    Возвращает список продаж с информацией о товарах:
    - Название товара
    - Артикул
    - Количество
    - Сумма
    - Магазин
    - Дата продажи
    """
    from app.models.sales_record import SalesRecord
    from app.models.store import Store
    
    try:
        # Определяем период
        if period:
            start, end = get_period_dates(period)
        elif start_date and end_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end = datetime.now()
            start = end - timedelta(days=days)
        
        # Получаем названия магазинов
        stores_query = await db.execute(select(Store.external_id, Store.name))
        store_names = {row[0]: row[1] for row in stores_query.all() if row[0]}
        
        # Формируем запрос
        # Исключаем записи с нулевыми quantity и revenue (это могут быть служебные записи)
        query = select(
            SalesRecord.id,
            SalesRecord.sale_date,
            SalesRecord.product_name,
            SalesRecord.product_article,
            SalesRecord.product_category,
            SalesRecord.product_brand,
            SalesRecord.quantity,
            SalesRecord.revenue,
            SalesRecord.store_id,
            SalesRecord.channel,
            SalesRecord.external_id
        ).where(
            and_(
                SalesRecord.sale_date >= start,
                SalesRecord.sale_date <= end,
                # Исключаем записи где и quantity и revenue равны 0
                or_(
                    SalesRecord.quantity > 0,
                    SalesRecord.revenue > 0
                ),
                # Исключаем упаковку (товары с ценой за единицу меньше 3 рублей)
                # Но они учитываются в агрегированных метриках
                # Проверяем, что quantity > 0 и цена за единицу >= 3.0
                SalesRecord.quantity > 0,
                SalesRecord.revenue / SalesRecord.quantity >= 3.0
            )
        )
        
        # Фильтр по магазину
        if store_id and store_id != "all":
            query = query.where(SalesRecord.store_id == store_id)
        
        # Сортируем по дате (новые сначала)
        query = query.order_by(desc(SalesRecord.sale_date))
        
        # Пагинация
        query = query.limit(limit).offset(offset)
        
        result = await db.execute(query)
        rows = result.all()
        
        # Формируем список продаж
        sales_details = []
        for row in rows:
            sales_details.append({
                'id': str(row[0]),
                'sale_date': row[1].isoformat() if row[1] else None,
                'product_name': row[2] or '—',
                'product_article': row[3] or '—',
                'product_category': row[4],
                'product_brand': row[5],
                'quantity': float(row[6]) if row[6] else 0.0,
                'revenue': float(row[7]) if row[7] else 0.0,
                'store_id': row[8],
                'store_name': store_names.get(row[8], row[8]) if row[8] else None,
                'channel': row[9] or 'offline',
                'external_id': row[10]
            })
        
        # Получаем общее количество записей (для пагинации)
        count_query = select(func.count(SalesRecord.id)).where(
            and_(
                SalesRecord.sale_date >= start,
                SalesRecord.sale_date <= end,
                # Исключаем записи где и quantity и revenue равны 0
                or_(
                    SalesRecord.quantity > 0,
                    SalesRecord.revenue > 0
                ),
                # Исключаем упаковку (товары с ценой за единицу меньше 3 рублей)
                # Проверяем, что quantity > 0 и цена за единицу >= 3.0
                and_(
                    SalesRecord.quantity > 0,
                    SalesRecord.revenue / SalesRecord.quantity >= 3.0
                )
            )
        )
        if store_id and store_id != "all":
            count_query = count_query.where(SalesRecord.store_id == store_id)
        
        count_result = await db.execute(count_query)
        total_count = count_result.scalar() or 0
        
        return {
            "status": "success",
            "period": {
                "start": start.isoformat(),
                "end": end.isoformat()
            },
            "sales": sales_details,
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total_count
        }
    except Exception as e:
        logger.error(f"Ошибка получения детальных продаж: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# 1С Покупатели
# =========================

@router.post("/1c-customers/sync")
async def sync_1c_customers(
    limit: int = Query(1000, ge=1, le=10000),
    db: AsyncSession = Depends(get_db)
):
    """Синхронизация дисконтных карт из 1С"""
    try:
        async with OneCCustomersService() as customers_service:
            cards = await customers_service.fetch_discount_cards(limit=limit)
            
            # Здесь можно сохранить в БД или обновить пользователей
            # Пока возвращаем данные для синхронизации
            
            return {
                "status": "success",
                "total": len(cards),
                "cards": [
                    {
                        "phone": card.get("КодКартыШтрихкод"),
                        "discount_card_id": card.get("Ref_Key"),
                        "customer_id": card.get("ВладелецКарты_Key"),
                        "code": card.get("Code"),
                        "description": card.get("Description")
                    }
                    for card in cards
                ]
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/1c-customers/{customer_id}/purchases")
async def get_customer_purchases(
    customer_id: str,
    days: int = Query(365, ge=1, le=3650),
    db: AsyncSession = Depends(get_db)
):
    """Получение истории покупок покупателя"""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        async with OneCCustomersService() as customers_service:
            purchases = await customers_service.get_customer_purchases(
                customer_id,
                start_date=start_date,
                end_date=end_date
            )
            
            return {
                "status": "success",
                "customer_id": customer_id,
                "total": len(purchases),
                "purchases": purchases,
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                }
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/1c-customers/by-phone/{phone}")
async def get_customer_by_phone(
    phone: str,
    include_purchases: bool = Query(False),
    purchase_days: int = Query(365, ge=1, le=3650),
    db: AsyncSession = Depends(get_db)
):
    """Получение информации о покупателе по номеру телефона"""
    try:
        async with OneCCustomersService() as customers_service:
            card = await customers_service.get_customer_by_phone(phone)
            
            if not card:
                raise HTTPException(status_code=404, detail="Покупатель не найден")
            
            result = {
                "status": "success",
                "phone": phone,
                "discount_card": {
                    "id": card.get("Ref_Key"),
                    "code": card.get("Code"),
                    "description": card.get("Description"),
                    "customer_id": card.get("ВладелецКарты_Key")
                }
            }
            
            if include_purchases and card.get("ВладелецКарты_Key"):
                end_date = datetime.now()
                start_date = end_date - timedelta(days=purchase_days)
                
                purchases = await customers_service.get_customer_purchases(
                    card.get("ВладелецКарты_Key"),
                    start_date=start_date,
                    end_date=end_date
                )
                
                result["purchases"] = purchases
                result["purchases_count"] = len(purchases)
            
            return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/1c-customers/{customer_id}/profile")
async def get_customer_profile(
    customer_id: str,
    purchase_days: int = Query(365, ge=1, le=3650),
    db: AsyncSession = Depends(get_db)
):
    """Получение профиля покупателя с аналитикой"""
    try:
        async with OneCCustomersService() as customers_service:
            # Получаем дисконтную карту по customer_id
            # Для упрощения используем поиск по всем картам
            # В реальности лучше иметь прямой endpoint для поиска карты по customer_id
            cards = await customers_service.fetch_discount_cards(limit=10000)
            card = None
            for c in cards:
                if c.get("ВладелецКарты_Key") == customer_id:
                    card = c
                    break
            
            if not card:
                raise HTTPException(status_code=404, detail="Дисконтная карта не найдена")
            
            # Получаем историю покупок
            end_date = datetime.now()
            start_date = end_date - timedelta(days=purchase_days)
            
            purchases = await customers_service.get_customer_purchases(
                customer_id,
                start_date=start_date,
                end_date=end_date
            )
            
            # Строим профиль
            profile = customers_service.build_customer_profile(card, purchases)
            
            return {
                "status": "success",
                "profile": profile
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# Объединенная аналитика
# =========================

@router.get("/unified")
async def get_unified_analytics(days: int = Query(30), db: AsyncSession = Depends(get_db)):
    """Получение объединенной аналитики из всех источников"""
    from app.models.social_media_metric import SocialMediaMetric
    from app.models.sales_metric import SalesMetric
    from app.models.store_visit import StoreVisit
    from sqlalchemy import select, func
    
    try:
        since = datetime.now() - timedelta(days=days)
        end = datetime.now()
        
        # Соцсети
        social_result = await db.execute(
            select(SocialMediaMetric).where(SocialMediaMetric.date >= since)
        )
        social_metrics = social_result.scalars().all()
        
        # Продажи
        sales_result = await db.execute(
            select(func.sum(SalesMetric.revenue), func.sum(SalesMetric.order_count))
            .where(SalesMetric.date >= since)
        )
        sales_total = sales_result.first()
        
        # Посещения магазинов
        stores_result = await db.execute(
            select(func.sum(StoreVisit.visitor_count), func.sum(StoreVisit.sales_count))
            .where(StoreVisit.date >= since)
        )
        stores_total = stores_result.first()
        
        # Яндекс.Метрика (сайт)
        website_visits = 0
        website_visitors = 0
        website_bounce_rate = 0.0
        website_avg_session_duration = 0.0
        
        try:
            async with YandexMetrikaService() as ym_service:
                visits_data = await ym_service.get_visits_metrics(since, end)
                if visits_data:
                    website_visits = visits_data.get("visits", 0)
                    website_visitors = visits_data.get("users", 0)
                    website_bounce_rate = visits_data.get("bounce_rate", 0.0)
                    website_avg_session_duration = visits_data.get("avg_visit_duration", 0.0)
        except Exception as ym_error:
            # Если Яндекс.Метрика недоступна, просто пропускаем
            import logging
            logging.warning(f"Yandex Metrika error: {ym_error}")
        
        return {
            "status": "success",
            "period": {"start": since.isoformat(), "end": end.isoformat()},
            "website": {
                "visits": website_visits,
                "visitors": website_visitors,
                "bounce_rate": round(website_bounce_rate, 2),
                "avg_session_duration": round(website_avg_session_duration, 2)
            },
            "social_media": {
                "total_metrics": len(social_metrics),
                "platforms": list(set(m.platform for m in social_metrics))
            },
            "sales": {
                "total_revenue": float(sales_total[0] or 0),
                "total_orders": int(sales_total[1] or 0)
            },
            "stores": {
                "total_visitors": int(stores_total[0] or 0),
                "total_sales": int(stores_total[1] or 0)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# Аналитика товаров (топ-продаваемые, по категориям, брендам и т.д.)
# =========================

@router.get("/products/top-sellers")
async def get_top_products(
    period: Optional[str] = Query(None, description="Период: today, yesterday, week, month, quarter, year"),
    start_date: Optional[str] = Query(None, description="Начальная дата (ISO format)"),
    end_date: Optional[str] = Query(None, description="Конечная дата (ISO format)"),
    days: int = Query(30, ge=1, le=365, description="Количество дней назад (если не указан период)"),
    limit: int = Query(20, ge=1, le=100, description="Количество товаров"),
    sort_by: str = Query("revenue", description="Сортировка: revenue, quantity, orders"),
    category: Optional[str] = Query(None, description="Фильтр по категории"),
    brand: Optional[str] = Query(None, description="Фильтр по бренду"),
    product_type: Optional[str] = Query(None, description="Фильтр по типу изделия"),
    channel: Optional[str] = Query(None, description="Фильтр по каналу продаж"),
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    db: AsyncSession = Depends(get_db)
):
    """
    Получение топ-продаваемых товаров
    
    Возвращает список товаров, отсортированных по выручке, количеству или количеству заказов
    """
    try:
        # Определяем период
        if period:
            start, end = get_period_dates(period)
        elif start_date and end_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end = datetime.now()
            start = end - timedelta(days=days)
        
        analytics_service = ProductAnalyticsService(db)
        products = await analytics_service.get_top_products(
            start_date=start,
            end_date=end,
            limit=limit,
            sort_by=sort_by,
            category=category,
            brand=brand,
            product_type=product_type,
            channel=channel,
            store_id=store_id
        )
        
        return {
            "period": {
                "start": start.isoformat(),
                "end": end.isoformat()
            },
            "filters": {
                "category": category,
                "brand": brand,
                "product_type": product_type,
                "channel": channel,
                "store_id": store_id
            },
            "sort_by": sort_by,
            "products": products,
            "total": len(products)
        }
    except Exception as e:
        logger.error(f"Ошибка получения топ-товаров: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/products/by-category")
async def get_sales_by_category(
    period: Optional[str] = Query(None, description="Период: today, yesterday, week, month, quarter, year"),
    start_date: Optional[str] = Query(None, description="Начальная дата (ISO format)"),
    end_date: Optional[str] = Query(None, description="Конечная дата (ISO format)"),
    days: int = Query(30, ge=1, le=365, description="Количество дней назад"),
    channel: Optional[str] = Query(None, description="Фильтр по каналу продаж"),
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    db: AsyncSession = Depends(get_db)
):
    """Получение продаж по категориям"""
    try:
        # Определяем период
        if period:
            start, end = get_period_dates(period)
        elif start_date and end_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end = datetime.now()
            start = end - timedelta(days=days)
        
        analytics_service = ProductAnalyticsService(db)
        categories = await analytics_service.get_sales_by_category(
            start_date=start,
            end_date=end,
            channel=channel,
            store_id=store_id
        )
        
        return {
            "period": {
                "start": start.isoformat(),
                "end": end.isoformat()
            },
            "filters": {
                "channel": channel,
                "store_id": store_id
            },
            "categories": categories,
            "total": len(categories)
        }
    except Exception as e:
        logger.error(f"Ошибка получения продаж по категориям: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/products/by-brand")
async def get_sales_by_brand(
    period: Optional[str] = Query(None, description="Период: today, yesterday, week, month, quarter, year"),
    start_date: Optional[str] = Query(None, description="Начальная дата (ISO format)"),
    end_date: Optional[str] = Query(None, description="Конечная дата (ISO format)"),
    days: int = Query(30, ge=1, le=365, description="Количество дней назад"),
    channel: Optional[str] = Query(None, description="Фильтр по каналу продаж"),
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    db: AsyncSession = Depends(get_db)
):
    """Получение продаж по брендам"""
    try:
        # Определяем период
        if period:
            start, end = get_period_dates(period)
        elif start_date and end_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end = datetime.now()
            start = end - timedelta(days=days)
        
        analytics_service = ProductAnalyticsService(db)
        brands = await analytics_service.get_sales_by_brand(
            start_date=start,
            end_date=end,
            channel=channel,
            store_id=store_id
        )
        
        return {
            "period": {
                "start": start.isoformat(),
                "end": end.isoformat()
            },
            "filters": {
                "channel": channel,
                "store_id": store_id
            },
            "brands": brands,
            "total": len(brands)
        }
    except Exception as e:
        logger.error(f"Ошибка получения продаж по брендам: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/products/by-type")
async def get_sales_by_type(
    period: Optional[str] = Query(None, description="Период: today, yesterday, week, month, quarter, year"),
    start_date: Optional[str] = Query(None, description="Начальная дата (ISO format)"),
    end_date: Optional[str] = Query(None, description="Конечная дата (ISO format)"),
    days: int = Query(30, ge=1, le=365, description="Количество дней назад"),
    channel: Optional[str] = Query(None, description="Фильтр по каналу продаж"),
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    db: AsyncSession = Depends(get_db)
):
    """Получение продаж по типам изделий"""
    try:
        # Определяем период
        if period:
            start, end = get_period_dates(period)
        elif start_date and end_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end = datetime.now()
            start = end - timedelta(days=days)
        
        analytics_service = ProductAnalyticsService(db)
        types = await analytics_service.get_sales_by_type(
            start_date=start,
            end_date=end,
            channel=channel,
            store_id=store_id
        )
        
        return {
            "period": {
                "start": start.isoformat(),
                "end": end.isoformat()
            },
            "filters": {
                "channel": channel,
                "store_id": store_id
            },
            "product_types": types,
            "total": len(types)
        }
    except Exception as e:
        logger.error(f"Ошибка получения продаж по типам: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# Аналитика оборачиваемости товаров
# =========================

@router.get("/products/turnover")
async def get_product_turnover(
    period: Optional[str] = Query(None, description="Период: today, yesterday, week, month, quarter, year"),
    start_date: Optional[str] = Query(None, description="Начальная дата (ISO format)"),
    end_date: Optional[str] = Query(None, description="Конечная дата (ISO format)"),
    days: int = Query(30, ge=1, le=365, description="Количество дней назад"),
    product_id_1c: Optional[str] = Query(None, description="Фильтр по ID товара из 1С"),
    product_article: Optional[str] = Query(None, description="Фильтр по артикулу"),
    category: Optional[str] = Query(None, description="Фильтр по категории"),
    brand: Optional[str] = Query(None, description="Фильтр по бренду"),
    product_type: Optional[str] = Query(None, description="Фильтр по типу изделия"),
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    channel: Optional[str] = Query(None, description="Фильтр по каналу продаж"),
    db: AsyncSession = Depends(get_db)
):
    """
    Получение оборачиваемости товаров
    
    Возвращает список товаров с метриками оборачиваемости:
    - turnover_rate: коэффициент оборачиваемости (раз в период)
    - turnover_days: оборачиваемость в днях
    - turnover_class: классификация (fast, medium, slow, very_slow)
    """
    try:
        # Определяем период
        if period:
            start, end = get_period_dates(period)
        elif start_date and end_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end = datetime.now()
            start = end - timedelta(days=days)
        
        turnover_service = ProductTurnoverService(db)
        turnover_data = await turnover_service.calculate_turnover(
            start_date=start,
            end_date=end,
            product_id_1c=product_id_1c,
            product_article=product_article,
            category=category,
            brand=brand,
            product_type=product_type,
            store_id=store_id,
            channel=channel
        )
        
        # Сортируем по коэффициенту оборачиваемости
        turnover_data.sort(key=lambda x: x['turnover_rate'] or 0, reverse=True)
        
        return {
            "period": {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "days": (end - start).days + 1
            },
            "filters": {
                "product_id_1c": product_id_1c,
                "product_article": product_article,
                "category": category,
                "brand": brand,
                "product_type": product_type,
                "store_id": store_id,
                "channel": channel
            },
            "products": turnover_data,
            "total": len(turnover_data)
        }
    except Exception as e:
        logger.error(f"Ошибка получения оборачиваемости: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/products/turnover/by-category")
async def get_turnover_by_category(
    period: Optional[str] = Query(None, description="Период: today, yesterday, week, month, quarter, year"),
    start_date: Optional[str] = Query(None, description="Начальная дата (ISO format)"),
    end_date: Optional[str] = Query(None, description="Конечная дата (ISO format)"),
    days: int = Query(30, ge=1, le=365, description="Количество дней назад"),
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    channel: Optional[str] = Query(None, description="Фильтр по каналу продаж"),
    db: AsyncSession = Depends(get_db)
):
    """Получение оборачиваемости по категориям"""
    try:
        # Определяем период
        if period:
            start, end = get_period_dates(period)
        elif start_date and end_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end = datetime.now()
            start = end - timedelta(days=days)
        
        turnover_service = ProductTurnoverService(db)
        categories = await turnover_service.get_turnover_by_category(
            start_date=start,
            end_date=end,
            store_id=store_id,
            channel=channel
        )
        
        return {
            "period": {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "days": (end - start).days + 1
            },
            "filters": {
                "store_id": store_id,
                "channel": channel
            },
            "categories": categories,
            "total": len(categories)
        }
    except Exception as e:
        logger.error(f"Ошибка получения оборачиваемости по категориям: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/products/turnover/by-brand")
async def get_turnover_by_brand(
    period: Optional[str] = Query(None, description="Период: today, yesterday, week, month, quarter, year"),
    start_date: Optional[str] = Query(None, description="Начальная дата (ISO format)"),
    end_date: Optional[str] = Query(None, description="Конечная дата (ISO format)"),
    days: int = Query(30, ge=1, le=365, description="Количество дней назад"),
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    channel: Optional[str] = Query(None, description="Фильтр по каналу продаж"),
    db: AsyncSession = Depends(get_db)
):
    """Получение оборачиваемости по брендам"""
    try:
        # Определяем период
        if period:
            start, end = get_period_dates(period)
        elif start_date and end_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end = datetime.now()
            start = end - timedelta(days=days)
        
        turnover_service = ProductTurnoverService(db)
        brands = await turnover_service.get_turnover_by_brand(
            start_date=start,
            end_date=end,
            store_id=store_id,
            channel=channel
        )
        
        return {
            "period": {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "days": (end - start).days + 1
            },
            "filters": {
                "store_id": store_id,
                "channel": channel
            },
            "brands": brands,
            "total": len(brands)
        }
    except Exception as e:
        logger.error(f"Ошибка получения оборачиваемости по брендам: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/products/slow-movers")
async def get_slow_movers(
    period: Optional[str] = Query(None, description="Период: today, yesterday, week, month, quarter, year"),
    start_date: Optional[str] = Query(None, description="Начальная дата (ISO format)"),
    end_date: Optional[str] = Query(None, description="Конечная дата (ISO format)"),
    days: int = Query(90, ge=1, le=365, description="Количество дней назад"),
    min_stock: float = Query(1.0, ge=0.0, description="Минимальный остаток для включения"),
    max_turnover_rate: float = Query(1.0, ge=0.0, description="Максимальный коэффициент оборачиваемости"),
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    channel: Optional[str] = Query(None, description="Фильтр по каналу продаж"),
    db: AsyncSession = Depends(get_db)
):
    """
    Получение товаров с низкой оборачиваемостью (медленные продажи)
    
    Возвращает товары, которые продаются медленно и имеют значительные остатки
    """
    try:
        # Определяем период
        if period:
            start, end = get_period_dates(period)
        elif start_date and end_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end = datetime.now()
            start = end - timedelta(days=days)
        
        turnover_service = ProductTurnoverService(db)
        slow_movers = await turnover_service.get_slow_movers(
            start_date=start,
            end_date=end,
            min_stock=min_stock,
            max_turnover_rate=max_turnover_rate,
            store_id=store_id,
            channel=channel
        )
        
        return {
            "period": {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "days": (end - start).days + 1
            },
            "filters": {
                "min_stock": min_stock,
                "max_turnover_rate": max_turnover_rate,
                "store_id": store_id,
                "channel": channel
            },
            "slow_movers": slow_movers,
            "total": len(slow_movers)
        }
    except Exception as e:
        logger.error(f"Ошибка получения медленных товаров: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# Аналитика каналов продаж
# =========================

@router.get("/channels/comparison")
async def get_channel_comparison(
    period: Optional[str] = Query(None, description="Период: today, yesterday, week, month, quarter, year"),
    start_date: Optional[str] = Query(None, description="Начальная дата (ISO format)"),
    end_date: Optional[str] = Query(None, description="Конечная дата (ISO format)"),
    days: int = Query(30, ge=1, le=365, description="Количество дней назад"),
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    category: Optional[str] = Query(None, description="Фильтр по категории"),
    brand: Optional[str] = Query(None, description="Фильтр по бренду"),
    db: AsyncSession = Depends(get_db)
):
    """
    Сравнение каналов продаж
    
    Возвращает метрики по каждому каналу:
    - Выручка, количество, заказы
    - Доли в общих продажах
    - Средний чек
    - Уникальные покупатели и товары
    """
    try:
        # Определяем период
        if period:
            start, end = get_period_dates(period)
        elif start_date and end_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end = datetime.now()
            start = end - timedelta(days=days)
        
        channel_service = ChannelAnalyticsService(db)
        channels = await channel_service.get_channel_comparison(
            start_date=start,
            end_date=end,
            store_id=store_id,
            category=category,
            brand=brand
        )
        
        return {
            "period": {
                "start": start.isoformat(),
                "end": end.isoformat()
            },
            "filters": {
                "store_id": store_id,
                "category": category,
                "brand": brand
            },
            "channels": channels,
            "total": len(channels)
        }
    except Exception as e:
        logger.error(f"Ошибка сравнения каналов: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/channels/conversion")
async def get_channel_conversion(
    period: Optional[str] = Query(None, description="Период: today, yesterday, week, month, quarter, year"),
    start_date: Optional[str] = Query(None, description="Начальная дата (ISO format)"),
    end_date: Optional[str] = Query(None, description="Конечная дата (ISO format)"),
    days: int = Query(30, ge=1, le=365, description="Количество дней назад"),
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    db: AsyncSession = Depends(get_db)
):
    """
    Конверсия по каналам продаж
    
    Возвращает метрики конверсии:
    - Количество заказов и уникальных покупателей
    - Средний чек
    - Повторные покупки
    - Конверсия (требует данных о посетителях)
    """
    try:
        # Определяем период
        if period:
            start, end = get_period_dates(period)
        elif start_date and end_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end = datetime.now()
            start = end - timedelta(days=days)
        
        channel_service = ChannelAnalyticsService(db)
        conversion_data = await channel_service.get_channel_conversion(
            start_date=start,
            end_date=end,
            store_id=store_id
        )
        
        return conversion_data
    except Exception as e:
        logger.error(f"Ошибка получения конверсии по каналам: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/channels/trends")
async def get_channel_trends(
    period: Optional[str] = Query(None, description="Период: today, yesterday, week, month, quarter, year"),
    start_date: Optional[str] = Query(None, description="Начальная дата (ISO format)"),
    end_date: Optional[str] = Query(None, description="Конечная дата (ISO format)"),
    days: int = Query(30, ge=1, le=365, description="Количество дней назад"),
    period_type: str = Query("day", description="Тип периода для группировки: day, week, month"),
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    category: Optional[str] = Query(None, description="Фильтр по категории"),
    brand: Optional[str] = Query(None, description="Фильтр по бренду"),
    db: AsyncSession = Depends(get_db)
):
    """
    Тренды по каналам продаж
    
    Возвращает динамику продаж по каналам за период
    """
    try:
        # Определяем период
        if period:
            start, end = get_period_dates(period)
        elif start_date and end_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end = datetime.now()
            start = end - timedelta(days=days)
        
        channel_service = ChannelAnalyticsService(db)
        trends = await channel_service.get_channel_trends(
            start_date=start,
            end_date=end,
            period_type=period_type,
            store_id=store_id,
            category=category,
            brand=brand
        )
        
        return trends
    except Exception as e:
        logger.error(f"Ошибка получения трендов по каналам: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/channels/performance")
async def get_channel_performance(
    period: Optional[str] = Query(None, description="Период: today, yesterday, week, month, quarter, year"),
    start_date: Optional[str] = Query(None, description="Начальная дата (ISO format)"),
    end_date: Optional[str] = Query(None, description="Конечная дата (ISO format)"),
    days: int = Query(30, ge=1, le=365, description="Количество дней назад"),
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    db: AsyncSession = Depends(get_db)
):
    """
    Производительность каналов продаж
    
    Комплексная метрика производительности каналов:
    - Сравнение каналов
    - Тренды
    - Рост/падение
    """
    try:
        # Определяем период
        if period:
            start, end = get_period_dates(period)
        elif start_date and end_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end = datetime.now()
            start = end - timedelta(days=days)
        
        channel_service = ChannelAnalyticsService(db)
        performance = await channel_service.get_channel_performance(
            start_date=start,
            end_date=end,
            store_id=store_id
        )
        
        return performance
    except Exception as e:
        logger.error(f"Ошибка получения производительности каналов: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# Приоритизация товаров для сайта
# =========================

@router.get("/inventory/website-priority")
async def get_website_priority(
    limit: int = Query(500, ge=1, le=1000, description="Количество товаров"),
    min_priority: float = Query(30.0, ge=0.0, le=100.0, description="Минимальный приоритет"),
    category: Optional[str] = Query(None, description="Фильтр по категории"),
    only_recommended: bool = Query(False, description="Только рекомендованные товары"),
    db: AsyncSession = Depends(get_db)
):
    """
    Получение списка товаров для приоритетной выкладки на сайт
    
    Возвращает товары, отсортированные по приоритету, рассчитанному на основе:
    - Наличия фото (40%) - ГЛАВНЫЙ ПРИОРИТЕТ
    - Наличия остатков (30%) - ГЛАВНЫЙ ПРИОРИТЕТ
    - Оборачиваемости (15%)
    - Маржинальности (10%)
    - Тренда продаж (5%)
    """
    try:
        priority_service = WebsitePriorityService(db)
        products = await priority_service.get_prioritized_products(
            limit=limit,
            min_priority=min_priority,
            category=category,
            only_recommended=only_recommended
        )
        
        return {
            "status": "success",
            "total": len(products),
            "filters": {
                "min_priority": min_priority,
                "category": category,
                "only_recommended": only_recommended
            },
            "products": products
        }
    except Exception as e:
        logger.error(f"Ошибка получения приоритетных товаров: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/inventory/website-priority/recalculate")
async def recalculate_website_priority(
    analysis_period_days: int = Query(90, ge=30, le=365, description="Период анализа в днях"),
    min_turnover_rate: float = Query(0.1, ge=0.0, le=10.0, description="Минимальный коэффициент оборачиваемости"),
    min_stock: float = Query(1.0, ge=0.0, description="Минимальный остаток"),
    db: AsyncSession = Depends(get_db)
):
    """
    Пересчёт приоритетов товаров для выкладки на сайт
    
    Запускает полный пересчёт приоритетов на основе текущих данных о продажах,
    оборачиваемости и остатках.
    """
    try:
        priority_service = WebsitePriorityService(db)
        count = await priority_service.calculate_priority(
            analysis_period_days=analysis_period_days,
            min_turnover_rate=min_turnover_rate,
            min_stock=min_stock
        )
        
        return {
            "status": "success",
            "message": f"Приоритеты пересчитаны для {count} товаров",
            "processed_count": count,
            "analysis_period_days": analysis_period_days
        }
    except Exception as e:
        logger.error(f"Ошибка пересчёта приоритетов: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inventory/hidden-gems")
async def get_hidden_gems(
    limit: int = Query(20, ge=1, le=100, description="Количество товаров"),
    db: AsyncSession = Depends(get_db)
):
    """
    Получение "скрытых жемчужин" - товаров с высоким потенциалом роста
    
    Возвращает товары с:
    - Высокой маржой (>= 60%)
    - Растущим трендом (>= 60%)
    - Но не входящие в топ по текущему приоритету
    """
    try:
        priority_service = WebsitePriorityService(db)
        gems = await priority_service.get_hidden_gems(limit=limit)
        
        return {
            "status": "success",
            "total": len(gems),
            "products": gems
        }
    except Exception as e:
        logger.error(f"Ошибка получения скрытых жемчужин: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# Рекомендации по закупкам
# =========================

@router.get("/inventory/purchase-recommendations")
async def get_purchase_recommendations(
    limit: int = Query(100, ge=1, le=1000, description="Количество рекомендаций"),
    urgency_level: Optional[str] = Query(None, description="Фильтр по уровню срочности (critical, high, medium, low)"),
    category: Optional[str] = Query(None, description="Фильтр по категории"),
    only_reorder: bool = Query(False, description="Только товары, требующие заказа"),
    db: AsyncSession = Depends(get_db)
):
    """
    Получение рекомендаций по закупкам товаров
    
    Возвращает список товаров с рекомендациями по количеству для заказа,
    рассчитанными на основе оборачиваемости и текущих остатков.
    """
    try:
        recommendation_service = PurchaseRecommendationService(db)
        recommendations = await recommendation_service.get_recommendations(
            limit=limit,
            urgency_level=urgency_level,
            category=category,
            only_reorder=only_reorder
        )
        
        return {
            "status": "success",
            "total": len(recommendations),
            "filters": {
                "urgency_level": urgency_level,
                "category": category,
                "only_reorder": only_reorder
            },
            "recommendations": recommendations
        }
    except Exception as e:
        logger.error(f"Ошибка получения рекомендаций по закупкам: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/inventory/purchase-recommendations/recalculate")
async def recalculate_purchase_recommendations(
    analysis_period_days: int = Query(90, ge=30, le=365, description="Период анализа в днях"),
    lead_time_days: int = Query(14, ge=1, le=90, description="Срок поставки в днях"),
    min_avg_daily_sales: float = Query(0.01, ge=0.0, description="Минимальные средние продажи в день"),
    db: AsyncSession = Depends(get_db)
):
    """
    Пересчёт рекомендаций по закупкам
    
    Запускает полный пересчёт рекомендаций на основе текущих данных о продажах,
    оборачиваемости и остатках.
    """
    try:
        recommendation_service = PurchaseRecommendationService(db)
        count = await recommendation_service.calculate_recommendations(
            analysis_period_days=analysis_period_days,
            lead_time_days=lead_time_days,
            min_avg_daily_sales=min_avg_daily_sales
        )
        
        return {
            "status": "success",
            "message": f"Рекомендации пересчитаны для {count} товаров",
            "processed_count": count,
            "analysis_period_days": analysis_period_days
        }
    except Exception as e:
        logger.error(f"Ошибка пересчёта рекомендаций: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inventory/purchase-recommendations/export")
async def export_purchase_recommendations(
    urgency_level: Optional[str] = Query(None, description="Фильтр по уровню срочности"),
    category: Optional[str] = Query(None, description="Фильтр по категории"),
    only_reorder: bool = Query(False, description="Только товары, требующие заказа"),
    db: AsyncSession = Depends(get_db)
):
    """
    Экспорт рекомендаций по закупкам в Excel
    
    Возвращает файл Excel с рекомендациями для отдела закупок
    """
    try:
        from fastapi.responses import StreamingResponse
        import io
        import pandas as pd
        from datetime import datetime
        
        recommendation_service = PurchaseRecommendationService(db)
        recommendations = await recommendation_service.get_recommendations(
            limit=10000,
            urgency_level=urgency_level,
            category=category,
            only_reorder=only_reorder
        )
        
        if not recommendations:
            raise HTTPException(status_code=404, detail="Нет рекомендаций для экспорта")
        
        # Формируем DataFrame
        df = pd.DataFrame(recommendations)
        
        # Переименовываем колонки на русский
        column_mapping = {
            'product_article': 'Артикул',
            'product_name': 'Название товара',
            'product_category': 'Категория',
            'product_brand': 'Бренд',
            'current_stock': 'Текущий остаток',
            'recommended_order_quantity': 'Рекомендуемый заказ',
            'reorder_point': 'Точка заказа',
            'days_until_stockout': 'Дней до дефицита',
            'avg_daily_sales': 'Средние продажи/день',
            'turnover_days': 'Оборачиваемость (дни)',
            'urgency_level': 'Срочность',
            'recommended_order_date': 'Рекомендуемая дата заказа',
            'lead_time_days': 'Срок поставки (дни)',
            'safety_stock': 'Страховой запас'
        }
        
        df = df.rename(columns=column_mapping)
        
        # Форматируем даты
        if 'Рекомендуемая дата заказа' in df.columns:
            df['Рекомендуемая дата заказа'] = pd.to_datetime(df['Рекомендуемая дата заказа']).dt.strftime('%Y-%m-%d')
        
        # Округляем числовые значения
        if 'Средние продажи/день' in df.columns:
            df['Средние продажи/день'] = df['Средние продажи/день'].round(2)
        if 'Дней до дефицита' in df.columns:
            df['Дней до дефицита'] = df['Дней до дефицита'].round(1)
        
        # Переводим уровни срочности
        urgency_translation = {
            'critical': 'Критично',
            'high': 'Высокая',
            'medium': 'Средняя',
            'low': 'Низкая'
        }
        if 'Срочность' in df.columns:
            df['Срочность'] = df['Срочность'].map(urgency_translation)
        
        # Создаём Excel файл в памяти
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Рекомендации по закупкам', index=False)
            
            # Автоматическая ширина колонок
            worksheet = writer.sheets['Рекомендации по закупкам']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        output.seek(0)
        
        # Формируем имя файла с URL-кодированием для RFC 5987
        from urllib.parse import quote
        filename = f"Рекомендации_по_закупкам_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filename_encoded = quote(filename)
        
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename_encoded}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка экспорта рекомендаций: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inventory/reorder-alerts")
async def get_reorder_alerts(
    limit: int = Query(50, ge=1, le=500, description="Количество товаров"),
    db: AsyncSession = Depends(get_db)
):
    """
    Получение товаров для срочного заказа
    
    Возвращает товары с уровнем срочности "critical" - товары, которые
    требуют немедленного заказа.
    """
    try:
        recommendation_service = PurchaseRecommendationService(db)
        alerts = await recommendation_service.get_reorder_alerts(limit=limit)
        
        return {
            "status": "success",
            "total": len(alerts),
            "alerts": alerts
        }
    except Exception as e:
        logger.error(f"Ошибка получения алертов на заказ: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inventory/dead-stock")
async def get_dead_stock(
    limit: int = Query(50, ge=1, le=500, description="Количество товаров"),
    min_days: int = Query(180, ge=30, description="Минимальное количество дней оборачиваемости"),
    db: AsyncSession = Depends(get_db)
):
    """
    Получение неликвидных товаров
    
    Возвращает товары с очень низкой оборачиваемостью (неликвид),
    которые требуют внимания (распродажа, возврат поставщику и т.д.).
    """
    try:
        recommendation_service = PurchaseRecommendationService(db)
        dead_stock = await recommendation_service.get_dead_stock(
            limit=limit,
            min_days=min_days
        )
        
        return {
            "status": "success",
            "total": len(dead_stock),
            "dead_stock": dead_stock
        }
    except Exception as e:
        logger.error(f"Ошибка получения неликвидных товаров: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inventory/stock-forecast")
async def get_stock_forecast(
    days: int = Query(30, ge=1, le=365, description="Количество дней для прогноза"),
    category: Optional[str] = Query(None, description="Фильтр по категории"),
    db: AsyncSession = Depends(get_db)
):
    """
    Прогноз остатков на N дней вперёд
    
    Рассчитывает прогнозируемые остатки товаров на основе текущих продаж
    и оборачиваемости.
    """
    try:
        recommendation_service = PurchaseRecommendationService(db)
        recommendations = await recommendation_service.get_recommendations(
            limit=1000,
            category=category
        )
        
        forecast = []
        for rec in recommendations:
            if rec.get('avg_daily_sales') and rec.get('avg_daily_sales') > 0:
                current_stock = rec.get('current_stock', 0)
                avg_daily_sales = rec.get('avg_daily_sales', 0)
                forecasted_stock = max(0, current_stock - (avg_daily_sales * days))
                
                forecast.append({
                    'product_id_1c': rec.get('product_id_1c'),
                    'product_name': rec.get('product_name'),
                    'product_article': rec.get('product_article'),
                    'category': rec.get('category'),
                    'current_stock': current_stock,
                    'forecasted_stock': int(forecasted_stock),
                    'days_until_stockout': int(current_stock / avg_daily_sales) if avg_daily_sales > 0 else None,
                    'needs_reorder': forecasted_stock < rec.get('reorder_point', 0)
                })
        
        # Сортируем по дням до дефицита
        forecast.sort(key=lambda x: x.get('days_until_stockout') or 999)
        
        return {
            "status": "success",
            "forecast_days": days,
            "total": len(forecast),
            "forecast": forecast
        }
    except Exception as e:
        logger.error(f"Ошибка получения прогноза остатков: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# Управление запасами и оптимизация остатков
# =========================

@router.get("/inventory/analysis")
async def get_inventory_analysis(
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    category: Optional[str] = Query(None, description="Фильтр по категории"),
    abc_class: Optional[str] = Query(None, description="Фильтр по ABC классу (A, B, C)"),
    xyz_class: Optional[str] = Query(None, description="Фильтр по XYZ классу (X, Y, Z)"),
    critical_stockout: bool = Query(False, description="Только товары с критическим дефицитом (stockout_risk > 0.7)"),
    critical_overstock: bool = Query(False, description="Только товары с критическими излишками (overstock_risk > 0.7)"),
    limit: int = Query(100, ge=1, le=1000, description="Количество записей"),
    db: AsyncSession = Depends(get_db)
):
    """
    Получение комплексной аналитики остатков
    
    Возвращает детальную аналитику остатков товаров с метриками:
    - Скорость продаж (Sales Velocity)
    - Оборачиваемость
    - Риски дефицита и излишков
    - ABC/XYZ классификация
    - Уровень сервиса
    """
    try:
        inventory_service = InventoryManagementService(db)
        analysis = await inventory_service.get_inventory_analysis(
            store_id=store_id,
            category=category,
            abc_class=abc_class,
            xyz_class=xyz_class,
            critical_stockout=critical_stockout,
            critical_overstock=critical_overstock,
            limit=limit
        )
        
        return {
            "status": "success",
            "total": len(analysis),
            "filters": {
                "store_id": store_id,
                "category": category,
                "abc_class": abc_class,
                "xyz_class": xyz_class,
                "critical_stockout": critical_stockout,
                "critical_overstock": critical_overstock
            },
            "analysis": analysis
        }
    except Exception as e:
        logger.error(f"Ошибка получения аналитики остатков: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/inventory/analysis/recalculate")
async def recalculate_inventory_analysis(
    analysis_period_days: int = Query(90, ge=30, le=365, description="Период анализа в днях"),
    db: AsyncSession = Depends(get_db)
):
    """
    Пересчёт аналитики остатков
    
    Запускает полный пересчёт аналитики остатков для всех товаров.
    """
    try:
        inventory_service = InventoryManagementService(db)
        count = await inventory_service.calculate_inventory_analytics(
            analysis_period_days=analysis_period_days
        )
        
        return {
            "status": "success",
            "message": f"Аналитика остатков пересчитана для {count} записей",
            "processed_count": count,
            "analysis_period_days": analysis_period_days
        }
    except Exception as e:
        logger.error(f"Ошибка пересчёта аналитики остатков: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inventory/analysis/export")
async def export_inventory_analysis(
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    category: Optional[str] = Query(None, description="Фильтр по категории"),
    abc_class: Optional[str] = Query(None, description="Фильтр по ABC классу (A, B, C)"),
    xyz_class: Optional[str] = Query(None, description="Фильтр по XYZ классу (X, Y, Z)"),
    critical_stockout: bool = Query(False, description="Только товары с критическим дефицитом"),
    critical_overstock: bool = Query(False, description="Только товары с критическими излишками"),
    db: AsyncSession = Depends(get_db)
):
    """
    Экспорт аналитики остатков в Excel
    """
    try:
        from fastapi.responses import StreamingResponse
        import io
        import pandas as pd
        from datetime import datetime
        from urllib.parse import quote
        
        inventory_service = InventoryManagementService(db)
        analysis = await inventory_service.get_inventory_analysis(
            store_id=store_id,
            category=category,
            abc_class=abc_class,
            xyz_class=xyz_class,
            critical_stockout=critical_stockout,
            critical_overstock=critical_overstock,
            limit=10000
        )
        
        if not analysis:
            raise HTTPException(status_code=404, detail="Нет данных для экспорта")
        
        df = pd.DataFrame(analysis)
        
        column_mapping = {
            'product_name': 'Название товара',
            'product_article': 'Артикул',
            'category': 'Категория',
            'brand': 'Бренд',
            'store_name': 'Магазин',
            'current_stock': 'Текущий остаток',
            'avg_stock_30d': 'Средний остаток (30 дней)',
            'avg_stock_90d': 'Средний остаток (90 дней)',
            'sales_velocity': 'Скорость продаж',
            'avg_daily_sales': 'Средние продажи/день',
            'turnover_days': 'Оборачиваемость (дни)',
            'turnover_rate': 'Коэффициент оборачиваемости',
            'stockout_risk': 'Риск дефицита',
            'overstock_risk': 'Риск излишков',
            'abc_class': 'ABC класс',
            'xyz_class': 'XYZ класс',
            'service_level': 'Уровень сервиса'
        }
        
        df = df.rename(columns=column_mapping)
        
        # Форматируем числовые поля
        numeric_columns = ['Текущий остаток', 'Средний остаток (30 дней)', 'Средний остаток (90 дней)',
                          'Скорость продаж', 'Средние продажи/день', 'Оборачиваемость (дни)',
                          'Коэффициент оборачиваемости', 'Риск дефицита', 'Риск излишков', 'Уровень сервиса']
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').round(2)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Аналитика остатков', index=False)
            
            worksheet = writer.sheets['Аналитика остатков']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        output.seek(0)
        
        filename = f"Аналитика_остатков_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filename_encoded = quote(filename)
        
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename_encoded}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка экспорта аналитики остатков: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inventory/categories")
async def get_inventory_categories(
    db: AsyncSession = Depends(get_db)
):
    """
    Получение списка категорий из аналитики остатков
    
    Returns:
        Список уникальных категорий
    """
    try:
        from app.models.inventory_analytics import InventoryAnalytics
        from sqlalchemy import distinct
        
        result = await db.execute(
            select(distinct(InventoryAnalytics.category))
            .where(
                and_(
                    InventoryAnalytics.category.isnot(None),
                    InventoryAnalytics.analysis_date == date.today()
                )
            )
            .order_by(InventoryAnalytics.category)
        )
        categories = [row[0] for row in result.all() if row[0]]
        
        return {
            "status": "success",
            "categories": categories
        }
    except Exception as e:
        logger.error(f"Ошибка получения категорий: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inventory/health-score")
async def get_inventory_health_score(
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    db: AsyncSession = Depends(get_db)
):
    """
    Получение "здоровья" остатков - общей оценки состояния запасов
    
    Возвращает комплексную оценку состояния запасов (0-100):
    - excellent (80-100): Отличное состояние
    - good (60-80): Хорошее состояние
    - fair (40-60): Удовлетворительное состояние
    - poor (0-40): Плохое состояние
    """
    try:
        inventory_service = InventoryManagementService(db)
        health = await inventory_service.get_health_score(store_id=store_id)
        
        return {
            "status": "success",
            **health
        }
    except Exception as e:
        logger.error(f"Ошибка получения здоровья остатков: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inventory/abc-xyz-matrix")
async def get_abc_xyz_matrix(
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    db: AsyncSession = Depends(get_db)
):
    """
    Получение ABC/XYZ матрицы товаров
    
    ABC классификация - по выручке (A - топ, B - средние, C - низкие)
    XYZ классификация - по стабильности спроса (X - стабильный, Y - переменный, Z - нестабильный)
    """
    try:
        inventory_service = InventoryManagementService(db)
        matrix = await inventory_service.get_abc_xyz_matrix(store_id=store_id)
        
        return matrix
    except Exception as e:
        logger.error(f"Ошибка получения ABC/XYZ матрицы: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inventory/stockout-forecast")
async def get_stockout_forecast(
    days: int = Query(30, ge=1, le=365, description="Количество дней для прогноза"),
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    db: AsyncSession = Depends(get_db)
):
    """
    Прогноз дефицита на N дней вперёд
    
    Возвращает товары, которые могут закончиться в течение указанного периода.
    """
    try:
        inventory_service = InventoryManagementService(db)
        forecast = await inventory_service.get_stockout_forecast(
            days=days,
            store_id=store_id
        )
        
        return {
            "status": "success",
            "forecast_days": days,
            "total": len(forecast),
            "forecast": forecast
        }
    except Exception as e:
        logger.error(f"Ошибка получения прогноза дефицита: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inventory/overstock-report")
async def get_overstock_report(
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    min_days: int = Query(180, ge=30, description="Минимальная оборачиваемость в днях"),
    db: AsyncSession = Depends(get_db)
):
    """
    Отчёт по излишкам товаров
    
    Возвращает товары с очень низкой оборачиваемостью (неликвид),
    которые требуют внимания.
    """
    try:
        inventory_service = InventoryManagementService(db)
        overstock = await inventory_service.get_overstock_report(
            store_id=store_id,
            min_days=min_days
        )
        
        return {
            "status": "success",
            "total": len(overstock),
            "min_days": min_days,
            "overstock": overstock
        }
    except Exception as e:
        logger.error(f"Ошибка получения отчёта по излишкам: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/inventory/stocks/sync")
async def sync_stocks_from_xml(
    recalculate_analytics: bool = Query(True, description="Автоматически пересчитать аналитику после синхронизации"),
    db: AsyncSession = Depends(get_db)
):
    """
    Синхронизация остатков товаров из offers.xml
    
    Загружает остатки по складам из CommerceML XML файла (offers.xml)
    и обновляет данные в таблице product_stocks.
    
    После синхронизации автоматически пересчитывает аналитику остатков,
    чтобы обновить данные в таблице inventory_analytics для отображения в UI.
    """
    import os
    from app.services.commerceml_xml_service import CommerceMLXMLService
    
    try:
        xml_url = os.getenv("ONEC_XML_OFFERS_URL")
        if not xml_url:
            raise HTTPException(
                status_code=400,
                detail="ONEC_XML_OFFERS_URL не настроен в переменных окружения"
            )
        
        logger.info(f"Начало синхронизации остатков из {xml_url}")
        
        async with OneCStockService(db) as stock_service:
            result = await stock_service.sync_stocks_from_xml(xml_url)
        
        logger.info(f"Синхронизация остатков завершена: {result}")
        
        # Автоматически пересчитываем аналитику после синхронизации остатков
        if recalculate_analytics:
            try:
                logger.info("Начало пересчёта аналитики остатков после синхронизации")
                inventory_service = InventoryManagementService(db)
                
                # Используем asyncio.wait_for для таймаута (5 минут)
                import asyncio
                try:
                    analytics_count = await asyncio.wait_for(
                        inventory_service.calculate_inventory_analytics(analysis_period_days=90),
                        timeout=300.0  # 5 минут
                    )
                    logger.info(f"Аналитика остатков пересчитана: обработано {analytics_count} товаров")
                    result['analytics_recalculated'] = True
                    result['analytics_count'] = analytics_count
                except asyncio.TimeoutError:
                    error_msg = "Пересчёт аналитики превысил таймаут (5 минут)"
                    logger.error(error_msg)
                    result['analytics_recalculated'] = False
                    result['analytics_error'] = error_msg
            except Exception as analytics_error:
                error_msg = str(analytics_error)
                logger.error(f"Ошибка при пересчёте аналитики после синхронизации остатков: {error_msg}", exc_info=True)
                result['analytics_recalculated'] = False
                result['analytics_error'] = error_msg
                # Не прерываем выполнение - остатки уже синхронизированы
        
        return {
            "status": "success",
            "message": "Синхронизация остатков успешно завершена",
            **result
        }
    except HTTPException as http_exc:
        # Пробрасываем HTTPException как есть, но убеждаемся, что это JSON
        logger.error(f"HTTP ошибка синхронизации остатков: {http_exc.detail}")
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=http_exc.status_code,
            content={
                "status": "error",
                "detail": http_exc.detail,
                "message": http_exc.detail
            }
        )
    except Exception as e:
        await db.rollback()
        error_message = str(e)
        logger.error(f"Ошибка синхронизации остатков: {error_message}", exc_info=True)
        # Всегда возвращаем JSON, даже при ошибке
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "detail": f"Ошибка синхронизации остатков: {error_message}",
                "message": error_message
            }
        )


@router.get("/inventory/store-distribution")
async def get_store_distribution(
    product_id_1c: Optional[str] = Query(None, description="Фильтр по товару (ID из 1С)"),
    category: Optional[str] = Query(None, description="Фильтр по категории"),
    db: AsyncSession = Depends(get_db)
):
    """
    План распределения товаров по магазинам
    
    Рассчитывает оптимальное распределение остатков товаров по магазинам
    на основе продаж каждого магазина.
    """
    try:
        recommendation_service = PurchaseRecommendationService(db)
        
        # Получаем рекомендации
        recommendations = await recommendation_service.get_recommendations(
            limit=1000,
            category=category
        )
        
        distribution = []
        for rec in recommendations:
            if product_id_1c and rec.get('product_id_1c') != product_id_1c:
                continue
            
            store_dist = rec.get('store_distribution')
            if store_dist:
                distribution.append({
                    'product_id_1c': rec.get('product_id_1c'),
                    'product_name': rec.get('product_name'),
                    'product_article': rec.get('product_article'),
                    'category': rec.get('category'),
                    'reorder_quantity': rec.get('reorder_quantity', 0),
                    'store_distribution': store_dist
                })
        
        return {
            "status": "success",
            "total": len(distribution),
            "distribution": distribution
        }
    except Exception as e:
        logger.error(f"Ошибка получения распределения по магазинам: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))



# =========================
# Прогнозирование спроса
# =========================

@router.get("/inventory/demand-forecast")
async def get_demand_forecast(
    product_id_1c: Optional[str] = Query(None, description="Фильтр по товару (ID из 1С)"),
    category: Optional[str] = Query(None, description="Фильтр по категории"),
    forecast_days: int = Query(30, ge=1, le=365, description="Количество дней для прогноза"),
    history_days: int = Query(90, ge=7, le=365, description="Количество дней истории для анализа"),
    db: AsyncSession = Depends(get_db)
):
    """
    Прогнозирование спроса на товары на указанное количество дней вперёд
    
    Использует исторические данные о продажах для прогнозирования будущего спроса
    с учётом трендов и сезонности.
    """
    try:
        forecasting_service = DemandForecastingService(db)
        forecasts = await forecasting_service.forecast_demand(
            product_id_1c=product_id_1c,
            category=category,
            forecast_days=forecast_days,
            history_days=history_days
        )
        
        return {
            "status": "success",
            "forecast_days": forecast_days,
            "history_days": history_days,
            "total": len(forecasts),
            "forecasts": forecasts
        }
    except Exception as e:
        logger.error(f"Ошибка прогнозирования спроса: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inventory/seasonal-forecast")
async def get_seasonal_forecast(
    category: Optional[str] = Query(None, description="Фильтр по категории"),
    months_ahead: int = Query(3, ge=1, le=12, description="Количество месяцев для прогноза"),
    db: AsyncSession = Depends(get_db)
):
    """
    Сезонное прогнозирование спроса на несколько месяцев вперёд
    
    Анализирует сезонные паттерны продаж и прогнозирует спрос на будущие месяцы.
    """
    try:
        forecasting_service = DemandForecastingService(db)
        forecast = await forecasting_service.get_seasonal_forecast(
            category=category,
            months_ahead=months_ahead
        )
        
        return forecast
    except Exception as e:
        logger.error(f"Ошибка сезонного прогнозирования: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inventory/demand-trends")
async def get_demand_trends(
    product_id_1c: Optional[str] = Query(None, description="Фильтр по товару (ID из 1С)"),
    category: Optional[str] = Query(None, description="Фильтр по категории"),
    days: int = Query(90, ge=14, le=365, description="Период анализа в днях"),
    db: AsyncSession = Depends(get_db)
):
    """
    Анализ трендов спроса за указанный период
    
    Определяет направление тренда (растущий/падающий/стабильный) и процент изменения спроса.
    """
    try:
        forecasting_service = DemandForecastingService(db)
        trends = await forecasting_service.get_demand_trends(
            product_id_1c=product_id_1c,
            category=category,
            days=days
        )
        
        return trends
    except Exception as e:
        logger.error(f"Ошибка анализа трендов спроса: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# Stock Transfer & Movement
# =========================


@router.get("/inventory/transfer-recommendations")
async def get_transfer_recommendations(
    analysis_period_days: int = Query(90, ge=30, le=180, description="Период анализа продаж"),
    min_daily_sales: float = Query(0.01, ge=0.0, description="Минимальные продажи/день"),
    safety_stock_days: int = Query(14, ge=7, le=30, description="Дней страхового запаса"),
    priority: Optional[str] = Query(None, description="Фильтр по приоритету (critical, high, medium)"),
    store_id: Optional[str] = Query(None, description="Фильтр по магазину"),
    category: Optional[str] = Query(None, description="Фильтр по категории"),
    limit: int = Query(100, ge=1, le=500, description="Количество рекомендаций"),
    db: AsyncSession = Depends(get_db)
):
    """
    Рекомендации по перемещению товаров со склада в магазины
    
    Использует AI-анализ для определения:
    - Какие товары нужно переместить и куда
    - Приоритет перемещения (критичность)
    - "Горячие" товары для каждого магазина
    - Оптимальное количество для перемещения
    """
    try:
        transfer_service = StockTransferService(db)
        recommendations = await transfer_service.calculate_transfer_recommendations(
            analysis_period_days=analysis_period_days,
            min_daily_sales=min_daily_sales,
            safety_stock_days=safety_stock_days
        )
        
        # Применяем фильтры
        if priority:
            recommendations = [r for r in recommendations if r.get('priority') == priority]
        
        if store_id:
            recommendations = [r for r in recommendations if r.get('to_store_id') == store_id]
        
        if category:
            recommendations = [r for r in recommendations if r.get('category') == category]
        
        # Ограничиваем количество
        recommendations = recommendations[:limit]
        
        return {
            "status": "success",
            "total": len(recommendations),
            "recommendations": recommendations
        }
    except Exception as e:
        logger.error(f"Ошибка получения рекомендаций по перемещению: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inventory/transfer-recommendations/export")
async def export_transfer_recommendations(
    analysis_period_days: int = Query(90, ge=30, le=180),
    priority: Optional[str] = Query(None),
    store_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Экспорт рекомендаций по перемещению в Excel"""
    try:
        from fastapi.responses import StreamingResponse
        import io
        import pandas as pd
        
        transfer_service = StockTransferService(db)
        recommendations = await transfer_service.calculate_transfer_recommendations(
            analysis_period_days=analysis_period_days
        )
        
        # Применяем фильтры
        if priority:
            recommendations = [r for r in recommendations if r.get('priority') == priority]
        if store_id:
            recommendations = [r for r in recommendations if r.get('to_store_id') == store_id]
        
        if not recommendations:
            raise HTTPException(status_code=404, detail="Нет рекомендаций для экспорта")
        
        # Формируем DataFrame
        df = pd.DataFrame(recommendations)
        
        # Переименовываем колонки
        column_mapping = {
            'product_article': 'Артикул',
            'product_name': 'Название товара',
            'category': 'Категория',
            'brand': 'Бренд',
            'from_store': 'Откуда',
            'to_store_name': 'Куда',
            'current_stock': 'Текущий остаток',
            'warehouse_stock': 'На складе',
            'recommended_transfer': 'Переместить (шт)',
            'days_until_stockout': 'Дней до дефицита',
            'avg_daily_sales': 'Продаж/день',
            'priority': 'Приоритет',
            'is_hot_product': 'Популярный товар',
            'reason': 'Причина'
        }
        
        df = df[[col for col in column_mapping.keys() if col in df.columns]]
        df = df.rename(columns=column_mapping)
        
        # Переводим приоритет
        priority_translation = {
            'critical': 'Критично',
            'high': 'Высокий',
            'medium': 'Средний'
        }
        if 'Приоритет' in df.columns:
            df['Приоритет'] = df['Приоритет'].map(priority_translation)
        
        if 'Популярный товар' in df.columns:
            df['Популярный товар'] = df['Популярный товар'].map({True: 'Да', False: 'Нет'})
        
        # Округляем числа
        if 'Дней до дефицита' in df.columns:
            df['Дней до дефицита'] = df['Дней до дефицита'].round(1)
        if 'Продаж/день' in df.columns:
            df['Продаж/день'] = df['Продаж/день'].round(2)
        
        # Создаём Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Перемещения', index=False)
            
            worksheet = writer.sheets['Перемещения']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        output.seek(0)
        
        # Формируем имя файла с URL-кодированием для RFC 5987
        from urllib.parse import quote
        filename = f"Перемещения_товаров_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filename_encoded = quote(filename)
        
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename_encoded}"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка экспорта рекомендаций по перемещению: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inventory/store-performance")
async def get_store_performance(
    analysis_period_days: int = Query(90, ge=30, le=365),
    db: AsyncSession = Depends(get_db)
):
    """
    AI-анализ эффективности продаж по магазинам
    Показывает, какие категории товаров лучше продаются в каких магазинах
    """
    try:
        transfer_service = StockTransferService(db)
        analysis = await transfer_service.get_store_performance_analysis(
            analysis_period_days=analysis_period_days
        )
        
        return {
            "status": "success",
            "analysis": analysis
        }
    except Exception as e:
        logger.error(f"Ошибка анализа эффективности магазинов: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
