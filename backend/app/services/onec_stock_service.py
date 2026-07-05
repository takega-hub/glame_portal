"""
Сервис для синхронизации остатков по складам из 1С.
Поддерживает CommerceML XML (offers.xml) и OData движения регистра запасов.
"""
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_stock import ProductStock
from app.models.store import Store
from app.services.commerceml_xml_service import CommerceMLXMLService

logger = logging.getLogger(__name__)


class OneCStockService:
    """
    Сервис для синхронизации остатков товаров из CommerceML XML (offers.xml)
    и OData регистра `ЗапасыНаСкладах`.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def _onec_headers(self) -> Dict[str, str]:
        token = os.getenv("ONEC_API_TOKEN")
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = token if token.startswith("Basic ") else f"Basic {token}"
        return headers

    async def _fetch_odata_stock_movements(
        self,
        *,
        page_size: int = 1000,
        period_from: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        api_url = os.getenv("ONEC_API_URL")
        if not api_url:
            raise ValueError("ONEC_API_URL is not set")

        endpoint = os.getenv(
            "ONEC_STOCKS_ODATA_ENDPOINT",
            "/AccumulationRegister_ЗапасыНаСкладах_RecordType",
        )
        select_fields = ",".join(
            [
                "Period",
                "Active",
                "RecordType",
                "Номенклатура_Key",
                "Характеристика_Key",
                "СтруктурнаяЕдиница_Key",
                "Количество",
            ]
        )
        filters = ["Active eq true"]
        if period_from:
            period_text = period_from.astimezone(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
            filters.append(f"Period ge datetime'{period_text}'")

        rows: List[Dict[str, Any]] = []
        skip = 0
        url = f"{api_url.rstrip('/')}{endpoint}"
        headers = self._onec_headers()
        async with httpx.AsyncClient(timeout=120.0, headers=headers) as client:
            while True:
                params = {
                    "$top": page_size,
                    "$skip": skip,
                    "$select": select_fields,
                    "$filter": " and ".join(filters),
                }
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                page = data.get("value") or []
                rows.extend(page)
                if len(page) < page_size:
                    break
                skip += page_size
        return rows

    @staticmethod
    def _product_external_id_from_stock_row(row: Dict[str, Any]) -> Optional[str]:
        product_key = str(row.get("Номенклатура_Key") or "").strip()
        characteristic_key = str(row.get("Характеристика_Key") or "").strip()
        if not product_key or product_key == "00000000-0000-0000-0000-000000000000":
            return None
        if characteristic_key and characteristic_key != "00000000-0000-0000-0000-000000000000":
            return f"{product_key}#{characteristic_key}"
        return product_key

    async def sync_stocks_from_odata_movements(
        self,
        *,
        page_size: int = 1000,
        replace_all: bool = True,
        dry_run: bool = False,
        period_from: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Синхронизация остатков через OData регистр движений 1С:
        AccumulationRegister_ЗапасыНаСкладах_RecordType.

        В текущей публикации 1С виртуальная таблица `_Остатки` не доступна,
        поэтому остаток рассчитывается как сумма Receipt минус Expense.
        """
        rows = await self._fetch_odata_stock_movements(page_size=page_size, period_from=period_from)
        balances: Dict[tuple[str, str], float] = defaultdict(float)
        product_key_by_external_id: Dict[str, str] = {}
        skipped = 0
        unknown_record_types: Dict[str, int] = defaultdict(int)

        for row in rows:
            product_external_id = self._product_external_id_from_stock_row(row)
            product_key = str(row.get("Номенклатура_Key") or "").strip()
            store_id = str(row.get("СтруктурнаяЕдиница_Key") or "").strip()
            if not product_external_id or not store_id:
                skipped += 1
                continue
            try:
                quantity = float(row.get("Количество") or 0)
            except (TypeError, ValueError):
                skipped += 1
                continue

            record_type = str(row.get("RecordType") or "").strip()
            if record_type == "Receipt":
                sign = 1.0
            elif record_type == "Expense":
                sign = -1.0
            else:
                unknown_record_types[record_type or "empty"] += 1
                continue
            balances[(product_external_id, store_id)] += sign * quantity
            product_key_by_external_id[product_external_id] = product_key

        product_external_ids = sorted(
            {
                product_external_id
                for product_external_id, _store_id in balances
            }
            | {
                product_key
                for product_key in product_key_by_external_id.values()
                if product_key and product_key != "00000000-0000-0000-0000-000000000000"
            }
        )
        product_by_external_id: Dict[str, Product] = {}
        chunk_size = 1000
        for index in range(0, len(product_external_ids), chunk_size):
            chunk = product_external_ids[index : index + chunk_size]
            result = await self.db.execute(select(Product).where(Product.external_id.in_(chunk)))
            for product in result.scalars().all():
                if product.external_id:
                    product_by_external_id[str(product.external_id)] = product

        if replace_all and not dry_run:
            existing_result = await self.db.execute(select(ProductStock))
            for stock in existing_result.scalars().all():
                stock.quantity = 0.0
                stock.available_quantity = 0.0
                stock.reserved_quantity = 0.0
                stock.last_synced_at = datetime.now(timezone.utc)

        created = 0
        updated = 0
        zeroed = 0
        unmatched = 0
        matched = 0
        parent_fallback_matched = 0
        resolved_balances: Dict[tuple[Any, str], float] = defaultdict(float)
        product_by_id: Dict[Any, Product] = {}
        stores_found = set()
        now = datetime.now(timezone.utc)

        for (product_external_id, store_id), quantity in balances.items():
            product = product_by_external_id.get(product_external_id)
            if not product:
                parent_external_id = product_key_by_external_id.get(product_external_id)
                product = product_by_external_id.get(parent_external_id or "")
                if product:
                    parent_fallback_matched += 1
            if not product:
                unmatched += 1
                continue
            matched += 1
            product_by_id[product.id] = product
            resolved_balances[(product.id, store_id)] += quantity

        for (product_id, store_id), quantity in resolved_balances.items():
            product = product_by_id[product_id]
            quantity = max(0.0, float(quantity))
            stores_found.add(store_id)
            if dry_run:
                if quantity <= 0:
                    zeroed += 1
                continue

            stock_result = await self.db.execute(
                select(ProductStock).where(
                    (ProductStock.product_id == product.id)
                    & (ProductStock.store_id == store_id)
                )
            )
            stock = stock_result.scalar_one_or_none()
            if stock:
                stock.quantity = quantity
                stock.available_quantity = quantity
                stock.reserved_quantity = 0.0
                stock.last_synced_at = now
                updated += 1
                if quantity <= 0:
                    zeroed += 1
            else:
                self.db.add(
                    ProductStock(
                        product_id=product.id,
                        store_id=store_id,
                        quantity=quantity,
                        reserved_quantity=0.0,
                        available_quantity=quantity,
                        last_synced_at=now,
                    )
                )
                created += 1

            if (created + updated) % 500 == 0:
                await self.db.flush()

        if dry_run:
            await self.db.rollback()
        else:
            await self.db.commit()
        logger.info(
            "OData stock sync finished: dry_run=%s movements=%s balances=%s matched=%s created=%s updated=%s unmatched=%s",
            dry_run,
            len(rows),
            len(balances),
            matched,
            created,
            updated,
            unmatched,
        )
        return {
            "source": "odata",
            "endpoint": os.getenv("ONEC_STOCKS_ODATA_ENDPOINT", "/AccumulationRegister_ЗапасыНаСкладах_RecordType"),
            "movements": len(rows),
            "balances": len(balances),
            "resolved_balances": len(resolved_balances),
            "matched": matched,
            "parent_fallback_matched": parent_fallback_matched,
            "created": created,
            "updated": updated,
            "zeroed": zeroed,
            "skipped": skipped,
            "unmatched": unmatched,
            "stores_found": sorted(stores_found),
            "stores_count": len(stores_found),
            "unknown_record_types": dict(unknown_record_types),
            "replace_all": replace_all,
            "dry_run": dry_run,
            "period_from": period_from.isoformat() if period_from else None,
        }

    async def sync_stores_from_xml(self, xml_content: bytes) -> Dict[str, Any]:
        """
        Синхронизация складов/магазинов из offers.xml
        
        Args:
            xml_content: Бинарные данные offers.xml файла
        
        Returns:
            Словарь со статистикой синхронизации складов
        """
        created = 0
        updated = 0
        skipped = 0
        
        try:
            # Парсим склады из offers.xml
            xml_service = CommerceMLXMLService()
            stores_data = xml_service.parse_stores_from_offers_xml(xml_content)
            
            if not stores_data:
                logger.warning("Склады не найдены в offers.xml")
                return {
                    'created': 0,
                    'updated': 0,
                    'skipped': 0,
                    'total': 0
                }
            
            logger.info(f"Найдено {len(stores_data)} складов для синхронизации")
            
            # Синхронизируем каждый склад
            for store_data in stores_data:
                try:
                    external_id = store_data.get('external_id')
                    name = store_data.get('name')
                    
                    if not external_id:
                        logger.warning(f"Склад без external_id пропущен: {name}")
                        skipped += 1
                        continue
                    
                    # Ищем существующий склад по external_id
                    result = await self.db.execute(
                        select(Store).where(Store.external_id == external_id)
                    )
                    store = result.scalar_one_or_none()
                    
                    if store:
                        # Обновляем существующий склад
                        if name and store.name != name:
                            store.name = name
                            updated += 1
                        else:
                            skipped += 1
                    else:
                        # Создаем новый склад
                        new_store = Store(
                            external_id=external_id,
                            name=name or external_id,
                            is_active=True
                        )
                        self.db.add(new_store)
                        created += 1
                        
                except Exception as e:
                    logger.error(f"Ошибка синхронизации склада {store_data.get('name', 'Unknown')}: {e}", exc_info=True)
                    skipped += 1
                    continue
            
            await self.db.commit()
            logger.info(f"Синхронизация складов завершена: создано {created}, обновлено {updated}, пропущено {skipped}")
            
            return {
                'created': created,
                'updated': updated,
                'skipped': skipped,
                'total': len(stores_data)
            }
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Ошибка синхронизации складов из offers.xml: {e}", exc_info=True)
            raise

    async def sync_stocks_from_offers_data(self, offers_data: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Синхронизация остатков из уже распарсенных данных offers.xml
        
        Args:
            offers_data: Словарь предложений {offer_id: {price, quantity, article, ...}}
        
        Returns:
            Словарь со статистикой синхронизации
        """
        created = 0
        updated = 0
        skipped = 0
        errors: List[str] = []
        
        try:
            logger.info(f"Получено {len(offers_data)} предложений для синхронизации остатков")
            
            # Собираем статистику по складам
            stores_found = set()
            
            # Обновляем остатки для каждого предложения
            for offer_id, offer_info in offers_data.items():
                try:
                    product_id = offer_info.get('product_id')
                    characteristic_id = offer_info.get('characteristic_id')
                    article = offer_info.get('article')
                    
                    if not product_id:
                        logger.warning(f"Предложение {offer_id} не имеет product_id, пропускаем")
                        skipped += 1
                        continue
                    
                    product = None
                    
                    product = None
                    
                    # Если есть characteristic_id (вариант товара), ищем ТОЛЬКО по артикулу варианта
                    # НЕ ищем по базовому артикулу, так как остатки должны быть у варианта, а не у родителя
                    if characteristic_id and article:
                        # Пробуем точное совпадение артикула варианта
                        result = await self.db.execute(
                            select(Product).where(Product.article == article)
                        )
                        product = result.scalar_one_or_none()
                        
                        if not product:
                            skipped += 1
                            continue  # Пропускаем вариант, если не найден - не сохраняем остатки для родителя
                    
                    # Если это НЕ вариант (нет characteristic_id), ищем по external_id родителя
                    elif not characteristic_id:
                        result = await self.db.execute(
                            select(Product).where(Product.external_id == product_id)
                        )
                        product = result.scalar_one_or_none()
                        
                        if not product and article:
                            # Пробуем найти по артикулу
                            result = await self.db.execute(
                                select(Product).where(Product.article == article)
                            )
                            product = result.scalar_one_or_none()
                    
                    if not product:
                        skipped += 1
                        continue
                    
                    # Получаем остатки по складам из offers.xml
                    store_stocks = offer_info.get('store_stocks', {})
                    
                    if store_stocks:
                        # Если есть разбивка по складам - используем её
                        for store_id_1c, quantity in store_stocks.items():
                            stores_found.add(store_id_1c)
                            
                            try:
                                quantity_float = float(quantity)
                                
                                # Ищем существующий остаток для этого товара и склада
                                stock_result = await self.db.execute(
                                    select(ProductStock).where(
                                        (ProductStock.product_id == product.id)
                                        & (ProductStock.store_id == store_id_1c)
                                    )
                                )
                                stock = stock_result.scalar_one_or_none()
                                
                                if stock:
                                    stock.quantity = quantity_float
                                    stock.available_quantity = quantity_float
                                    updated += 1
                                else:
                                    # Создаем новый остаток для этого склада
                                    new_stock = ProductStock(
                                        product_id=product.id,
                                        store_id=store_id_1c,
                                        quantity=quantity_float,
                                        reserved_quantity=0.0,
                                        available_quantity=quantity_float,
                                    )
                                    self.db.add(new_stock)
                                    created += 1
                                
                            except (ValueError, TypeError) as e:
                                logger.warning(f"Ошибка обработки остатка для склада {store_id_1c}: {e}")
                                continue
                    else:
                        # Если нет разбивки по складам, но есть общее количество
                        # Используем склад по умолчанию (для обратной совместимости)
                        quantity = offer_info.get('quantity', 0)
                        if quantity is None:
                            skipped += 1
                            continue
                        
                        default_store_id = "default_store"
                        stores_found.add(default_store_id)
                        
                        try:
                            quantity_float = float(quantity)
                            
                            # Ищем существующий остаток
                            stock_result = await self.db.execute(
                                select(ProductStock).where(
                                    (ProductStock.product_id == product.id)
                                    & (ProductStock.store_id == default_store_id)
                                )
                            )
                            stock = stock_result.scalar_one_or_none()
                            
                            if stock:
                                stock.quantity = quantity_float
                                stock.available_quantity = quantity_float
                                updated += 1
                            else:
                                # Создаем новый остаток
                                new_stock = ProductStock(
                                    product_id=product.id,
                                    store_id=default_store_id,
                                    quantity=quantity_float,
                                    reserved_quantity=0.0,
                                    available_quantity=quantity_float,
                                )
                                self.db.add(new_stock)
                                created += 1
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Ошибка обработки общего остатка: {e}")
                            skipped += 1
                            continue
                    
                    # Коммитим каждые 100 записей
                    if (created + updated) % 100 == 0:
                        await self.db.commit()
                        
                except Exception as exc:
                    error_msg = f"Ошибка синхронизации остатков для предложения {offer_id}: {exc}"
                    logger.warning(error_msg)
                    errors.append(error_msg)
            
            await self.db.commit()
            
            logger.info(f"Синхронизация остатков завершена: создано {created}, обновлено {updated}, пропущено {skipped}")
            logger.info(f"Найдено складов в offers.xml: {len(stores_found)} - {', '.join(sorted(stores_found))}")
            
            return {
                "total": len(offers_data),
                "created": created,
                "updated": updated,
                "skipped": skipped,
                "stores_found": list(stores_found),
                "stores_count": len(stores_found),
                "errors": errors[:20],
                "error_count": len(errors),
            }
            
        except Exception as e:
            logger.error(f"Ошибка при синхронизации остатков: {e}", exc_info=True)
            raise
    
    async def sync_stocks_from_xml(self, xml_url: str) -> Dict[str, Any]:
        """
        Синхронизация остатков из offers.xml по URL
        
        Args:
            xml_url: URL к offers.xml файлу
        
        Returns:
            Словарь со статистикой синхронизации
        """
        try:
            # Загружаем offers.xml
            async with CommerceMLXMLService() as xml_service:
                xml_content = await xml_service.download_xml_from_url(xml_url)
                
                # Сначала синхронизируем склады из offers.xml
                stores_result = await self.sync_stores_from_xml(xml_content)
                logger.info(f"Синхронизация складов: создано {stores_result.get('created', 0)}, обновлено {stores_result.get('updated', 0)}")
                
                # Затем парсим предложения
                offers_data = xml_service.parse_offers_xml(xml_content)
            
            logger.info(f"Загружено {len(offers_data)} предложений из offers.xml для синхронизации остатков")
            
            # Используем общий метод синхронизации остатков
            stocks_result = await self.sync_stocks_from_offers_data(offers_data)
            
            # Добавляем информацию о синхронизации складов в результат
            stocks_result['stores_synced'] = stores_result
            
            return stocks_result
        except Exception as e:
            logger.error(f"Ошибка при синхронизации остатков из XML: {e}", exc_info=True)
            raise
