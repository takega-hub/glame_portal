"""
Сервис для комплексного управления запасами
Расчёт скорости продаж, прогноз дефицита, ABC/XYZ анализ, оптимизация точки заказа
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta, date, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, case

from app.models.sales_record import SalesRecord
from app.models.product_stock import ProductStock
from app.models.product import Product
from app.models.inventory_analytics import InventoryAnalytics
from app.models.store import Store
from app.services.product_turnover_service import ProductTurnoverService
from app.services.product_analytics_service import ProductAnalyticsService

logger = logging.getLogger(__name__)


class InventoryManagementService:
    """Сервис для управления запасами"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.turnover_service = ProductTurnoverService(db)
        self.analytics_service = ProductAnalyticsService(db)
    
    async def calculate_inventory_analytics(
        self,
        analysis_date: Optional[date] = None,
        analysis_period_days: int = 90
    ) -> int:
        """
        Рассчитывает комплексную аналитику остатков для всех товаров
        
        Args:
            analysis_date: Дата анализа (по умолчанию сегодня)
            analysis_period_days: Период анализа продаж в днях
        
        Returns:
            Количество обработанных товаров
        """
        if not analysis_date:
            analysis_date = date.today()
        
        logger.info(f"Начало расчёта аналитики остатков на {analysis_date}")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=analysis_period_days)
        
        # Получаем данные об оборачиваемости
        turnover_data = await self.turnover_service.calculate_turnover(
            start_date=start_date,
            end_date=end_date
        )
        
        # Получаем данные о продажах
        sales_data = await self.analytics_service.get_top_products(
            start_date=start_date,
            end_date=end_date,
            limit=10000
        )
        
        # Получаем данные об остатках напрямую из product_stocks
        # Работаем ТОЛЬКО с вариантами товаров (не с родителями)
        # Варианты определяются по наличию parent_external_id в specifications или sync_metadata
        stock_query = select(
            Product.external_id.label('product_id_1c'),
            Product.id.label('product_uuid'),
            Product.name,
            Product.article,
            Product.category,
            Product.brand,
            Product.specifications,  # Характеристики варианта (цвет, размер и т.д.)
            ProductStock.store_id,
            ProductStock.available_quantity.label('current_stock')
        ).join(
            Product, ProductStock.product_id == Product.id
        ).where(
            Product.external_id.isnot(None),
            ProductStock.available_quantity > 0,  # Только товары с остатками > 0
            # Фильтруем только варианты: есть parent_external_id в specifications или sync_metadata
            # Вариант определяется по наличию parent_external_id в JSON полях
            or_(
                Product.specifications['parent_external_id'].isnot(None),
                Product.sync_metadata['parent_external_id'].isnot(None)
            )
        )
        
        stock_result = await self.db.execute(stock_query)
        stock_rows = stock_result.all()
        
        logger.info(f"Получено {len(stock_rows)} записей остатков из product_stocks")
        
        # Создаём словари для быстрого доступа
        # Индексируем по артикулу, так как продажи теперь идут по вариантам
        turnover_map = {}
        for item in turnover_data:
            product_article = item.get('product_article')
            if product_article:
                turnover_map[str(product_article)] = item
        
        sales_map = {}
        for item in sales_data:
            product_article = item.get('product_article')
            if product_article:
                sales_map[str(product_article)] = item
        
        logger.info(f"Создано {len(turnover_map)} записей оборачиваемости, {len(sales_map)} записей продаж")
        
        # Группируем остатки по товарам и магазинам
        stock_by_product_store = {}
        for row in stock_rows:
            try:
                product_id_1c = row[0]
                if not product_id_1c:
                    continue
                
                product_id_1c = str(product_id_1c)  # Преобразуем в строку
                specifications = row[6] if len(row) > 6 else None  # Характеристики варианта (7-й элемент, индекс 6)
                store_id = str(row[7]) if len(row) > 7 and row[7] else None  # store_id (8-й элемент, индекс 7)
                if not store_id:
                    continue
                
                stock = float(row[8] or 0.0) if len(row) > 8 else 0.0  # stock (9-й элемент, индекс 8)
                
                # Формируем уникальный ключ: external_id варианта (не родителя)
                variant_key = product_id_1c
                
                # Получаем базовый артикул (артикул родителя) для связи с продажами
                base_article = row[3]
                if base_article and '-' in base_article:
                    base_article = base_article.split('-')[0]
                
                if variant_key not in stock_by_product_store:
                    # Извлекаем характеристики варианта для отображения
                    variant_characteristics = {}
                    if specifications and isinstance(specifications, dict):
                        # Извлекаем цвет, размер и другие характеристики
                        for key in ['Цвет', 'Размер', 'Color', 'Size', 'Материал', 'Покрытие', 'Вставка']:
                            if key in specifications:
                                variant_characteristics[key] = specifications[key]
                    
                    stock_by_product_store[variant_key] = {
                        'product_uuid': row[1],
                        'product_name': row[2],
                        'product_article': row[3],
                        'base_article': base_article,  # Базовый артикул для поиска продаж
                        'category': row[4],
                        'brand': row[5] if isinstance(row[5], str) else None,
                        'characteristics': variant_characteristics,  # Характеристики варианта
                        'stores': {}
                    }
                
                stock_by_product_store[variant_key]['stores'][store_id] = stock
            except Exception as e:
                logger.warning(f"Ошибка обработки строки остатков: {e}, row: {row}")
                continue
        
        logger.info(f"Обработано {len(stock_by_product_store)} товаров с остатками")
        
        analytics_records = []
        
        for product_id_1c, product_info in stock_by_product_store.items():
            try:
                # Ищем продажи и оборачиваемость по артикулу варианта
                product_article = product_info.get('product_article')
                turnover_info = turnover_map.get(product_article, {})
                sales_info = sales_map.get(product_article, {})
                
                # Рассчитываем аналитику для каждого магазина
                for store_id, current_stock in product_info['stores'].items():
                    try:
                        analytics = await self._calculate_store_analytics(
                            product_id_1c=product_id_1c,
                            product_info=product_info,
                            store_id=store_id,
                            current_stock=current_stock,
                            turnover_info=turnover_info,
                            sales_info=sales_info,
                            analysis_date=analysis_date,
                            analysis_period_days=analysis_period_days
                        )
                        
                        if analytics:
                            analytics_records.append(analytics)
                    except Exception as e:
                        logger.warning(f"Ошибка расчёта аналитики для товара {product_id_1c}, магазин {store_id}: {e}")
                        continue
            except Exception as e:
                logger.warning(f"Ошибка обработки товара {product_id_1c}: {e}")
                continue
        
        # Удаляем старые записи для текущей даты перед сохранением новых
        from sqlalchemy import delete
        stmt = delete(InventoryAnalytics).where(
            InventoryAnalytics.analysis_date == analysis_date
        )
        await self.db.execute(stmt)
        await self.db.commit()
        logger.info(f"Удалены старые записи аналитики для даты {analysis_date}")
        
        # Применяем правильную ABC/XYZ классификацию ко всем товарам
        if analytics_records:
            analytics_records = await self._apply_abc_xyz_classification(analytics_records)
            await self._save_analytics(analytics_records)
        
        logger.info(f"Расчёт аналитики остатков завершён. Обработано записей: {len(analytics_records)}")
        return len(analytics_records)
    
    async def _calculate_store_analytics(
        self,
        product_id_1c: str,
        product_info: Dict[str, Any],
        store_id: str,
        current_stock: float,
        turnover_info: Dict[str, Any],
        sales_info: Dict[str, Any],
        analysis_date: date,
        analysis_period_days: int
    ) -> Optional[Dict[str, Any]]:
        """Рассчитывает аналитику остатков для товара в конкретном магазине"""
        
        # Рассчитываем средние продажи в день
        total_quantity = sales_info.get('total_quantity', 0.0) or 0.0
        avg_daily_sales = total_quantity / analysis_period_days if analysis_period_days > 0 else 0.0
        
        # Скорость продаж (sales velocity)
        sales_velocity = avg_daily_sales
        
        # Оборачиваемость
        turnover_rate = turnover_info.get('turnover_rate', 0.0) or 0.0
        turnover_days = turnover_info.get('turnover_days', 0.0) or 0.0
        
        # Рассчитываем средние остатки (упрощённо - используем текущий остаток)
        # В будущем можно использовать историю остатков
        avg_stock_30d = current_stock
        avg_stock_90d = current_stock
        
        # Риск дефицита (stockout risk)
        if avg_daily_sales > 0:
            days_until_stockout = current_stock / avg_daily_sales
            # Риск выше, если остаток меньше чем на 14 дней
            if days_until_stockout < 14:
                stockout_risk = 1.0 - (days_until_stockout / 14.0)
            else:
                stockout_risk = 0.0
        else:
            stockout_risk = 0.0
        
        # Риск излишков (overstock risk)
        if turnover_days > 0:
            # Риск выше, если оборачиваемость больше 180 дней
            if turnover_days > 180:
                overstock_risk = min(1.0, (turnover_days - 180) / 180.0)
            else:
                overstock_risk = 0.0
        else:
            overstock_risk = 0.0
        
        # ABC и XYZ классификация - временная заглушка
        # Правильная классификация требует анализа всех товаров сразу
        # Будет пересчитана в методе _apply_abc_xyz_classification()
        total_revenue = sales_info.get('total_revenue', 0.0) or 0.0
        abc_class = "C"  # По умолчанию
        xyz_class = "Z"  # По умолчанию
        
        # Для последующей классификации сохраняем метрики
        revenue_for_classification = total_revenue
        
        # Рассчитываем коэффициент вариации на основе оборачиваемости и продаж
        # CV (коэффициент вариации) = стандартное отклонение / среднее
        # Используем оборачиваемость как прокси для стабильности
        # Адаптированные пороги под реальные данные (max turnover_rate ~2.0)
        if avg_daily_sales > 0.01:  # Есть продажи
            # Высокая оборачиваемость = стабильный спрос (низкий CV)
            if turnover_rate >= 0.5:  # Товар продается регулярно (>0.5 раз в 90 дней)
                cv_for_classification = 0.4  # X класс - стабильный спрос
            elif turnover_rate >= 0.1:  # Средняя оборачиваемость
                cv_for_classification = 0.8  # Y класс - умеренный спрос
            else:  # Низкая оборачиваемость
                cv_for_classification = 1.5  # Z класс - нестабильный спрос
        else:  # Почти нет продаж
            cv_for_classification = 999.0  # Z класс - нет спроса
        
        # Уровень сервиса (service level)
        # Процент времени, когда товар был в наличии
        # Упрощённая версия - рассчитываем на основе текущего остатка
        if current_stock > 0:
            service_level = 1.0 if stockout_risk < 0.1 else 0.8
        else:
            service_level = 0.0
        
        # Снимки остатков по дням (упрощённо - только текущий)
        daily_snapshots = {
            str(analysis_date): current_stock
        }
        
        # Формируем название товара с характеристиками варианта
        product_name = product_info.get('product_name', '')
        characteristics = product_info.get('characteristics', {})
        if characteristics:
            # Добавляем характеристики к названию (например: "Браслет (Золотой, Размер 18)")
            char_parts = []
            for key, value in characteristics.items():
                if value:
                    char_parts.append(f"{value}")
            if char_parts:
                product_name = f"{product_name} ({', '.join(char_parts)})"
        
        return {
            'product_id_1c': product_id_1c,
            'product_id': product_info.get('product_uuid'),
            'product_name': product_name,  # Название с характеристиками
            'product_article': product_info.get('product_article'),
            'category': product_info.get('category'),
            'brand': product_info.get('brand'),
            # НЕ включаем 'characteristics' в результат, так как его нет в модели InventoryAnalytics
            'store_id': store_id,
            'analysis_date': analysis_date,
            'current_stock': current_stock,
            'avg_stock_30d': avg_stock_30d,
            'avg_stock_90d': avg_stock_90d,
            'sales_velocity': sales_velocity,
            'avg_daily_sales': avg_daily_sales,
            'turnover_days': turnover_days,
            'turnover_rate': turnover_rate,
            'stockout_risk': stockout_risk,
            'overstock_risk': overstock_risk,
            'abc_class': abc_class,
            'xyz_class': xyz_class,
            'service_level': service_level,
            'daily_snapshots': daily_snapshots,
            # Метрики для последующей классификации
            '_revenue_for_abc': revenue_for_classification,
            '_cv_for_xyz': cv_for_classification
        }
    
    async def _apply_abc_xyz_classification(self, analytics_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Применяет правильную ABC/XYZ классификацию на основе всех товаров
        ABC: на основе выручки (A=80%, B=15%, C=5%)
        XYZ: на основе коэффициента вариации продаж (X<0.5, Y<1.0, Z>=1.0)
        """
        if not analytics_records:
            return analytics_records
        
        # Собираем выручку по товарам (суммируем по всем магазинам)
        product_revenues = {}
        product_cvs = {}
        
        for record in analytics_records:
            product_id = record.get('product_id_1c')
            if not product_id:
                continue
            
            revenue = record.get('_revenue_for_abc', 0.0)
            cv = record.get('_cv_for_xyz', 999.0)
            
            if product_id not in product_revenues:
                product_revenues[product_id] = 0.0
                product_cvs[product_id] = cv
            
            product_revenues[product_id] += revenue
        
        # Сортируем товары по выручке
        sorted_products = sorted(product_revenues.items(), key=lambda x: x[1], reverse=True)
        total_revenue = sum(product_revenues.values())
        
        # Определяем ABC классы (80/15/5)
        abc_classification = {}
        cumulative_revenue = 0.0
        
        for product_id, revenue in sorted_products:
            cumulative_revenue += revenue
            percentage = (cumulative_revenue / total_revenue) if total_revenue > 0 else 0
            
            if percentage <= 0.80:
                abc_classification[product_id] = "A"
            elif percentage <= 0.95:
                abc_classification[product_id] = "B"
            else:
                abc_classification[product_id] = "C"
        
        # Определяем XYZ классы на основе CV
        xyz_classification = {}
        for product_id, cv in product_cvs.items():
            if cv < 0.5:
                xyz_classification[product_id] = "X"
            elif cv < 1.0:
                xyz_classification[product_id] = "Y"
            else:
                xyz_classification[product_id] = "Z"
        
        # Применяем классификацию к записям
        for record in analytics_records:
            product_id = record.get('product_id_1c')
            if product_id:
                record['abc_class'] = abc_classification.get(product_id, "C")
                record['xyz_class'] = xyz_classification.get(product_id, "Z")
            
            # Удаляем временные поля
            record.pop('_revenue_for_abc', None)
            record.pop('_cv_for_xyz', None)
        
        logger.info(f"ABC/XYZ классификация применена: A={sum(1 for v in abc_classification.values() if v=='A')}, "
                   f"B={sum(1 for v in abc_classification.values() if v=='B')}, "
                   f"C={sum(1 for v in abc_classification.values() if v=='C')}")
        
        return analytics_records
    
    async def _save_analytics(self, analytics_records: List[Dict[str, Any]]):
        """Сохраняет аналитику остатков в БД"""
        try:
            # Используем цикл для вставки/обновления, так как уникальный индекс может отсутствовать
            for analytics_data in analytics_records:
                product_id_1c = analytics_data.get('product_id_1c')
                store_id = analytics_data.get('store_id')
                analysis_date = analytics_data.get('analysis_date')
                
                if not product_id_1c or not store_id or not analysis_date:
                    continue
                
                # Проверяем существование записи
                existing_query = select(InventoryAnalytics).where(
                    and_(
                        InventoryAnalytics.product_id_1c == product_id_1c,
                        InventoryAnalytics.store_id == store_id,
                        InventoryAnalytics.analysis_date == analysis_date
                    )
                )
                existing_result = await self.db.execute(existing_query)
                existing = existing_result.scalar_one_or_none()
                
                if existing:
                    # Обновляем существующую запись
                    for key, value in analytics_data.items():
                        if key not in ['product_id_1c', 'store_id', 'analysis_date'] and hasattr(existing, key):
                            setattr(existing, key, value)
                    existing.updated_at = datetime.now(timezone.utc)
                else:
                    # Создаём новую запись
                    new_analytics = InventoryAnalytics(**analytics_data)
                    self.db.add(new_analytics)
            
            await self.db.commit()
            logger.info(f"Сохранено {len(analytics_records)} записей аналитики остатков в БД")
        except Exception as e:
            await self.db.rollback()
            error_msg = str(e)
            logger.error(f"Ошибка сохранения аналитики остатков: {error_msg}", exc_info=True)
            # Не пробрасываем исключение дальше, чтобы не прерывать синхронизацию остатков
            # Просто логируем ошибку
            raise RuntimeError(f"Ошибка сохранения аналитики остатков: {error_msg}") from e
    
    async def get_inventory_analysis(
        self,
        store_id: Optional[str] = None,
        category: Optional[str] = None,
        abc_class: Optional[str] = None,
        xyz_class: Optional[str] = None,
        critical_stockout: bool = False,
        critical_overstock: bool = False,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Получает комплексную аналитику остатков
        
        Args:
            store_id: Фильтр по магазину
            category: Фильтр по категории
            abc_class: Фильтр по ABC классу
            xyz_class: Фильтр по XYZ классу
            critical_stockout: Только товары с критическим дефицитом (stockout_risk > 0.7)
            critical_overstock: Только товары с критическими излишками (overstock_risk > 0.7)
            limit: Максимальное количество записей
        
        Returns:
            Список аналитики остатков
        """
        # Используем LEFT JOIN с Store для получения названий магазинов
        query = select(
            InventoryAnalytics,
            Store.name.label('store_name')
        ).outerjoin(
            Store,
            InventoryAnalytics.store_id == Store.external_id
        ).where(
            InventoryAnalytics.analysis_date == date.today()
        )
        
        if store_id:
            query = query.where(InventoryAnalytics.store_id == store_id)
        
        if category:
            query = query.where(InventoryAnalytics.category == category)
        
        if abc_class:
            query = query.where(InventoryAnalytics.abc_class == abc_class)
        
        if xyz_class:
            query = query.where(InventoryAnalytics.xyz_class == xyz_class)
        
        if critical_stockout:
            query = query.where(InventoryAnalytics.stockout_risk > 0.7)
        
        if critical_overstock:
            query = query.where(InventoryAnalytics.overstock_risk > 0.7)
        
        # Сортируем по приоритету: сначала критический дефицит, потом излишки
        if critical_stockout:
            query = query.order_by(desc(InventoryAnalytics.stockout_risk))
        elif critical_overstock:
            query = query.order_by(desc(InventoryAnalytics.overstock_risk))
        else:
            query = query.order_by(desc(InventoryAnalytics.stockout_risk))
        
        query = query.limit(limit)
        
        result = await self.db.execute(query)
        rows = result.all()
        
        return [
            {
                'product_id_1c': a.product_id_1c,
                'product_id': str(a.product_id) if a.product_id else None,
                'product_name': a.product_name,
                'product_article': a.product_article,
                'category': a.category,
                'brand': a.brand,
                'store_id': a.store_id,
                'store_name': store_name if store_name else a.store_id,  # Используем название или UUID
                'current_stock': a.current_stock,
                'avg_stock_30d': a.avg_stock_30d,
                'avg_stock_90d': a.avg_stock_90d,
                'sales_velocity': a.sales_velocity,
                'avg_daily_sales': a.avg_daily_sales,
                'turnover_days': a.turnover_days,
                'turnover_rate': a.turnover_rate,
                'stockout_risk': a.stockout_risk,
                'overstock_risk': a.overstock_risk,
                'abc_class': a.abc_class,
                'xyz_class': a.xyz_class,
                'service_level': a.service_level
            }
            for a, store_name in rows
        ]
    
    async def get_health_score(
        self,
        store_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Рассчитывает "здоровье" остатков - общую оценку состояния запасов
        
        Returns:
            Словарь с метриками здоровья остатков
        """
        query = select(
            func.count(InventoryAnalytics.id).label('total_products'),
            func.avg(InventoryAnalytics.stockout_risk).label('avg_stockout_risk'),
            func.avg(InventoryAnalytics.overstock_risk).label('avg_overstock_risk'),
            func.avg(InventoryAnalytics.service_level).label('avg_service_level'),
            func.count(case((InventoryAnalytics.stockout_risk > 0.7, 1))).label('critical_stockout'),
            func.count(case((InventoryAnalytics.overstock_risk > 0.7, 1))).label('critical_overstock')
        ).where(
            InventoryAnalytics.analysis_date == date.today()
        )
        
        if store_id:
            query = query.where(InventoryAnalytics.store_id == store_id)
        
        result = await self.db.execute(query)
        row = result.first()
        
        if not row or row[0] == 0:
            return {
                "health_score": 0.0,
                "status": "no_data",
                "metrics": {}
            }
        
        total_products = int(row[0] or 0)
        avg_stockout_risk = float(row[1] or 0.0)
        avg_overstock_risk = float(row[2] or 0.0)
        avg_service_level = float(row[3] or 0.0)
        critical_stockout = int(row[4] or 0)
        critical_overstock = int(row[5] or 0)
        
        # Рассчитываем общий health score (0-100)
        # Чем выше service_level и ниже риски - тем выше score
        health_score = (
            avg_service_level * 50 +
            (1.0 - avg_stockout_risk) * 30 +
            (1.0 - avg_overstock_risk) * 20
        ) * 100
        
        # Определяем статус
        if health_score >= 80:
            status = "excellent"
        elif health_score >= 60:
            status = "good"
        elif health_score >= 40:
            status = "fair"
        else:
            status = "poor"
        
        return {
            "health_score": round(health_score, 2),
            "status": status,
            "metrics": {
                "total_products": total_products,
                "avg_stockout_risk": round(avg_stockout_risk, 3),
                "avg_overstock_risk": round(avg_overstock_risk, 3),
                "avg_service_level": round(avg_service_level, 3),
                "critical_stockout_count": critical_stockout,
                "critical_overstock_count": critical_overstock
            }
        }
    
    async def get_abc_xyz_matrix(
        self,
        store_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Получает ABC/XYZ матрицу товаров
        
        Returns:
            Словарь с матрицей ABC/XYZ
        """
        query = select(
            InventoryAnalytics.abc_class,
            InventoryAnalytics.xyz_class,
            func.count(InventoryAnalytics.id).label('count'),
            func.sum(InventoryAnalytics.current_stock).label('total_stock'),
            func.avg(InventoryAnalytics.turnover_rate).label('avg_turnover')
        ).where(
            InventoryAnalytics.analysis_date == date.today()
        )
        
        if store_id:
            query = query.where(InventoryAnalytics.store_id == store_id)
        
        query = query.group_by(
            InventoryAnalytics.abc_class,
            InventoryAnalytics.xyz_class
        )
        
        result = await self.db.execute(query)
        rows = result.all()
        
        # Формируем матрицу
        matrix = {}
        for row in rows:
            abc = row[0] or "Unknown"
            xyz = row[1] or "Unknown"
            key = f"{abc}{xyz}"
            
            matrix[key] = {
                "abc_class": abc,
                "xyz_class": xyz,
                "count": int(row[2] or 0),
                "total_stock": float(row[3] or 0.0),
                "avg_turnover": float(row[4] or 0.0)
            }
        
        return {
            "status": "success",
            "matrix": matrix
        }
    
    async def get_stockout_forecast(
        self,
        days: int = 30,
        store_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Прогноз дефицита на N дней вперёд
        
        Args:
            days: Количество дней для прогноза
            store_id: Фильтр по магазину
        
        Returns:
            Список товаров с прогнозом дефицита
        """
        query = select(InventoryAnalytics).where(
            and_(
                InventoryAnalytics.analysis_date == date.today(),
                InventoryAnalytics.avg_daily_sales > 0
            )
        )
        
        if store_id:
            query = query.where(InventoryAnalytics.store_id == store_id)
        
        result = await self.db.execute(query)
        analytics = result.scalars().all()
        
        forecast = []
        for a in analytics:
            if a.avg_daily_sales and a.avg_daily_sales > 0:
                days_until_stockout = a.current_stock / a.avg_daily_sales
                
                if days_until_stockout <= days:
                    forecast.append({
                        'product_id_1c': a.product_id_1c,
                        'product_name': a.product_name,
                        'product_article': a.product_article,
                        'category': a.category,
                        'store_id': a.store_id,
                        'current_stock': a.current_stock,
                        'avg_daily_sales': a.avg_daily_sales,
                        'days_until_stockout': round(days_until_stockout, 1),
                        'stockout_risk': a.stockout_risk
                    })
        
        # Сортируем по дням до дефицита
        forecast.sort(key=lambda x: x['days_until_stockout'])
        
        return forecast
    
    async def get_overstock_report(
        self,
        store_id: Optional[str] = None,
        min_days: int = 180
    ) -> List[Dict[str, Any]]:
        """
        Отчёт по излишкам товаров
        
        Args:
            store_id: Фильтр по магазину
            min_days: Минимальная оборачиваемость в днях для включения
        
        Returns:
            Список товаров с излишками
        """
        query = select(InventoryAnalytics).where(
            and_(
                InventoryAnalytics.analysis_date == date.today(),
                InventoryAnalytics.turnover_days >= min_days,
                InventoryAnalytics.current_stock > 0
            )
        )
        
        if store_id:
            query = query.where(InventoryAnalytics.store_id == store_id)
        
        query = query.order_by(desc(InventoryAnalytics.turnover_days)).limit(100)
        
        result = await self.db.execute(query)
        analytics = result.scalars().all()
        
        return [
            {
                'product_id_1c': a.product_id_1c,
                'product_name': a.product_name,
                'product_article': a.product_article,
                'category': a.category,
                'store_id': a.store_id,
                'current_stock': a.current_stock,
                'turnover_days': a.turnover_days,
                'turnover_rate': a.turnover_rate,
                'overstock_risk': a.overstock_risk
            }
            for a in analytics
        ]
