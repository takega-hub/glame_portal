"""
Сервис для расчёта оборачиваемости товаров
Оборачиваемость = Объём продаж / Средний остаток
Оборачиваемость в днях = Средний остаток × Период (дней) / Объём продаж
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta, date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc, case
from sqlalchemy.orm import aliased

from app.models.sales_record import SalesRecord
from app.models.product_stock import ProductStock
from app.models.product import Product

logger = logging.getLogger(__name__)


class ProductTurnoverService:
    """Сервис для расчёта оборачиваемости товаров"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def calculate_turnover(
        self,
        start_date: datetime,
        end_date: datetime,
        product_id_1c: Optional[str] = None,
        product_article: Optional[str] = None,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        product_type: Optional[str] = None,
        store_id: Optional[str] = None,
        channel: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Рассчитывает оборачиваемость товаров за период
        
        Args:
            start_date: Начальная дата
            end_date: Конечная дата
            product_id_1c: Фильтр по ID товара из 1С
            product_article: Фильтр по артикулу
            category: Фильтр по категории
            brand: Фильтр по бренду
            product_type: Фильтр по типу
            store_id: Фильтр по магазину
            channel: Фильтр по каналу
        
        Returns:
            Список товаров с метриками оборачиваемости
        """
        # Рассчитываем период в днях
        period_days = (end_date - start_date).days + 1
        
        # Получаем объём продаж по товарам
        # Используем LEFT JOIN с Product для получения данных о товаре, если они отсутствуют в SalesRecord
        sales_query = select(
            SalesRecord.product_id.label('product_id_1c'),
            func.coalesce(SalesRecord.product_name, Product.name).label('product_name'),
            func.coalesce(SalesRecord.product_article, Product.article).label('product_article'),
            func.coalesce(SalesRecord.product_category, Product.category).label('product_category'),
            func.coalesce(SalesRecord.product_brand, Product.brand).label('product_brand'),
            SalesRecord.product_type.label('product_type'),  # product_type только из SalesRecord
            SalesRecord.store_id,
            SalesRecord.channel,
            func.sum(SalesRecord.quantity).label('total_sold'),
            func.sum(SalesRecord.revenue).label('total_revenue'),
            func.count(func.distinct(SalesRecord.external_id)).label('orders_count')
        ).outerjoin(
            Product,
            or_(
                SalesRecord.product_id == Product.external_id,
                SalesRecord.product_article == Product.article
            )
        ).where(
            and_(
                SalesRecord.sale_date >= start_date,
                SalesRecord.sale_date <= end_date
            )
        )
        
        # Применяем фильтры
        if product_id_1c:
            sales_query = sales_query.where(SalesRecord.product_id == product_id_1c)
        if product_article:
            sales_query = sales_query.where(SalesRecord.product_article == product_article)
        if category:
            sales_query = sales_query.where(SalesRecord.product_category == category)
        if brand:
            sales_query = sales_query.where(SalesRecord.product_brand == brand)
        if product_type:
            sales_query = sales_query.where(SalesRecord.product_type == product_type)
        if store_id:
            sales_query = sales_query.where(SalesRecord.store_id == store_id)
        if channel:
            sales_query = sales_query.where(SalesRecord.channel == channel)
        
        # Группируем по всем полям, включая поля из Product
        sales_query = sales_query.group_by(
            SalesRecord.product_id,
            func.coalesce(SalesRecord.product_name, Product.name),
            func.coalesce(SalesRecord.product_article, Product.article),
            func.coalesce(SalesRecord.product_category, Product.category),
            func.coalesce(SalesRecord.product_brand, Product.brand),
            SalesRecord.product_type,
            SalesRecord.store_id,
            SalesRecord.channel
        )
        
        sales_result = await self.db.execute(sales_query)
        sales_rows = sales_result.all()
        
        # Получаем текущие остатки из ProductStock
        # Для упрощения используем текущие остатки как средние
        # В будущем можно добавить историю остатков для более точного расчёта
        stock_query = select(
            ProductStock.product_id,
            ProductStock.store_id,
            func.sum(ProductStock.available_quantity).label('current_stock')
        ).group_by(
            ProductStock.product_id,
            ProductStock.store_id
        )
        
        stock_result = await self.db.execute(stock_query)
        stock_rows = stock_result.all()
        
        # Создаём словарь остатков: (product_id, store_id) -> stock
        stock_dict = {}
        for row in stock_rows:
            # Нужно сопоставить product_id из ProductStock (UUID) с product_id из SalesRecord (String из 1С)
            # Для этого используем связь через Product.article
            stock_dict[(str(row[0]), row[1])] = float(row[2]) if row[2] else 0.0
        
        # Также создаём словарь для сопоставления по артикулу
        # Получаем связь product_id (UUID) -> product_id_1c (String) через Product
        product_mapping_query = select(
            Product.id,
            Product.external_id.label('product_id_1c'),
            Product.article
        ).where(Product.external_id.isnot(None))
        
        product_mapping_result = await self.db.execute(product_mapping_query)
        product_mapping_rows = product_mapping_result.all()
        
        # Создаём маппинг: product_id_1c -> product_id (UUID)
        product_id_mapping = {}
        article_to_product_id_1c = {}
        for row in product_mapping_rows:
            if row[1]:  # product_id_1c
                product_id_mapping[row[1]] = str(row[0])
            if row[2]:  # article
                article_to_product_id_1c[row[2]] = row[1]
        
        # Рассчитываем оборачиваемость для каждого товара
        turnover_data = []
        for sales_row in sales_rows:
            product_id_1c = sales_row[0]
            store_id = sales_row[6]
            total_sold = float(sales_row[8]) if sales_row[8] else 0.0
            total_revenue = float(sales_row[9]) if sales_row[9] else 0.0
            orders_count = int(sales_row[10]) if sales_row[10] else 0
            
            # Пытаемся найти остаток
            # Сначала по product_id_1c -> product_id (UUID)
            product_uuid = product_id_mapping.get(product_id_1c)
            current_stock = 0.0
            
            if product_uuid and store_id:
                current_stock = stock_dict.get((product_uuid, store_id), 0.0)
            
            # Если не нашли по store_id, суммируем по всем магазинам
            if current_stock == 0.0 and product_uuid:
                for (pid, sid), stock in stock_dict.items():
                    if pid == product_uuid:
                        current_stock += stock
            
            # Рассчитываем метрики оборачиваемости
            avg_daily_sales = total_sold / period_days if period_days > 0 else 0.0
            turnover_rate = total_sold / current_stock if current_stock > 0 else None
            turnover_days = (current_stock / avg_daily_sales) if avg_daily_sales > 0 else None
            
            # Классификация оборачиваемости
            turnover_class = None
            if turnover_rate is not None:
                if turnover_rate >= 12:  # Оборачиваемость >= 12 раз в год (быстрая)
                    turnover_class = "fast"
                elif turnover_rate >= 6:  # Оборачиваемость >= 6 раз в год (средняя)
                    turnover_class = "medium"
                elif turnover_rate >= 1:  # Оборачиваемость >= 1 раз в год (медленная)
                    turnover_class = "slow"
                else:  # Оборачиваемость < 1 раз в год (очень медленная)
                    turnover_class = "very_slow"
            
            turnover_data.append({
                'product_id_1c': product_id_1c,
                'product_name': sales_row[1],
                'product_article': sales_row[2],
                'category': sales_row[3],
                'brand': sales_row[4],
                'product_type': sales_row[5],
                'store_id': store_id,
                'channel': sales_row[7],
                'total_sold': total_sold,
                'total_revenue': total_revenue,
                'orders_count': orders_count,
                'current_stock': current_stock,
                'avg_daily_sales': avg_daily_sales,
                'turnover_rate': turnover_rate,  # Коэффициент оборачиваемости (раз в период)
                'turnover_days': turnover_days,  # Оборачиваемость в днях
                'turnover_class': turnover_class,
                'period_days': period_days
            })
        
        return turnover_data
    
    async def get_turnover_by_category(
        self,
        start_date: datetime,
        end_date: datetime,
        store_id: Optional[str] = None,
        channel: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Получает оборачиваемость по категориям"""
        turnover_data = await self.calculate_turnover(
            start_date=start_date,
            end_date=end_date,
            store_id=store_id,
            channel=channel
        )
        
        # Группируем по категориям
        category_turnover = {}
        for item in turnover_data:
            category = item['category']
            if not category:
                continue
            
            if category not in category_turnover:
                category_turnover[category] = {
                    'category': category,
                    'total_sold': 0.0,
                    'total_revenue': 0.0,
                    'total_stock': 0.0,
                    'products_count': 0,
                    'avg_turnover_rate': None,
                    'avg_turnover_days': None
                }
            
            category_turnover[category]['total_sold'] += item['total_sold']
            category_turnover[category]['total_revenue'] += item['total_revenue']
            category_turnover[category]['total_stock'] += item['current_stock']
            category_turnover[category]['products_count'] += 1
        
        # Рассчитываем средние метрики
        result = []
        period_days = (end_date - start_date).days + 1
        for category, data in category_turnover.items():
            avg_daily_sales = data['total_sold'] / period_days if period_days > 0 else 0.0
            avg_turnover_rate = data['total_sold'] / data['total_stock'] if data['total_stock'] > 0 else None
            avg_turnover_days = (data['total_stock'] / avg_daily_sales) if avg_daily_sales > 0 else None
            
            result.append({
                'category': category,
                'total_sold': data['total_sold'],
                'total_revenue': data['total_revenue'],
                'total_stock': data['total_stock'],
                'products_count': data['products_count'],
                'avg_daily_sales': avg_daily_sales,
                'avg_turnover_rate': avg_turnover_rate,
                'avg_turnover_days': avg_turnover_days
            })
        
        # Сортируем по оборачиваемости
        result.sort(key=lambda x: x['avg_turnover_rate'] or 0, reverse=True)
        
        return result
    
    async def get_turnover_by_brand(
        self,
        start_date: datetime,
        end_date: datetime,
        store_id: Optional[str] = None,
        channel: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Получает оборачиваемость по брендам"""
        turnover_data = await self.calculate_turnover(
            start_date=start_date,
            end_date=end_date,
            store_id=store_id,
            channel=channel
        )
        
        # Группируем по брендам
        brand_turnover = {}
        for item in turnover_data:
            brand = item['brand']
            if not brand:
                continue
            
            if brand not in brand_turnover:
                brand_turnover[brand] = {
                    'brand': brand,
                    'total_sold': 0.0,
                    'total_revenue': 0.0,
                    'total_stock': 0.0,
                    'products_count': 0,
                    'avg_turnover_rate': None,
                    'avg_turnover_days': None
                }
            
            brand_turnover[brand]['total_sold'] += item['total_sold']
            brand_turnover[brand]['total_revenue'] += item['total_revenue']
            brand_turnover[brand]['total_stock'] += item['current_stock']
            brand_turnover[brand]['products_count'] += 1
        
        # Рассчитываем средние метрики
        result = []
        period_days = (end_date - start_date).days + 1
        for brand, data in brand_turnover.items():
            avg_daily_sales = data['total_sold'] / period_days if period_days > 0 else 0.0
            avg_turnover_rate = data['total_sold'] / data['total_stock'] if data['total_stock'] > 0 else None
            avg_turnover_days = (data['total_stock'] / avg_daily_sales) if avg_daily_sales > 0 else None
            
            result.append({
                'brand': brand,
                'total_sold': data['total_sold'],
                'total_revenue': data['total_revenue'],
                'total_stock': data['total_stock'],
                'products_count': data['products_count'],
                'avg_daily_sales': avg_daily_sales,
                'avg_turnover_rate': avg_turnover_rate,
                'avg_turnover_days': avg_turnover_days
            })
        
        # Сортируем по оборачиваемости
        result.sort(key=lambda x: x['avg_turnover_rate'] or 0, reverse=True)
        
        return result
    
    async def get_slow_movers(
        self,
        start_date: datetime,
        end_date: datetime,
        min_stock: float = 1.0,
        max_turnover_rate: float = 1.0,
        store_id: Optional[str] = None,
        channel: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Получает товары с низкой оборачиваемостью (медленные продажи)
        
        Args:
            start_date: Начальная дата
            end_date: Конечная дата
            min_stock: Минимальный остаток для включения в список
            max_turnover_rate: Максимальный коэффициент оборачиваемости (товары с меньшим коэффициентом)
            store_id: Фильтр по магазину
            channel: Фильтр по каналу
        
        Returns:
            Список товаров с низкой оборачиваемостью
        """
        turnover_data = await self.calculate_turnover(
            start_date=start_date,
            end_date=end_date,
            store_id=store_id,
            channel=channel
        )
        
        # Фильтруем товары с низкой оборачиваемостью
        slow_movers = []
        for item in turnover_data:
            if item['current_stock'] >= min_stock:
                if item['turnover_rate'] is None or item['turnover_rate'] <= max_turnover_rate:
                    slow_movers.append(item)
        
        # Сортируем по остатку (от большего к меньшему)
        slow_movers.sort(key=lambda x: x['current_stock'], reverse=True)
        
        return slow_movers
