"""
Сервис синхронизации продаж из 1С УНФ ФРЕШ
Оптимизирован для работы с большими объемами данных
"""
import httpx
import base64
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
import os
import uuid

from app.models.sales_record import SalesRecord
from app.models.sales_metric import SalesMetric
from app.models.product import Product
from app.services.onec_sales_service import OneCSalesService

logger = logging.getLogger(__name__)

# Список ключевых слов для исключения товаров из продаж
EXCLUDED_PRODUCT_KEYWORDS = [
    'упаковка', 'упаковки', 'packaging', 'pack',
    'салфетк', 'napkin', 'салфетка', 'салфетки',
    'сертификат', 'certificate', 'подарочный сертификат', 'gift certificate',
    'подарочный', 'gift card'
]

# Список категорий для исключения
EXCLUDED_CATEGORIES = [
    'упаковка', 'упаковки',
    'салфетки',
    'сертификаты', 'подарочные сертификаты'
]


def _should_exclude_product(product_name: Optional[str] = None, 
                            product_category: Optional[str] = None,
                            product_article: Optional[str] = None) -> bool:
    """
    Проверяет, нужно ли исключить товар из продаж
    
    Args:
        product_name: Название товара
        product_category: Категория товара
        product_article: Артикул товара
    
    Returns:
        True если товар нужно исключить, False если нужно включить
    """
    # Проверяем по названию товара
    if product_name:
        product_name_lower = product_name.lower()
        for keyword in EXCLUDED_PRODUCT_KEYWORDS:
            if keyword.lower() in product_name_lower:
                logger.debug(f"Исключен товар по названию: {product_name} (ключевое слово: {keyword})")
                return True
    
    # Проверяем по категории
    if product_category:
        category_lower = product_category.lower()
        for excluded_cat in EXCLUDED_CATEGORIES:
            if excluded_cat.lower() in category_lower:
                logger.debug(f"Исключен товар по категории: {product_name} (категория: {product_category})")
                return True
    
    return False


class OneCSalesSyncService:
    """Сервис для синхронизации продаж из 1С в БД"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.sales_service = None
    
    async def __aenter__(self):
        self.sales_service = OneCSalesService()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.sales_service:
            await self.sales_service.close()
    
    def _generate_batch_id(self) -> str:
        """Генерация ID пакета синхронизации"""
        return f"sync_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    async def sync_period(
        self,
        start_date: datetime,
        end_date: datetime,
        batch_id: Optional[str] = None,
        incremental: bool = True
    ) -> Dict[str, Any]:
        """
        Синхронизация продаж за период
        
        Args:
            start_date: Начальная дата
            end_date: Конечная дата
            batch_id: ID пакета синхронизации (если None, генерируется автоматически)
            incremental: Если True, синхронизирует только новые данные
        
        Returns:
            Статистика синхронизации
        """
        if not batch_id:
            batch_id = self._generate_batch_id()
        
        logger.info(f"Начало синхронизации продаж за период {start_date.date()} - {end_date.date()}, batch_id={batch_id}")
        
        # Проверяем, существует ли таблица sales_records (простая проверка через запрос)
        try:
            await self.db.execute(select(SalesRecord).limit(0))
        except Exception as e:
            error_msg = str(e).lower()
            if "does not exist" in error_msg or "не существует" in error_msg or "relation" in error_msg:
                logger.error("Таблица sales_records не существует. Запустите: python backend/create_sales_tables.py")
                raise ValueError(
                    "Таблица sales_records не существует. "
                    "Запустите скрипт создания таблиц: python backend/create_sales_tables.py"
                )
            else:
                # Если это не ошибка отсутствия таблицы, просто логируем и продолжаем
                logger.warning(f"Предупреждение при проверке таблицы: {e}")
        
        # Получаем данные из 1С
        sales_data = await self.sales_service.fetch_sales_from_api(start_date, end_date)
        orders = sales_data.get("orders", [])
        
        logger.info(f"Получено {len(orders)} записей о продажах из 1С")
        
        # Логируем статистику по магазинам и товарам для отладки
        if orders:
            stores_count = len(set(o.get("store_id") for o in orders if o.get("store_id")))
            products_count = len(set(o.get("product_id") for o in orders if o.get("product_id")))
            logger.info(f"Статистика: {stores_count} уникальных магазинов, {products_count} уникальных товаров")
        
        if not orders:
            return {
                "batch_id": batch_id,
                "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
                "total_records": 0,
                "inserted": 0,
                "updated": 0,
                "skipped": 0
            }
        
        # Если инкрементальная синхронизация, проверяем какие записи уже есть
        existing_ids = set()
        if incremental:
            # Получаем список уже существующих external_id за этот период
            result = await self.db.execute(
                select(SalesRecord.external_id, SalesRecord.document_id)
                .where(
                    and_(
                        SalesRecord.sale_date >= start_date,
                        SalesRecord.sale_date <= end_date,
                        SalesRecord.external_id.isnot(None)
                    )
                )
            )
            existing_ids = {row[0] for row in result.all() if row[0]}
            logger.info(f"Найдено {len(existing_ids)} существующих записей за период")
        
        # Подготавливаем записи для вставки
        records_to_insert = []
        records_to_update = []
        skipped = 0
        
        for order in orders:
            # Формируем external_id из данных заказа
            external_id = order.get("id") or order.get("document_id")
            if not external_id:
                skipped += 1
                continue
            
            # Получаем данные о товаре из заказа
            product_id_1c = order.get("product_id")
            product_name = order.get("product_name")
            product_category = order.get("product_category")
            product_article = order.get("product_article")
            
            # Извлекаем Характеристика_Key из raw_data (это ID варианта товара)
            characteristic_id = None
            raw_data = order.get("raw_1c_data", order)
            if raw_data and isinstance(raw_data, dict):
                characteristic_id = raw_data.get("Характеристика_Key")
                # Если characteristic_id это GUID с нулями, игнорируем его
                if characteristic_id == "00000000-0000-0000-0000-000000000000":
                    characteristic_id = None
            
            # Пытаемся получить данные о товаре из базы данных для обогащения
            product_data = None
            if product_id_1c:
                try:
                    from app.models.product import Product
                    
                    # Если есть characteristic_id, ищем вариант товара
                    variant_external_id = None
                    if characteristic_id:
                        variant_external_id = f"{product_id_1c}#{characteristic_id}"
                        logger.debug(f"Ищем вариант товара: {variant_external_id}")
                        product_result = await self.db.execute(
                            select(Product).where(Product.external_id == variant_external_id)
                        )
                        product = product_result.scalar_one_or_none()
                        
                        if product:
                            logger.debug(f"Найден вариант: {product.article} ({product.name})")
                            product_data = {
                                "name": product.name,
                                "article": product.article,
                                "category": product.category,
                                "brand": product.brand
                            }
                    
                    # Если вариант не найден или нет characteristic_id, ищем родителя
                    if not product_data:
                        product_result = await self.db.execute(
                            select(Product).where(Product.external_id == product_id_1c)
                        )
                        product = product_result.scalar_one_or_none()
                        if product:
                            product_data = {
                                "name": product.name,
                                "article": product.article,
                                "category": product.category,
                                "brand": product.brand
                            }
                except Exception as e:
                    logger.debug(f"Не удалось получить данные о товаре {product_id_1c}: {e}")
            
            # Если нашли товар в базе, используем его данные, иначе данные из заказа
            if product_data:
                product_name = product_data.get("name") or product_name
                product_category = product_data.get("category") or product_category
                product_article = product_data.get("article") or product_article
            
            # Проверяем, нужно ли исключить этот товар
            if _should_exclude_product(product_name, product_category, product_article):
                skipped += 1
                logger.debug(f"Пропущена продажа товара: {product_name} (категория: {product_category})")
                continue
            
            # Проверяем, существует ли уже запись
            if incremental and external_id in existing_ids:
                # Обновляем существующую запись
                update_record = {
                    "external_id": external_id,
                    "revenue": order.get("revenue", 0),
                    "quantity": order.get("items_count", 0),
                    "sale_date": self._parse_date(order.get("date")),
                    "store_id": order.get("store_id"),
                    "customer_id": order.get("customer_id"),
                    "product_id": product_id_1c,
                    "organization_id": order.get("organization_id"),
                    "channel": order.get("channel", "offline"),
                    "raw_data": order.get("raw_1c_data", order),  # Сохраняем исходные данные из 1С, если есть
                    "updated_at": datetime.now(),
                    "sync_batch_id": batch_id
                }
                # Добавляем данные о товаре, если они есть
                if product_data:
                    update_record.update({
                        "product_name": product_data.get("name") or order.get("product_name"),
                        "product_article": product_data.get("article") or order.get("product_article"),
                        "product_category": product_data.get("category") or order.get("product_category"),
                        "product_brand": product_data.get("brand") or order.get("product_brand")
                    })
                else:
                    # Используем данные из заказа, если они есть
                    update_record.update({
                        "product_name": order.get("product_name"),
                        "product_article": order.get("product_article"),
                        "product_category": order.get("product_category"),
                        "product_brand": order.get("product_brand")
                    })
                records_to_update.append(update_record)
            else:
                # Новая запись
                sale_date = self._parse_date(order.get("date"))
                if not sale_date:
                    skipped += 1
                    continue
                
                insert_record = {
                    "id": uuid.uuid4(),
                    "external_id": external_id,
                    "document_id": order.get("document_id"),
                    "sale_date": sale_date,
                    "store_id": order.get("store_id"),
                    "customer_id": order.get("customer_id"),
                    "product_id": product_id_1c,
                    "organization_id": order.get("organization_id"),
                    "revenue": order.get("revenue", 0),
                    "quantity": order.get("items_count", 0),
                    "revenue_without_discount": order.get("revenue_without_discount"),
                    "channel": order.get("channel", "offline"),
                    "raw_data": order.get("raw_1c_data", order),  # Сохраняем исходные данные из 1С, если есть
                    "sync_batch_id": batch_id,
                    "synced_at": datetime.now()
                }
                # Добавляем данные о товаре, если они есть
                if product_data:
                    insert_record.update({
                        "product_name": product_data.get("name") or order.get("product_name"),
                        "product_article": product_data.get("article") or order.get("product_article"),
                        "product_category": product_data.get("category") or order.get("product_category"),
                        "product_brand": product_data.get("brand") or order.get("product_brand")
                    })
                else:
                    # Используем данные из заказа, если они есть
                    insert_record.update({
                        "product_name": order.get("product_name"),
                        "product_article": order.get("product_article"),
                        "product_category": order.get("product_category"),
                        "product_brand": order.get("product_brand")
                    })
                records_to_insert.append(insert_record)
        
        # Вставляем новые записи
        inserted = 0
        updated = 0  # Инициализируем переменную для подсчета обновленных записей
        if records_to_insert:
            try:
                # Используем bulk insert для производительности
                # Для PostgreSQL используем on_conflict_do_update
                # Важно: external_id должен быть не NULL для работы on_conflict_do_update
                # Фильтруем записи с external_id для bulk insert
                records_with_id = [r for r in records_to_insert if r.get('external_id')]
                records_without_id = [r for r in records_to_insert if not r.get('external_id')]
                
                # Дедуплицируем записи по external_id (берем последнюю версию)
                if records_with_id:
                    seen_ids = {}
                    deduplicated_records = []
                    for r in records_with_id:
                        ext_id = r.get('external_id')
                        if ext_id:
                            seen_ids[ext_id] = r  # Последняя версия перезаписывает предыдущую
                    records_with_id = list(seen_ids.values())
                    logger.info(f"После дедупликации осталось {len(records_with_id)} записей с external_id")
                
                # Bulk insert для записей с external_id (с on_conflict_do_update)
                if records_with_id:
                    try:
                        stmt = pg_insert(SalesRecord).values(records_with_id)
                        stmt = stmt.on_conflict_do_update(
                            index_elements=['external_id'],
                            set_={
                                'revenue': stmt.excluded.revenue,
                                'quantity': stmt.excluded.quantity,
                                'sale_date': stmt.excluded.sale_date,
                                'store_id': stmt.excluded.store_id,
                                'customer_id': stmt.excluded.customer_id,
                                'product_id': stmt.excluded.product_id,
                                'product_name': stmt.excluded.product_name,
                                'product_article': stmt.excluded.product_article,
                                'product_category': stmt.excluded.product_category,
                                'product_brand': stmt.excluded.product_brand,
                                'updated_at': datetime.now(),
                                'sync_batch_id': stmt.excluded.sync_batch_id,
                                'raw_data': stmt.excluded.raw_data
                            }
                        )
                        await self.db.execute(stmt)
                        inserted += len(records_with_id)
                    except Exception as bulk_error:
                        # Если bulk insert не удался (например, из-за UniqueViolation), 
                        # переходим к fallback методу
                        logger.warning(f"Bulk insert не удался, переходим к fallback методу: {bulk_error}")
                        raise  # Пробрасываем ошибку, чтобы сработал общий catch блок
                
                # Обычная вставка для записей без external_id
                if records_without_id:
                    for record_data in records_without_id:
                        new_record = SalesRecord(**record_data)
                        self.db.add(new_record)
                        inserted += 1
                
                await self.db.commit()
                logger.info(f"Вставлено {inserted} новых записей")
            except Exception as e:
                logger.error(f"Ошибка при bulk insert: {e}", exc_info=True)
                # Откатываем транзакцию перед fallback методом
                await self.db.rollback()
                # Fallback: вставляем по одной записи
                logger.info("Пробуем вставить записи по одной...")
                inserted = 0
                fallback_updated = 0
                for record_data in records_to_insert:
                    try:
                        # Используем точку сохранения для каждой записи, 
                        # чтобы ошибка в одной записи не прерывала всю транзакцию
                        async with self.db.begin_nested():
                            if record_data.get("external_id"):
                                # Сначала проверяем существование
                                result = await self.db.execute(
                                    select(SalesRecord).where(
                                        SalesRecord.external_id == record_data["external_id"]
                                    )
                                )
                                existing = result.scalar_one_or_none()
                                
                                if existing:
                                    # Обновляем существующую
                                    for key, value in record_data.items():
                                        if key != "id" and hasattr(existing, key):
                                            setattr(existing, key, value)
                                    existing.updated_at = datetime.now()
                                    fallback_updated += 1
                                else:
                                    # Создаем новую
                                    new_record = SalesRecord(**record_data)
                                    self.db.add(new_record)
                                    inserted += 1
                            else:
                                # Если нет external_id, просто создаем новую запись
                                new_record = SalesRecord(**record_data)
                                self.db.add(new_record)
                                inserted += 1
                    except Exception as record_error:
                        logger.warning(f"Ошибка при обработке записи {record_data.get('external_id')}: {record_error}")
                        # begin_nested() сам сделает rollback до точки сохранения при ошибке
                        continue
                
                try:
                    await self.db.commit()
                    logger.info(f"Вставлено {inserted} записей, обновлено {fallback_updated} записей (fallback метод)")
                    # Обновляем счетчик updated для общего результата
                    updated += fallback_updated
                except Exception as commit_error:
                    await self.db.rollback()
                    logger.error(f"Ошибка при коммите (fallback метод): {commit_error}", exc_info=True)
                    raise
        
        # Обновляем существующие записи (если они не были обновлены в fallback методе)
        if records_to_update:
            for record_data in records_to_update:
                result = await self.db.execute(
                    select(SalesRecord).where(SalesRecord.external_id == record_data["external_id"])
                )
                existing = result.scalar_one_or_none()
                if existing:
                    for key, value in record_data.items():
                        if key != "external_id":
                            setattr(existing, key, value)
                    updated += 1
            
            await self.db.commit()
            logger.info(f"Обновлено {updated} существующих записей")
        else:
            await self.db.commit()
        
        # Агрегируем метрики по дням
        await self._aggregate_daily_metrics(start_date, end_date)
        
        # Логируем итоговую статистику по магазинам и товарам
        if inserted > 0 or updated > 0:
            stats_result = await self.db.execute(
                select(
                    func.count(func.distinct(SalesRecord.store_id)).label('stores'),
                    func.count(func.distinct(SalesRecord.product_id)).label('products'),
                    func.count(func.distinct(func.date(SalesRecord.sale_date))).label('days')
                ).where(
                    and_(
                        SalesRecord.sale_date >= start_date,
                        SalesRecord.sale_date <= end_date,
                        SalesRecord.sync_batch_id == batch_id
                    )
                )
            )
            stats = stats_result.first()
            if stats:
                logger.info(f"Синхронизировано: {stats.stores} магазинов, {stats.products} товаров, {stats.days} дней")
        
        return {
            "batch_id": batch_id,
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "total_records": len(orders),
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped
        }
    
    def _parse_date(self, date_value: Any) -> Optional[datetime]:
        """Парсинг даты из различных форматов"""
        if not date_value:
            return None
        
        if isinstance(date_value, datetime):
            return date_value
        
        if isinstance(date_value, str):
            try:
                # Пробуем разные форматы
                for fmt in [
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S.%f",
                    "%Y-%m-%dT%H:%M:%SZ",
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d"
                ]:
                    try:
                        return datetime.strptime(date_value.split('.')[0].replace('Z', ''), fmt)
                    except:
                        continue
                # Если ничего не подошло, пробуем ISO формат
                return datetime.fromisoformat(date_value.replace('Z', '+00:00').split('.')[0])
            except:
                logger.warning(f"Не удалось распарсить дату: {date_value}")
                return None
        
        return None
    
    async def _aggregate_daily_metrics(
        self,
        start_date: datetime,
        end_date: datetime
    ):
        """Агрегация метрик по дням из детальных записей"""
        # Получаем все записи за период
        result = await self.db.execute(
            select(SalesRecord)
            .where(
                and_(
                    SalesRecord.sale_date >= start_date,
                    SalesRecord.sale_date <= end_date
                )
            )
        )
        records = result.scalars().all()
        
        # Группируем по дням
        daily_metrics = {}
        for record in records:
            # Округляем дату до дня
            day_key = record.sale_date.date()
            
            if day_key not in daily_metrics:
                daily_metrics[day_key] = {
                    "revenue": 0.0,
                    "orders": set(),  # Уникальные заказы
                    "items_sold": 0.0,
                    "by_store": {},
                    "by_channel": {}
                }
            
            daily_metrics[day_key]["revenue"] += record.revenue
            # Используем document_id для подсчета уникальных заказов
            daily_metrics[day_key]["orders"].add(record.document_id or record.external_id or record.id)
            daily_metrics[day_key]["items_sold"] += record.quantity
            
            # По магазинам
            store_id = record.store_id or "unknown"
            if store_id not in daily_metrics[day_key]["by_store"]:
                daily_metrics[day_key]["by_store"][store_id] = {
                    "revenue": 0.0, 
                    "orders_set": set(),  # Используем set для уникальных заказов
                    "items_sold": 0
                }
            daily_metrics[day_key]["by_store"][store_id]["revenue"] += record.revenue
            daily_metrics[day_key]["by_store"][store_id]["orders_set"].add(record.document_id or record.external_id or str(record.id))
            daily_metrics[day_key]["by_store"][store_id]["items_sold"] += int(record.quantity)
            
            # По каналам
            channel = record.channel or "unknown"
            if channel not in daily_metrics[day_key]["by_channel"]:
                daily_metrics[day_key]["by_channel"][channel] = {
                    "revenue": 0.0, 
                    "orders_set": set()
                }
            daily_metrics[day_key]["by_channel"][channel]["revenue"] += record.revenue
            daily_metrics[day_key]["by_channel"][channel]["orders_set"].add(record.document_id or record.external_id or str(record.id))
        
        # Сохраняем агрегированные метрики
        for day_key, metrics in daily_metrics.items():
            order_count = len(metrics["orders"])
            avg_order_value = metrics["revenue"] / order_count if order_count > 0 else 0.0
            
            # Подготавливаем данные по магазинам (преобразуем set в count)
            by_store_summary = {}
            for s_id, s_data in metrics["by_store"].items():
                by_store_summary[s_id] = {
                    "revenue": s_data["revenue"],
                    "orders": len(s_data["orders_set"]),
                    "items_sold": s_data["items_sold"]
                }
                
            # Подготавливаем данные по каналам
            by_channel_summary = {}
            for c_id, c_data in metrics["by_channel"].items():
                by_channel_summary[c_id] = {
                    "revenue": c_data["revenue"],
                    "orders": len(c_data["orders_set"])
                }
            
            # Проверяем, существует ли уже метрика за этот день
            day_start = datetime.combine(day_key, datetime.min.time())
            result = await self.db.execute(
                select(SalesMetric)
                .where(
                    and_(
                        func.date(SalesMetric.date) == day_key,
                        SalesMetric.channel == "offline"
                    )
                )
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                # Обновляем существующую
                existing.revenue = metrics["revenue"]
                existing.order_count = order_count
                existing.items_sold = int(metrics["items_sold"])
                existing.average_order_value = avg_order_value
                existing.meta_data = {
                    "by_store": by_store_summary,
                    "by_channel": by_channel_summary
                }
            else:
                # Создаем новую
                new_metric = SalesMetric(
                    date=day_start,
                    revenue=metrics["revenue"],
                    order_count=order_count,
                    items_sold=int(metrics["items_sold"]),
                    average_order_value=avg_order_value,
                    channel="offline",
                    meta_data={
                        "by_store": by_store_summary,
                        "by_channel": by_channel_summary
                    }
                )
                self.db.add(new_metric)
        
        await self.db.commit()
        logger.info(f"Агрегированы метрики за {len(daily_metrics)} дней")
    
    async def sync_today_online(self) -> Dict[str, Any]:
        """Онлайн синхронизация продаж за сегодня"""
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = datetime.now()
        
        logger.info("Онлайн синхронизация продаж за сегодня")
        
        # Получаем данные из 1С
        sales_data = await self.sales_service.fetch_sales_from_api(today, end_date)
        orders = sales_data.get("orders", [])
        
        # Возвращаем данные без сохранения в БД (для онлайн отображения)
        return {
            "period": {"start": today.isoformat(), "end": end_date.isoformat()},
            "total_records": len(orders),
            "orders": orders,
            "metrics": self.sales_service.calculate_metrics(sales_data)
        }
    
    async def get_last_sync_date(self) -> Optional[datetime]:
        """Получение даты последней синхронизации"""
        result = await self.db.execute(
            select(func.max(SalesRecord.synced_at))
        )
        max_date = result.scalar_one()
        return max_date
    
    async def sync_incremental(self, days_back: int = 1) -> Dict[str, Any]:
        """
        Инкрементальная синхронизация (только новые данные)
        
        Args:
            days_back: Сколько дней назад начать проверку
        """
        last_sync = await self.get_last_sync_date()
        
        if last_sync:
            # Синхронизируем с последней даты синхронизации
            start_date = last_sync.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            # Если нет данных, синхронизируем за последние N дней
            start_date = datetime.now() - timedelta(days=days_back)
            start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        
        end_date = datetime.now()
        
        logger.info(f"Инкрементальная синхронизация с {start_date.date()}")
        
        return await self.sync_period(start_date, end_date, incremental=True)
    
    async def sync_full_period(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Полная синхронизация за период (перезаписывает существующие данные)"""
        logger.info(f"Полная синхронизация за период {start_date.date()} - {end_date.date()}")
        
        return await self.sync_period(start_date, end_date, incremental=False)
