from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime, timedelta
from app.database.connection import get_db
from app.models.store import Store
from app.models.app_setting import AppSetting
from app.models.store_visit import StoreVisit
from app.services.ftp_service import FTPService
from app.services.geolocation_service import GeolocationService
import os
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter()


class StoreCreate(BaseModel):
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class StoreResponse(BaseModel):
    id: str
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    external_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_active: bool

    class Config:
        from_attributes = True

@router.get("", response_model=List[StoreResponse])
async def list_stores(
    q: Optional[str] = Query(None, description="Фильтр по названию"),
    city: Optional[str] = Query(None, description="Фильтр по городу"),
    active: Optional[bool] = Query(None, description="Только активные"),
    is_active: Optional[bool] = Query(None, description="Alias for active (deprecated)"),
    pickup_only: bool = Query(False, description="Только магазины, разрешенные для самовывоза"),
    db: AsyncSession = Depends(get_db)
):
    """
    Получить список магазинов.
    Поддерживает фильтрацию по названию (q), городу и активности.
    """
    stmt = select(Store)
    
    # Handle both 'active' and 'is_active' parameters
    filter_active = active if active is not None else is_active
    if filter_active is not None:
        stmt = stmt.where(Store.is_active == filter_active)
        
    if city:
        stmt = stmt.where(Store.city == city)
        
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Store.name.ilike(like))

    if pickup_only:
        raw = (
            await db.execute(
                select(AppSetting.value).where(AppSetting.key == "pickup_store_ids")
            )
        ).scalar_one_or_none()
        selected_ids: list[str] = []
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    selected_ids = [str(x).strip() for x in parsed if str(x).strip()]
            except Exception:
                selected_ids = []
        if selected_ids:
            valid_ids: list[UUID] = []
            for raw_id in selected_ids:
                try:
                    valid_ids.append(UUID(raw_id))
                except Exception:
                    continue
            if valid_ids:
                stmt = stmt.where(Store.id.in_(valid_ids))
            else:
                stmt = stmt.where(False)
        
    # Всегда сортируем по названию для удобства в выпадающих списках
    res = await db.execute(stmt.order_by(Store.name.asc()))
    rows = res.scalars().all()
    
    return [
        StoreResponse(
            id=str(s.id),
            name=s.name,
            address=s.address,
            city=s.city,
            external_id=s.external_id,
            latitude=s.latitude,
            longitude=s.longitude,
            is_active=bool(s.is_active),
        )
        for s in rows
    ]


@router.post("/sync-ftp", status_code=202)
async def sync_ftp(
    background_tasks: BackgroundTasks,
    filename: Optional[str] = None,
    pattern: Optional[str] = "*.csv",
    db: AsyncSession = Depends(get_db)
):
    """Ручная синхронизация статистики с FTP"""
    ftp_host = os.getenv("FTP_HOST")
    ftp_user = os.getenv("FTP_USER") or os.getenv("FTP_USERNAME")
    ftp_password = os.getenv("FTP_PASSWORD")
    ftp_dir = os.getenv("FTP_DIR") or os.getenv("FTP_DIRECTORY", "/")
    
    if not all([ftp_host, ftp_user, ftp_password]):
        raise HTTPException(
            status_code=400,
            detail="FTP credentials not configured. Set FTP_HOST, FTP_USER, FTP_PASSWORD environment variables."
        )
    
    background_tasks.add_task(sync_ftp_task, ftp_host, ftp_user, ftp_password, ftp_dir, filename, pattern, db)
    
    return {
        "status": "accepted",
        "message": "FTP sync started in background"
    }


async def sync_ftp_task(
    ftp_host: str,
    ftp_user: str,
    ftp_password: str,
    ftp_dir: str,
    filename: Optional[str],
    pattern: Optional[str],
    db: AsyncSession
):
    """Фоновая задача синхронизации FTP"""
    try:
        ftp_service = FTPService(ftp_host, ftp_user, ftp_password, ftp_dir)
        ftp_service.connect()
        
        # Получаем список файлов
        if filename:
            files = [filename]
        else:
            files = ftp_service.list_files(pattern)
        
        # Загружаем все магазины для маппинга
        stores_result = await db.execute(select(Store))
        stores = {store.name: store.id for store in stores_result.scalars().all()}
        
        synced_count = 0
        for file in files:
            try:
                visits = ftp_service.sync_store_visits_from_csv(file)
                
                for visit_data in visits:
                    # Находим или создаем магазин
                    store_id = visit_data.get('store_id')
                    if isinstance(store_id, str) and store_id not in stores:
                        # Создаем новый магазин
                        new_store = Store(name=store_id, is_active=True)
                        db.add(new_store)
                        await db.flush()
                        stores[store_id] = new_store.id
                    
                    store_uuid = stores.get(store_id) if isinstance(store_id, str) else UUID(store_id)
                    
                    # Проверяем, существует ли уже запись
                    existing = await db.execute(
                        select(StoreVisit).where(
                            StoreVisit.store_id == store_uuid,
                            StoreVisit.date == visit_data['date']
                        )
                    )
                    existing_visit = existing.scalar_one_or_none()
                    
                    if existing_visit:
                        # Обновляем существующую запись
                        existing_visit.visitor_count = visit_data['visitor_count']
                        existing_visit.sales_count = visit_data['sales_count']
                        existing_visit.revenue = visit_data['revenue']
                    else:
                        # Создаем новую запись
                        new_visit = StoreVisit(
                            store_id=store_uuid,
                            date=visit_data['date'],
                            visitor_count=visit_data['visitor_count'],
                            sales_count=visit_data['sales_count'],
                            revenue=visit_data['revenue']
                        )
                        db.add(new_visit)
                    
                    synced_count += 1
                
                await db.commit()
                logger.info(f"Synced {len(visits)} visits from {file}")
            except Exception as e:
                logger.error(f"Error syncing file {file}: {e}")
                await db.rollback()
        
        ftp_service.disconnect()
        logger.info(f"FTP sync completed. Synced {synced_count} visits")
    except Exception as e:
        logger.error(f"FTP sync error: {e}")
        await db.rollback()


@router.get("/visits")
async def get_store_visits(
    store_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db)
):
    """Статистика посещений офлайн магазинов"""
    try:
        query = select(StoreVisit)
        
        if store_id:
            query = query.where(StoreVisit.store_id == UUID(store_id))
        
        if start_date and end_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end = datetime.now()
            start = end - timedelta(days=days)
        
        query = query.where(
            StoreVisit.date >= start,
            StoreVisit.date <= end
        ).order_by(StoreVisit.date.desc())
        
        result = await db.execute(query)
        visits = result.scalars().all()
        
        return {
            "period": {
                "start": start.isoformat(),
                "end": end.isoformat()
            },
            "visits": [
                {
                    "id": str(v.id),
                    "store_id": str(v.store_id),
                    "date": v.date.isoformat(),
                    "visitor_count": v.visitor_count,
                    "sales_count": v.sales_count,
                    "revenue": v.revenue
                }
                for v in visits
            ],
            "total_visits": len(visits)
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date or UUID format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting store visits: {str(e)}")


@router.get("/sales")
async def get_store_sales(
    store_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db)
):
    """Статистика продаж офлайн магазинов"""
    try:
        query = select(StoreVisit)
        
        if store_id:
            query = query.where(StoreVisit.store_id == UUID(store_id))
        
        if start_date and end_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end = datetime.now()
            start = end - timedelta(days=days)
        
        query = query.where(
            StoreVisit.date >= start,
            StoreVisit.date <= end
        )
        
        result = await db.execute(query)
        visits = result.scalars().all()
        
        total_revenue = sum(v.revenue for v in visits)
        total_sales = sum(v.sales_count for v in visits)
        
        return {
            "period": {
                "start": start.isoformat(),
                "end": end.isoformat()
            },
            "total_revenue": total_revenue,
            "total_sales": total_sales,
            "avg_revenue_per_sale": total_revenue / total_sales if total_sales > 0 else 0.0,
            "stores_count": len(set(v.store_id for v in visits))
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date or UUID format: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting store sales: {str(e)}")


@router.post("/", response_model=StoreResponse)
async def create_store(store: StoreCreate, db: AsyncSession = Depends(get_db)):
    """Создание магазина"""
    try:
        new_store = Store(
            name=store.name,
            address=store.address,
            city=store.city,
            latitude=store.latitude,
            longitude=store.longitude
        )
        db.add(new_store)
        await db.commit()
        await db.refresh(new_store)
        return StoreResponse(
            id=str(new_store.id),
            name=new_store.name,
            address=new_store.address,
            city=new_store.city,
            external_id=new_store.external_id,
            latitude=new_store.latitude,
            longitude=new_store.longitude,
            is_active=new_store.is_active
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating store: {str(e)}")





@router.get("/nearest")
async def get_nearest_stores(
    latitude: float = Query(..., description="Latitude"),
    longitude: float = Query(..., description="Longitude"),
    radius_km: float = Query(50.0, ge=1.0, le=1000.0, description="Search radius in kilometers"),
    limit: int = Query(5, ge=1, le=20, description="Maximum number of stores to return"),
    db: AsyncSession = Depends(get_db)
):
    """Поиск ближайших магазинов по координатам"""
    try:
        service = GeolocationService(db)
        stores = await service.find_nearest_stores(latitude, longitude, radius_km, limit)
        return {
            "latitude": latitude,
            "longitude": longitude,
            "radius_km": radius_km,
            "stores": stores
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error finding nearest stores: {str(e)}")
