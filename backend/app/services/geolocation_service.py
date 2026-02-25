from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Dict, Any, Optional
from app.models.store import Store
from uuid import UUID
import math
import logging

logger = logging.getLogger(__name__)


class GeolocationService:
    def __init__(self, db: AsyncSession):
        self.db = db
    
    @staticmethod
    def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Расчет расстояния между двумя точками в километрах (формула Haversine)"""
        R = 6371  # Радиус Земли в километрах
        
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        
        a = (
            math.sin(dlat / 2) ** 2 +
            math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
            math.sin(dlon / 2) ** 2
        )
        c = 2 * math.asin(math.sqrt(a))
        
        return R * c
    
    async def find_nearest_stores(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 50.0,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Поиск ближайших магазинов"""
        # Получаем все активные магазины с координатами
        query = select(Store).where(
            Store.is_active == True,
            Store.latitude.isnot(None),
            Store.longitude.isnot(None)
        )
        
        result = await self.db.execute(query)
        stores = result.scalars().all()
        
        # Рассчитываем расстояние для каждого магазина
        stores_with_distance = []
        for store in stores:
            if store.latitude and store.longitude:
                distance = self.calculate_distance(
                    latitude, longitude,
                    store.latitude, store.longitude
                )
                
                if distance <= radius_km:
                    stores_with_distance.append({
                        "store": store,
                        "distance": distance
                    })
        
        # Сортируем по расстоянию
        stores_with_distance.sort(key=lambda x: x["distance"])
        
        # Возвращаем топ N ближайших
        return [
            {
                "id": str(item["store"].id),
                "name": item["store"].name,
                "address": item["store"].address,
                "city": item["store"].city,
                "latitude": item["store"].latitude,
                "longitude": item["store"].longitude,
                "distance_km": round(item["distance"], 2)
            }
            for item in stores_with_distance[:limit]
        ]
    
    async def get_store_by_id(self, store_id: UUID) -> Optional[Store]:
        """Получение магазина по ID"""
        result = await self.db.execute(select(Store).where(Store.id == store_id))
        return result.scalar_one_or_none()
    
    async def get_stores_in_city(self, city: str) -> List[Store]:
        """Получение всех магазинов в городе"""
        result = await self.db.execute(
            select(Store).where(
                Store.city == city,
                Store.is_active == True
            )
        )
        return list(result.scalars().all())
