"""
Сервис для синхронизации складов (магазинов) из 1С через OData API.
Использует Catalog_Склады для получения информации о магазинах.
"""
import httpx
import logging
import os
from typing import Any, Dict, List, Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.store import Store

logger = logging.getLogger(__name__)


class OneCStoresService:
    """Сервис для синхронизации складов из 1С"""

    def __init__(
        self,
        db: AsyncSession,
        api_url: Optional[str] = None,
        api_token: Optional[str] = None,
        stores_endpoint: Optional[str] = None,
    ):
        self.db = db
        self.api_url = api_url or os.getenv("ONEC_API_URL")
        self.api_token = api_token or os.getenv("ONEC_API_TOKEN")
        self.stores_endpoint = stores_endpoint or os.getenv(
            "ONEC_STORES_ENDPOINT", "/Catalog_Склады"
        )
        # Альтернативные названия каталога складов (если основное не работает)
        self.alternative_endpoints = [
            "/Catalog_Склады",
            "/Catalog_Stores",
            "/Catalog_Склады_Key",
            "/InformationRegister_Склады",
        ]
        self.client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()

    async def _ensure_client(self) -> None:
        """Создает HTTP клиент для запросов к 1С"""
        if self.client:
            return
        if not self.api_url:
            raise ValueError("ONEC_API_URL не настроен")

        headers = {"Accept": "application/json"}
        if self.api_token:
            if self.api_token.startswith("Basic "):
                headers["Authorization"] = self.api_token
            else:
                headers["Authorization"] = f"Basic {self.api_token}"

        self.client = httpx.AsyncClient(timeout=120.0, headers=headers, verify=True)

    async def fetch_stores_page(self, top: int = 1000, skip: int = 0) -> List[Dict[str, Any]]:
        """Получение одной страницы складов из 1С"""
        await self._ensure_client()

        url = f"{self.api_url.rstrip('/')}{self.stores_endpoint}"
        params = {"$top": top, "$skip": skip}

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if "value" in data:
                return data["value"]
            return []
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # Каталог складов может быть недоступен - это нормально
                # Логируем только на уровне debug, чтобы не засорять логи
                logger.debug(f"Каталог складов недоступен (404): {self.stores_endpoint}")
                # Возвращаем пустой список вместо ошибки
                return []
            logger.error(f"HTTP ошибка при запросе складов из 1С: {e.response.status_code}")
            logger.error(f"URL: {url}")
            logger.error(f"Ответ: {e.response.text[:500]}")
            raise
        except Exception as e:
            logger.error(f"Ошибка при запросе складов из 1С: {e}")
            raise

    async def fetch_stores(self) -> List[Dict[str, Any]]:
        """Получение всех складов из 1С с пагинацией"""
        # Пробуем разные endpoint'ы, если основной не работает
        endpoints_to_try = [self.stores_endpoint] + [
            ep for ep in self.alternative_endpoints if ep != self.stores_endpoint
        ]
        
        for endpoint in endpoints_to_try:
            try:
                original_endpoint = self.stores_endpoint
                self.stores_endpoint = endpoint
                
                all_stores = []
                top = 1000
                skip = 0

                while True:
                    page_stores = await self.fetch_stores_page(top=top, skip=skip)
                    if not page_stores:
                        break

                    all_stores.extend(page_stores)
                    if len(page_stores) < top:
                        break

                    skip += top

                if all_stores:
                    logger.info(f"Получено {len(all_stores)} складов из 1С через {endpoint}")
                    return all_stores
                    
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    # Логируем только на уровне debug, чтобы не засорять логи
                    logger.debug(f"Endpoint {endpoint} недоступен (404), пробуем следующий...")
                    continue
                else:
                    raise
            except Exception as e:
                logger.debug(f"Ошибка при запросе {endpoint}: {e}, пробуем следующий...")
                continue
            finally:
                self.stores_endpoint = original_endpoint
        
        # Если ни один endpoint не сработал - это нормально, каталог складов может быть недоступен
        logger.info("Каталог складов недоступен в 1С OData. Это не критично - склады можно синхронизировать из продаж.")
        return []

    def map_1c_to_store(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Маппинг данных из 1С в модель Store"""
        # В 1С OData обычно используется Ref_Key для ID
        external_id = item.get("Ref_Key") or item.get("Ref") or item.get("Key")
        
        # Название склада
        name = item.get("Description") or item.get("Наименование") or item.get("Name") or ""
        
        # Адрес может быть в разных полях
        address = (
            item.get("Адрес") 
            or item.get("Address") 
            or item.get("АдресПолный")
            or item.get("FullAddress")
        )
        
        # Город
        city = item.get("Город") or item.get("City") or item.get("НаселенныйПункт")

        return {
            "external_id": external_id,
            "name": name,
            "address": address,
            "city": city,
            "is_active": True,  # По умолчанию активен
            "1c_data": item,  # Сохраняем полные данные из 1С
        }

    async def sync_stores(self, update_existing: bool = True) -> Dict[str, Any]:
        """Синхронизация складов из 1С"""
        try:
            items = await self.fetch_stores()
        except Exception as e:
            # Каталог складов может быть недоступен в некоторых версиях 1С
            # Это не критично - склады можно синхронизировать из продаж
            logger.info(f"Каталог складов недоступен в 1С OData: {str(e)}")
            logger.info("Синхронизация складов пропущена. Это не критично - склады можно получить из продаж.")
            return {
                "created": 0,
                "updated": 0,
                "error_count": 0,
                "errors": [],
                "skipped": True,
                "message": "Каталог складов недоступен в 1С OData. Склады можно синхронизировать из продаж.",
            }
        
        created = 0
        updated = 0
        errors: List[str] = []

        for item in items:
            try:
                mapped = self.map_1c_to_store(item)
                external_id = mapped.get("external_id")

                if not external_id:
                    errors.append(f"Склад без external_id: {mapped.get('name', 'Unknown')}")
                    continue

                # Ищем существующий склад по external_id
                result = await self.db.execute(
                    select(Store).where(Store.external_id == external_id)
                )
                store = result.scalars().first()

                if store:
                    if update_existing:
                        # Обновляем существующий склад
                        store.name = mapped.get("name") or store.name
                        store.address = mapped.get("address") or store.address
                        store.city = mapped.get("city") or store.city
                        # Можно добавить сохранение 1c_data в JSON поле, если нужно
                        updated += 1
                else:
                    # Создаем новый склад
                    if not mapped.get("name"):
                        mapped["name"] = external_id or "Unnamed store"
                    
                    new_store = Store(**{k: v for k, v in mapped.items() if k != "1c_data"})
                    self.db.add(new_store)
                    created += 1
            except Exception as exc:
                error_msg = f"Ошибка синхронизации склада {item.get('Description', 'Unknown')}: {exc}"
                logger.error(error_msg, exc_info=True)
                errors.append(error_msg)

        await self.db.commit()

        return {
            "created": created,
            "updated": updated,
            "error_count": len(errors),
            "errors": errors[:10],  # Первые 10 ошибок
        }
