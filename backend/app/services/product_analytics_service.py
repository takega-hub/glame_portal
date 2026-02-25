"""
Сервис для агрегации данных о продажах товаров и расчёта аналитики
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta, date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc, case
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.sales_record import SalesRecord
from app.models.product_sales_analytics import ProductSalesAnalytics
from app.models.product import Product

logger = logging.getLogger(__name__)


class ProductAnalyticsService:
    """Сервис для аналитики продаж товаров"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def aggregate_sales_by_period(
        self,
        start_date: datetime,
        end_date: datetime,
        period_type: str = 'day',
        channel: Optional[str] = None,
        store_id: Optional[str] = None
    ) -> int:
        """
        Агрегирует данные о продажах в таблицу ProductSalesAnalytics
        
        Args:
            start_date: Начальная дата
            end_date: Конечная дата
            period_type: Тип периода ('day', 'week', 'month', 'quarter', 'year')
            channel: Фильтр по каналу (опционально)
            store_id: Фильтр по магазину (опционально)
        
        Returns:
            Количество созданных/обновлённых записей
        """
        logger.info(f"Агрегация продаж за период {start_date.date()} - {end_date.date()}, тип: {period_type}")
        
        # Формируем запрос для агрегации
        query = select(
            SalesRecord.product_id.label('product_id_1c'),  # product_id из 1С хранится в product_id
            SalesRecord.product_id.label('product_id'),  # UUID из каталога (если есть связь)
            SalesRecord.product_name,
            SalesRecord.product_article,
            SalesRecord.product_category.label('category'),
            SalesRecord.product_brand.label('brand'),
            SalesRecord.product_type,
            SalesRecord.channel,
            SalesRecord.store_id,
            func.sum(SalesRecord.revenue).label('total_revenue'),
            func.sum(SalesRecord.quantity).label('total_quantity'),
            func.count(SalesRecord.id).label('orders_count'),
            func.avg(
                case(
                    (SalesRecord.quantity > 0, SalesRecord.revenue / SalesRecord.quantity),
                    else_=None
                )
            ).label('avg_price'),
            func.sum(SalesRecord.revenue_without_discount).label('revenue_without_discount'),
            func.sum(SalesRecord.cost_price * SalesRecord.quantity).label('total_cost'),
            func.sum(SalesRecord.margin).label('total_margin'),
        ).where(
            and_(
                SalesRecord.sale_date >= start_date,
                SalesRecord.sale_date <= end_date
            )
        )
        
        # Применяем фильтры
        if channel:
            query = query.where(SalesRecord.channel == channel)
        if store_id:
            query = query.where(SalesRecord.store_id == store_id)
        
        # Группируем по товару и периоду
        if period_type == 'day':
            query = query.group_by(
                func.date(SalesRecord.sale_date),
                SalesRecord.product_id,  # product_id содержит ID из 1С
                SalesRecord.product_name,
                SalesRecord.product_article,
                SalesRecord.product_category,
                SalesRecord.product_brand,
                SalesRecord.product_type,
                SalesRecord.channel,
                SalesRecord.store_id
            )
        elif period_type == 'week':
            query = query.group_by(
                func.date_trunc('week', SalesRecord.sale_date),
                SalesRecord.product_id,
                SalesRecord.product_name,
                SalesRecord.product_article,
                SalesRecord.product_category,
                SalesRecord.product_brand,
                SalesRecord.product_type,
                SalesRecord.channel,
                SalesRecord.store_id
            )
        elif period_type == 'month':
            query = query.group_by(
                func.date_trunc('month', SalesRecord.sale_date),
                SalesRecord.product_id,
                SalesRecord.product_name,
                SalesRecord.product_article,
                SalesRecord.product_category,
                SalesRecord.product_brand,
                SalesRecord.product_type,
                SalesRecord.channel,
                SalesRecord.store_id
            )
        
        result = await self.db.execute(query)
        rows = result.all()
        
        logger.info(f"Получено {len(rows)} групп для агрегации")
        
        # Вставляем/обновляем записи в ProductSalesAnalytics
        records_to_upsert = []
        for row in rows:
            # Определяем period_date в зависимости от типа периода
            if period_type == 'day':
                period_date = row[0] if isinstance(row[0], date) else row[0].date()
            elif period_type in ['week', 'month']:
                period_date = row[0].date() if hasattr(row[0], 'date') else row[0]
            else:
                period_date = start_date.date()
            
            avg_price = row[12] if row[12] else 0.0
            total_cost = row[14] if row[14] else None
            total_margin = row[15] if row[15] else None
            margin_percent = None
            if total_revenue := row[9]:
                if total_cost:
                    margin_percent = ((total_revenue - total_cost) / total_revenue * 100) if total_revenue > 0 else None
                elif total_margin:
                    margin_percent = (total_margin / total_revenue * 100) if total_revenue > 0 else None
            
            revenue_without_discount = row[13] if row[13] else None
            discount_amount = None
            if revenue_without_discount and total_revenue:
                discount_amount = revenue_without_discount - total_revenue
            
            avg_quantity_per_order = None
            if row[11] and row[10]:  # orders_count and total_quantity
                avg_quantity_per_order = row[10] / row[11] if row[11] > 0 else None
            
            record = {
                'product_id_1c': row[0],  # product_id из 1С (хранится в product_id в SalesRecord)
                'product_id': None,  # UUID из каталога (если есть связь через product_id)
                'product_name': row[1],
                'product_article': row[2],
                'category': row[3],
                'brand': row[4],
                'product_type': row[5],
                'channel': row[6],
                'store_id': row[7],
                'period_date': period_date,
                'period_type': period_type,
                'total_revenue': float(row[8]) if row[8] else 0.0,
                'total_quantity': float(row[9]) if row[9] else 0.0,
                'orders_count': int(row[10]) if row[10] else 0,
                'avg_price': float(avg_price) if avg_price else None,
                'avg_quantity_per_order': float(avg_quantity_per_order) if avg_quantity_per_order else None,
                'revenue_without_discount': float(revenue_without_discount) if revenue_without_discount else None,
                'discount_amount': float(discount_amount) if discount_amount else None,
                'total_cost': float(total_cost) if total_cost else None,
                'total_margin': float(total_margin) if total_margin else None,
                'margin_percent': float(margin_percent) if margin_percent else None,
                'calculated_at': datetime.now()
            }
            
            records_to_upsert.append(record)
        
        # Используем upsert для обновления существующих записей
        if records_to_upsert:
            stmt = pg_insert(ProductSalesAnalytics).values(records_to_upsert)
            stmt = stmt.on_conflict_do_update(
                index_elements=['product_id_1c', 'period_date', 'period_type', 'channel', 'store_id'],
                set_={
                    'total_revenue': stmt.excluded.total_revenue,
                    'total_quantity': stmt.excluded.total_quantity,
                    'orders_count': stmt.excluded.orders_count,
                    'avg_price': stmt.excluded.avg_price,
                    'avg_quantity_per_order': stmt.excluded.avg_quantity_per_order,
                    'revenue_without_discount': stmt.excluded.revenue_without_discount,
                    'discount_amount': stmt.excluded.discount_amount,
                    'total_cost': stmt.excluded.total_cost,
                    'total_margin': stmt.excluded.total_margin,
                    'margin_percent': stmt.excluded.margin_percent,
                    'calculated_at': stmt.excluded.calculated_at,
                    'updated_at': datetime.now()
                }
            )
            
            await self.db.execute(stmt)
            await self.db.commit()
            
            logger.info(f"Агрегировано {len(records_to_upsert)} записей")
        
        return len(records_to_upsert)
    
    async def get_top_products(
        self,
        start_date: datetime,
        end_date: datetime,
        limit: int = 20,
        sort_by: str = 'revenue',  # 'revenue', 'quantity', 'orders'
        category: Optional[str] = None,
        brand: Optional[str] = None,
        product_type: Optional[str] = None,
        channel: Optional[str] = None,
        store_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Получает топ продаваемых товаров
        
        Использует SalesRecord напрямую для получения данных
        """
        # Используем SalesRecord для получения данных
        # Используем LEFT JOIN с Product для получения данных о товаре, если они отсутствуют в SalesRecord
        query = select(
            SalesRecord.product_id,
            func.coalesce(SalesRecord.product_name, Product.name).label('product_name'),
            func.coalesce(SalesRecord.product_article, Product.article).label('product_article'),
            func.coalesce(SalesRecord.product_category, Product.category).label('product_category'),
            func.coalesce(SalesRecord.product_brand, Product.brand).label('product_brand'),
            SalesRecord.product_type,  # product_type только из SalesRecord
            func.sum(SalesRecord.revenue).label('total_revenue'),
            func.sum(SalesRecord.quantity).label('total_quantity'),
            func.count(func.distinct(SalesRecord.document_id)).label('total_orders'),
            func.avg(
                case(
                    (SalesRecord.quantity > 0, SalesRecord.revenue / SalesRecord.quantity),
                    else_=None
                )
            ).label('avg_price'),
            func.avg(SalesRecord.margin).label('avg_margin')
        ).outerjoin(
            Product,
            or_(
                SalesRecord.product_id == Product.external_id,
                SalesRecord.product_article == Product.article
            )
        ).where(
            and_(
                SalesRecord.sale_date >= start_date,
                SalesRecord.sale_date <= end_date,
                # Исключаем упаковку и сопутку (товары с ценой за единицу меньше 3 рублей)
                # Проверяем, что quantity > 0 и цена за единицу >= 3.0
                SalesRecord.quantity > 0,
                SalesRecord.revenue / SalesRecord.quantity >= 3.0
            )
        )
        
        # Применяем фильтры
        if category:
            query = query.where(SalesRecord.product_category == category)
        if brand:
            query = query.where(SalesRecord.product_brand == brand)
        if product_type:
            query = query.where(SalesRecord.product_type == product_type)
        if channel:
            query = query.where(SalesRecord.channel == channel)
        if store_id:
            query = query.where(SalesRecord.store_id == store_id)
        
        # Группируем по товару, включая поля из Product
        query = query.group_by(
            SalesRecord.product_id,
            func.coalesce(SalesRecord.product_name, Product.name),
            func.coalesce(SalesRecord.product_article, Product.article),
            func.coalesce(SalesRecord.product_category, Product.category),
            func.coalesce(SalesRecord.product_brand, Product.brand),
            SalesRecord.product_type
        ).having(
            # Дополнительная фильтрация после группировки: исключаем товары, где средняя цена за единицу меньше 3 рублей
            func.avg(
                case(
                    (SalesRecord.quantity > 0, SalesRecord.revenue / SalesRecord.quantity),
                    else_=None
                )
            ) >= 3.0
        )
        
        # Сортируем
        if sort_by == 'revenue':
            query = query.order_by(desc('total_revenue'))
        elif sort_by == 'quantity':
            query = query.order_by(desc('total_quantity'))
        elif sort_by == 'orders':
            query = query.order_by(desc('total_orders'))
        else:
            query = query.order_by(desc('total_revenue'))
        
        query = query.limit(limit)
        
        result = await self.db.execute(query)
        rows = result.all()
        
        products = []
        for row in rows:
            avg_price = row[9] if row[9] else None
            avg_margin = row[10] if row[10] else None
            avg_margin_percent = None
            if avg_margin and avg_price:
                avg_margin_percent = (avg_margin / avg_price * 100) if avg_price > 0 else None
            
            products.append({
                'product_id_1c': str(row[0]) if row[0] else None,
                'product_id': str(row[0]) if row[0] else None,
                'product_name': row[1],
                'product_article': row[2],
                'category': row[3],
                'brand': row[4],
                'product_type': row[5],
                'total_revenue': float(row[6]) if row[6] else 0.0,
                'total_quantity': float(row[7]) if row[7] else 0.0,
                'total_orders': int(row[8]) if row[8] else 0,
                'avg_price': float(avg_price) if avg_price else None,
                'avg_margin_percent': float(avg_margin_percent) if avg_margin_percent else None
            })
        
        return products
    
    async def get_sales_by_category(
        self,
        start_date: datetime,
        end_date: datetime,
        channel: Optional[str] = None,
        store_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Получает продажи по категориям"""
        query = select(
            SalesRecord.product_category.label('category'),
            func.sum(SalesRecord.revenue).label('total_revenue'),
            func.sum(SalesRecord.quantity).label('total_quantity'),
            func.count(func.distinct(SalesRecord.document_id)).label('total_orders'),
            func.count(func.distinct(SalesRecord.product_id)).label('products_count')
        ).where(
            and_(
                SalesRecord.sale_date >= start_date,
                SalesRecord.sale_date <= end_date,
                SalesRecord.product_category.isnot(None)
            )
        )
        
        if channel:
            query = query.where(SalesRecord.channel == channel)
        if store_id:
            query = query.where(SalesRecord.store_id == store_id)
        
        query = query.group_by(SalesRecord.product_category).order_by(desc('total_revenue'))
        
        result = await self.db.execute(query)
        rows = result.all()
        
        return [
            {
                'category': row[0],
                'total_revenue': float(row[1]) if row[1] else 0.0,
                'total_quantity': float(row[2]) if row[2] else 0.0,
                'total_orders': int(row[3]) if row[3] else 0,
                'products_count': int(row[4]) if row[4] else 0
            }
            for row in rows
        ]
    
    async def get_sales_by_brand(
        self,
        start_date: datetime,
        end_date: datetime,
        channel: Optional[str] = None,
        store_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Получает продажи по брендам"""
        query = select(
            SalesRecord.product_brand.label('brand'),
            func.sum(SalesRecord.revenue).label('total_revenue'),
            func.sum(SalesRecord.quantity).label('total_quantity'),
            func.count(func.distinct(SalesRecord.document_id)).label('total_orders'),
            func.count(func.distinct(SalesRecord.product_id)).label('products_count')
        ).where(
            and_(
                SalesRecord.sale_date >= start_date,
                SalesRecord.sale_date <= end_date,
                SalesRecord.product_brand.isnot(None)
            )
        )
        
        if channel:
            query = query.where(SalesRecord.channel == channel)
        if store_id:
            query = query.where(SalesRecord.store_id == store_id)
        
        query = query.group_by(SalesRecord.product_brand).order_by(desc('total_revenue'))
        
        result = await self.db.execute(query)
        rows = result.all()
        
        return [
            {
                'brand': row[0],
                'total_revenue': float(row[1]) if row[1] else 0.0,
                'total_quantity': float(row[2]) if row[2] else 0.0,
                'total_orders': int(row[3]) if row[3] else 0,
                'products_count': int(row[4]) if row[4] else 0
            }
            for row in rows
        ]
    
    async def get_sales_by_type(
        self,
        start_date: datetime,
        end_date: datetime,
        channel: Optional[str] = None,
        store_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Получает продажи по типам изделий"""
        query = select(
            SalesRecord.product_type,
            func.sum(SalesRecord.revenue).label('total_revenue'),
            func.sum(SalesRecord.quantity).label('total_quantity'),
            func.count(func.distinct(SalesRecord.document_id)).label('total_orders'),
            func.count(func.distinct(SalesRecord.product_id)).label('products_count')
        ).where(
            and_(
                SalesRecord.sale_date >= start_date,
                SalesRecord.sale_date <= end_date,
                SalesRecord.product_type.isnot(None)
            )
        )
        
        if channel:
            query = query.where(SalesRecord.channel == channel)
        if store_id:
            query = query.where(SalesRecord.store_id == store_id)
        
        query = query.group_by(SalesRecord.product_type).order_by(desc('total_revenue'))
        
        result = await self.db.execute(query)
        rows = result.all()
        
        return [
            {
                'product_type': row[0],
                'total_revenue': float(row[1]) if row[1] else 0.0,
                'total_quantity': float(row[2]) if row[2] else 0.0,
                'total_orders': int(row[3]) if row[3] else 0,
                'products_count': int(row[4]) if row[4] else 0
            }
            for row in rows
        ]
