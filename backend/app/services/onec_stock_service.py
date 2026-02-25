"""
Сервис для синхронизации остатков по складам из 1С через CommerceML XML (offers.xml).
OData методы удалены. Используется только XML импорт.
"""
import logging
import os
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_stock import ProductStock
from app.models.store import Store
from app.services.commerceml_xml_service import CommerceMLXMLService

logger = logging.getLogger(__name__)


class OneCStockService:
    """
    Сервис для синхронизации остатков товаров из CommerceML XML (offers.xml).
    OData методы удалены - используется только XML импорт.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

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
