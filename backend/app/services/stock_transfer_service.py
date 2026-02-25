"""
Сервис для анализа и рекомендаций по перемещению товаров между складом и магазинами
Включает AI-анализ паттернов продаж и оптимизацию распределения запасов
"""
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta, date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, case
from collections import defaultdict

from app.models.sales_record import SalesRecord
from app.models.product_stock import ProductStock
from app.models.product import Product
from app.models.store import Store
from app.models.inventory_analytics import InventoryAnalytics

logger = logging.getLogger(__name__)


class StockTransferService:
    """Сервис для управления перемещениями товаров между складом и магазинами"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def calculate_transfer_recommendations(
        self,
        analysis_period_days: int = 90,
        min_daily_sales: float = 0.01,
        safety_stock_days: int = 14
    ) -> List[Dict[str, Any]]:
        """
        Рассчитывает рекомендации по перемещению товаров со склада в магазины
        
        Args:
            analysis_period_days: Период анализа продаж
            min_daily_sales: Минимальные продажи для включения товара
            safety_stock_days: Дней запаса для поддержания
            
        Returns:
            Список рекомендаций по перемещению
        """
        logger.info("Начало расчета рекомендаций по перемещению товаров")
        
        # 1. Получаем остатки на складе (warehouse)
        warehouse_stocks = await self._get_warehouse_stocks()
        
        # 2. Получаем остатки в магазинах
        store_stocks = await self._get_store_stocks()
        
        # 3. Анализируем продажи по магазинам за период
        store_sales = await self._analyze_store_sales(analysis_period_days)
        
        # 4. Анализируем "горячие" товары для каждого магазина (AI-анализ)
        hot_products_by_store = await self._analyze_hot_products_by_store(analysis_period_days)
        
        # 5. Рассчитываем рекомендации
        recommendations = []
        
        for product_article, warehouse_qty in warehouse_stocks.items():
            if warehouse_qty <= 0:
                continue
            
            # Для каждого магазина анализируем потребность
            for store_info in await self._get_active_stores():
                store_id = store_info['id']
                store_name = store_info['name']
                
                # Пропускаем склад
                if 'склад' in store_name.lower() or 'warehouse' in store_name.lower():
                    continue
                
                # Текущий остаток в магазине
                current_stock = store_stocks.get(product_article, {}).get(store_id, 0)
                
                # Средние продажи в день в этом магазине
                avg_daily_sales = store_sales.get(product_article, {}).get(store_id, {}).get('avg_daily_sales', 0)
                
                if avg_daily_sales < min_daily_sales:
                    continue
                
                # Рассчитываем потребность
                days_of_stock = current_stock / avg_daily_sales if avg_daily_sales > 0 else 999
                
                # Если остаток меньше safety_stock_days, рекомендуем перемещение
                if days_of_stock < safety_stock_days:
                    import math
                    needed_qty_raw = (avg_daily_sales * safety_stock_days) - current_stock
                    needed_qty = max(1, math.ceil(needed_qty_raw)) if needed_qty_raw > 0 else 0
                    
                    # Ограничиваем количество доступным на складе
                    transfer_qty = min(needed_qty, int(warehouse_qty))
                    
                    if transfer_qty > 0:
                        # Определяем приоритет (срочность)
                        if days_of_stock < 7:
                            priority = "critical"
                            priority_score = 100
                        elif days_of_stock < 10:
                            priority = "high"
                            priority_score = 75
                        else:
                            priority = "medium"
                            priority_score = 50
                        
                        # Проверяем, является ли товар "горячим" для этого магазина
                        is_hot = product_article in hot_products_by_store.get(store_id, [])
                        if is_hot:
                            priority_score += 20  # Бонус за "горячий" товар
                        
                        # Получаем информацию о товаре
                        product_info = await self._get_product_info(product_article)
                        
                        recommendations.append({
                            'product_article': product_article,
                            'product_name': product_info.get('name'),
                            'category': product_info.get('category'),
                            'brand': product_info.get('brand'),
                            'from_store': 'Основной склад',
                            'to_store_id': store_id,
                            'to_store_name': store_name,
                            'current_stock': current_stock,
                            'warehouse_stock': warehouse_qty,
                            'recommended_transfer': transfer_qty,
                            'days_until_stockout': days_of_stock,
                            'avg_daily_sales': avg_daily_sales,
                            'priority': priority,
                            'priority_score': priority_score,
                            'is_hot_product': is_hot,
                            'reason': self._generate_reason(days_of_stock, is_hot, avg_daily_sales)
                        })
        
        # Сортируем по приоритету
        recommendations.sort(key=lambda x: x['priority_score'], reverse=True)
        
        logger.info(f"Рассчитано {len(recommendations)} рекомендаций по перемещению")
        return recommendations
    
    async def _get_warehouse_stocks(self) -> Dict[str, float]:
        """Получает остатки на основном складе"""
        query = select(
            Product.article,
            ProductStock.available_quantity
        ).join(
            Product, ProductStock.product_id == Product.id
        ).join(
            Store, ProductStock.store_id == Store.external_id
        ).where(
            and_(
                Product.article.isnot(None),
                ProductStock.available_quantity > 0,
                or_(
                    Store.name.ilike('%склад%'),
                    Store.name.ilike('%warehouse%'),
                    Store.name == 'Основной склад'
                )
            )
        )
        
        result = await self.db.execute(query)
        return {row[0]: float(row[1] or 0) for row in result.all() if row[0]}
    
    async def _get_store_stocks(self) -> Dict[str, Dict[str, float]]:
        """Получает остатки по магазинам"""
        query = select(
            Product.article,
            ProductStock.store_id,
            ProductStock.available_quantity
        ).join(
            Product, ProductStock.product_id == Product.id
        ).where(
            and_(
                Product.article.isnot(None),
                ProductStock.available_quantity > 0
            )
        )
        
        result = await self.db.execute(query)
        
        stocks = defaultdict(dict)
        for row in result.all():
            article = row[0]
            store_id = str(row[1])
            qty = float(row[2] or 0)
            stocks[article][store_id] = qty
        
        return dict(stocks)
    
    async def _analyze_store_sales(self, days: int) -> Dict[str, Dict[str, Dict[str, float]]]:
        """
        Анализирует продажи по товарам и магазинам
        Возвращает: {article: {store_id: {avg_daily_sales, total_sales, ...}}}
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        query = select(
            SalesRecord.product_article,
            SalesRecord.store_id,
            func.sum(SalesRecord.quantity).label('total_quantity'),
            func.count(func.distinct(SalesRecord.document_id)).label('orders_count')
        ).where(
            and_(
                SalesRecord.sale_date >= start_date,
                SalesRecord.sale_date <= end_date,
                SalesRecord.product_article.isnot(None),
                SalesRecord.store_id.isnot(None),
                SalesRecord.quantity > 0
            )
        ).group_by(
            SalesRecord.product_article,
            SalesRecord.store_id
        )
        
        result = await self.db.execute(query)
        
        sales = defaultdict(lambda: defaultdict(dict))
        for row in result.all():
            article = row[0]
            store_id = str(row[1])
            total_qty = float(row[2] or 0)
            orders = int(row[3] or 0)
            
            sales[article][store_id] = {
                'total_sales': total_qty,
                'avg_daily_sales': total_qty / days if days > 0 else 0,
                'orders_count': orders
            }
        
        return dict(sales)
    
    async def _analyze_hot_products_by_store(
        self,
        days: int,
        top_n: int = 20
    ) -> Dict[str, List[str]]:
        """
        AI-анализ: определяет "горячие" товары для каждого магазина
        Горячий товар = высокие продажи + высокая частота покупок + рост тренда
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Анализируем продажи за последний период vs предыдущий период
        current_period_start = end_date - timedelta(days=days // 2)
        
        query = select(
            SalesRecord.product_article,
            SalesRecord.store_id,
            func.sum(
                case(
                    (SalesRecord.sale_date >= current_period_start, SalesRecord.quantity),
                    else_=0
                )
            ).label('recent_sales'),
            func.sum(
                case(
                    (SalesRecord.sale_date < current_period_start, SalesRecord.quantity),
                    else_=0
                )
            ).label('old_sales'),
            func.count(func.distinct(SalesRecord.document_id)).label('frequency')
        ).where(
            and_(
                SalesRecord.sale_date >= start_date,
                SalesRecord.sale_date <= end_date,
                SalesRecord.product_article.isnot(None),
                SalesRecord.store_id.isnot(None),
                SalesRecord.quantity > 0
            )
        ).group_by(
            SalesRecord.product_article,
            SalesRecord.store_id
        ).having(
            func.sum(SalesRecord.quantity) > 0
        )
        
        result = await self.db.execute(query)
        
        # Рассчитываем "горячесть" товара для каждого магазина
        store_products = defaultdict(list)
        
        for row in result.all():
            article = row[0]
            store_id = str(row[1])
            recent = float(row[2] or 0)
            old = float(row[3] or 0)
            frequency = int(row[4] or 0)
            
            # Рассчитываем score
            # 1. Тренд роста (recent vs old)
            trend_score = (recent - old) / (old + 1)  # +1 для избежания деления на 0
            
            # 2. Частота покупок
            frequency_score = frequency / (days / 2) if days > 0 else 0
            
            # 3. Объем продаж
            volume_score = recent / (days / 2) if days > 0 else 0
            
            # Общий score
            hot_score = (trend_score * 0.4) + (frequency_score * 0.3) + (volume_score * 0.3)
            
            store_products[store_id].append((article, hot_score))
        
        # Отбираем топ-N для каждого магазина
        hot_products = {}
        for store_id, products in store_products.items():
            # Сортируем по score и берем топ-N
            sorted_products = sorted(products, key=lambda x: x[1], reverse=True)
            hot_products[store_id] = [article for article, _ in sorted_products[:top_n]]
        
        return hot_products
    
    async def _get_active_stores(self) -> List[Dict[str, str]]:
        """Получает список активных магазинов"""
        query = select(
            Store.external_id,
            Store.name
        ).where(
            and_(
                Store.is_active == True,
                Store.external_id.isnot(None)
            )
        )
        
        result = await self.db.execute(query)
        return [{'id': str(row[0]), 'name': row[1]} for row in result.all() if row[0]]
    
    async def _get_product_info(self, article: str) -> Dict[str, Any]:
        """Получает информацию о товаре"""
        query = select(
            Product.name,
            Product.category,
            Product.brand
        ).where(
            Product.article == article
        )
        
        result = await self.db.execute(query)
        row = result.first()
        
        if row:
            return {
                'name': row[0],
                'category': row[1],
                'brand': row[2]
            }
        return {'name': None, 'category': None, 'brand': None}
    
    def _generate_reason(
        self,
        days_of_stock: float,
        is_hot: bool,
        avg_daily_sales: float
    ) -> str:
        """Генерирует описание причины рекомендации"""
        reasons = []
        
        if days_of_stock < 7:
            reasons.append(f"Критически низкий остаток ({days_of_stock:.1f} дней)")
        elif days_of_stock < 14:
            reasons.append(f"Низкий остаток ({days_of_stock:.1f} дней)")
        
        if is_hot:
            reasons.append("Популярный товар в этой точке")
        
        if avg_daily_sales > 0.1:
            reasons.append(f"Высокий спрос ({avg_daily_sales:.2f} шт/день)")
        
        return "; ".join(reasons) if reasons else "Требуется пополнение"
    
    async def get_store_performance_analysis(
        self,
        analysis_period_days: int = 90
    ) -> Dict[str, Any]:
        """
        Анализ эффективности продаж по магазинам
        Для AI-анализа паттернов
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=analysis_period_days)
        
        # Продажи по магазинам и категориям
        query = select(
            SalesRecord.store_id,
            SalesRecord.product_category,
            func.sum(SalesRecord.revenue).label('revenue'),
            func.sum(SalesRecord.quantity).label('quantity'),
            func.count(func.distinct(SalesRecord.product_article)).label('unique_products')
        ).where(
            and_(
                SalesRecord.sale_date >= start_date,
                SalesRecord.sale_date <= end_date,
                SalesRecord.store_id.isnot(None),
                SalesRecord.product_category.isnot(None)
            )
        ).group_by(
            SalesRecord.store_id,
            SalesRecord.product_category
        )
        
        result = await self.db.execute(query)
        
        # Получаем названия магазинов
        stores_query = select(Store.id, Store.name)
        stores_result = await self.db.execute(stores_query)
        store_names = {str(row[0]): row[1] for row in stores_result.all()}
        
        # Группируем данные
        analysis = defaultdict(lambda: defaultdict(dict))
        
        for row in result.all():
            store_id = str(row[0])
            category = row[1]
            revenue = float(row[2] or 0)
            quantity = float(row[3] or 0)
            unique = int(row[4] or 0)
            
            store_name = store_names.get(store_id, f"Store {store_id}")
            
            analysis[store_name][category] = {
                'revenue': revenue,
                'quantity': quantity,
                'unique_products': unique,
                'avg_price': revenue / quantity if quantity > 0 else 0
            }
        
        return dict(analysis)
