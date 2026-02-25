"""
Сервис для аналитики каналов продаж
Анализирует продажи по каналам: offline, online и другим
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, case, desc

from app.models.sales_record import SalesRecord

logger = logging.getLogger(__name__)


class ChannelAnalyticsService:
    """Сервис для аналитики каналов продаж"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_channel_comparison(
        self,
        start_date: datetime,
        end_date: datetime,
        store_id: Optional[str] = None,
        category: Optional[str] = None,
        brand: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Сравнение каналов продаж
        
        Args:
            start_date: Начальная дата
            end_date: Конечная дата
            store_id: Фильтр по магазину
            category: Фильтр по категории
            brand: Фильтр по бренду
        
        Returns:
            Список каналов с метриками
        """
        query = select(
            SalesRecord.channel,
            func.sum(SalesRecord.revenue).label('total_revenue'),
            func.sum(SalesRecord.quantity).label('total_quantity'),
            func.count(func.distinct(SalesRecord.external_id)).label('total_orders'),
            func.count(func.distinct(SalesRecord.customer_id)).label('unique_customers'),
            func.avg(
                case(
                    (SalesRecord.quantity > 0, SalesRecord.revenue / SalesRecord.quantity),
                    else_=None
                )
            ).label('avg_price'),
            func.sum(SalesRecord.revenue_without_discount).label('revenue_without_discount'),
            func.count(func.distinct(SalesRecord.product_id)).label('unique_products')
        ).where(
            and_(
                SalesRecord.sale_date >= start_date,
                SalesRecord.sale_date <= end_date,
                SalesRecord.channel.isnot(None)
            )
        )
        
        # Применяем фильтры
        if store_id:
            query = query.where(SalesRecord.store_id == store_id)
        if category:
            query = query.where(SalesRecord.product_category == category)
        if brand:
            query = query.where(SalesRecord.product_brand == brand)
        
        query = query.group_by(SalesRecord.channel).order_by(desc('total_revenue'))
        
        result = await self.db.execute(query)
        rows = result.all()
        
        # Рассчитываем общие метрики для сравнения
        total_revenue = sum(float(row[1]) if row[1] else 0.0 for row in rows)
        total_quantity = sum(float(row[2]) if row[2] else 0.0 for row in rows)
        total_orders = sum(int(row[3]) if row[3] else 0 for row in rows)
        
        channels = []
        for row in rows:
            channel_revenue = float(row[1]) if row[1] else 0.0
            channel_quantity = float(row[2]) if row[2] else 0.0
            channel_orders = int(row[3]) if row[3] else 0
            unique_customers = int(row[4]) if row[4] else 0
            avg_price = float(row[5]) if row[5] else None
            revenue_without_discount = float(row[6]) if row[6] else None
            unique_products = int(row[7]) if row[7] else 0
            
            # Рассчитываем доли
            revenue_share = (channel_revenue / total_revenue * 100) if total_revenue > 0 else 0.0
            quantity_share = (channel_quantity / total_quantity * 100) if total_quantity > 0 else 0.0
            orders_share = (channel_orders / total_orders * 100) if total_orders > 0 else 0.0
            
            # Средний чек
            avg_order_value = (channel_revenue / channel_orders) if channel_orders > 0 else None
            
            # Скидки
            discount_amount = None
            discount_percent = None
            if revenue_without_discount and channel_revenue:
                discount_amount = revenue_without_discount - channel_revenue
                discount_percent = (discount_amount / revenue_without_discount * 100) if revenue_without_discount > 0 else None
            
            channels.append({
                'channel': row[0],
                'total_revenue': channel_revenue,
                'total_quantity': channel_quantity,
                'total_orders': channel_orders,
                'unique_customers': unique_customers,
                'unique_products': unique_products,
                'avg_price': avg_price,
                'avg_order_value': avg_order_value,
                'revenue_share': revenue_share,
                'quantity_share': quantity_share,
                'orders_share': orders_share,
                'revenue_without_discount': revenue_without_discount,
                'discount_amount': discount_amount,
                'discount_percent': discount_percent
            })
        
        return channels
    
    async def get_channel_conversion(
        self,
        start_date: datetime,
        end_date: datetime,
        store_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Конверсия по каналам продаж
        
        Рассчитывает метрики конверсии для каждого канала:
        - Конверсия = (Количество заказов / Количество посетителей) * 100
        - Средний чек
        - Повторные покупки
        
        Args:
            start_date: Начальная дата
            end_date: Конечная дата
            store_id: Фильтр по магазину
        
        Returns:
            Словарь с метриками конверсии по каналам
        """
        # Получаем данные о продажах по каналам
        query = select(
            SalesRecord.channel,
            func.count(func.distinct(SalesRecord.external_id)).label('total_orders'),
            func.count(func.distinct(SalesRecord.customer_id)).label('unique_customers'),
            func.sum(SalesRecord.revenue).label('total_revenue'),
            func.sum(SalesRecord.quantity).label('total_quantity')
        ).where(
            and_(
                SalesRecord.sale_date >= start_date,
                SalesRecord.sale_date <= end_date,
                SalesRecord.channel.isnot(None)
            )
        )
        
        if store_id:
            query = query.where(SalesRecord.store_id == store_id)
        
        query = query.group_by(SalesRecord.channel)
        
        result = await self.db.execute(query)
        rows = result.all()
        
        # Получаем данные о повторных покупках
        repeat_purchase_query = select(
            SalesRecord.channel,
            SalesRecord.customer_id,
            func.count(func.distinct(SalesRecord.external_id)).label('orders_count')
        ).where(
            and_(
                SalesRecord.sale_date >= start_date,
                SalesRecord.sale_date <= end_date,
                SalesRecord.channel.isnot(None),
                SalesRecord.customer_id.isnot(None)
            )
        )
        
        if store_id:
            repeat_purchase_query = repeat_purchase_query.where(SalesRecord.store_id == store_id)
        
        repeat_purchase_query = repeat_purchase_query.group_by(
            SalesRecord.channel,
            SalesRecord.customer_id
        ).having(func.count(func.distinct(SalesRecord.external_id)) > 1)
        
        repeat_result = await self.db.execute(repeat_purchase_query)
        repeat_rows = repeat_result.all()
        
        # Подсчитываем повторных покупателей по каналам
        repeat_customers_by_channel = {}
        for row in repeat_rows:
            channel = row[0]
            if channel not in repeat_customers_by_channel:
                repeat_customers_by_channel[channel] = 0
            repeat_customers_by_channel[channel] += 1
        
        channels_data = []
        for row in rows:
            channel = row[0]
            total_orders = int(row[1]) if row[1] else 0
            unique_customers = int(row[2]) if row[2] else 0
            total_revenue = float(row[3]) if row[3] else 0.0
            total_quantity = float(row[4]) if row[4] else 0.0
            
            # Конверсия (для offline это может быть не применимо, но оставим для единообразия)
            # В реальности для offline нужны данные о посетителях магазинов
            conversion_rate = None  # Будет рассчитываться на основе данных о посетителях
            
            # Средний чек
            avg_order_value = (total_revenue / total_orders) if total_orders > 0 else None
            
            # Повторные покупки
            repeat_customers = repeat_customers_by_channel.get(channel, 0)
            repeat_purchase_rate = (repeat_customers / unique_customers * 100) if unique_customers > 0 else None
            
            # Среднее количество товаров в заказе
            avg_items_per_order = (total_quantity / total_orders) if total_orders > 0 else None
            
            channels_data.append({
                'channel': channel,
                'total_orders': total_orders,
                'unique_customers': unique_customers,
                'total_revenue': total_revenue,
                'total_quantity': total_quantity,
                'avg_order_value': avg_order_value,
                'avg_items_per_order': avg_items_per_order,
                'repeat_customers': repeat_customers,
                'repeat_purchase_rate': repeat_purchase_rate,
                'conversion_rate': conversion_rate  # Требует данных о посетителях
            })
        
        return {
            'channels': channels_data,
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            }
        }
    
    async def get_channel_trends(
        self,
        start_date: datetime,
        end_date: datetime,
        period_type: str = 'day',  # 'day', 'week', 'month'
        store_id: Optional[str] = None,
        category: Optional[str] = None,
        brand: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Тренды по каналам продаж
        
        Args:
            start_date: Начальная дата
            end_date: Конечная дата
            period_type: Тип периода ('day', 'week', 'month')
            store_id: Фильтр по магазину
            category: Фильтр по категории
            brand: Фильтр по бренду
        
        Returns:
            Словарь с трендами по каналам
        """
        # Определяем функцию для группировки по периоду
        if period_type == 'day':
            period_func = func.date(SalesRecord.sale_date)
        elif period_type == 'week':
            period_func = func.date_trunc('week', SalesRecord.sale_date)
        elif period_type == 'month':
            period_func = func.date_trunc('month', SalesRecord.sale_date)
        else:
            period_func = func.date(SalesRecord.sale_date)
        
        query = select(
            period_func.label('period'),
            SalesRecord.channel,
            func.sum(SalesRecord.revenue).label('total_revenue'),
            func.sum(SalesRecord.quantity).label('total_quantity'),
            func.count(func.distinct(SalesRecord.external_id)).label('total_orders'),
            func.count(func.distinct(SalesRecord.customer_id)).label('unique_customers')
        ).where(
            and_(
                SalesRecord.sale_date >= start_date,
                SalesRecord.sale_date <= end_date,
                SalesRecord.channel.isnot(None)
            )
        )
        
        # Применяем фильтры
        if store_id:
            query = query.where(SalesRecord.store_id == store_id)
        if category:
            query = query.where(SalesRecord.product_category == category)
        if brand:
            query = query.where(SalesRecord.product_brand == brand)
        
        query = query.group_by(
            period_func,
            SalesRecord.channel
        ).order_by(
            period_func,
            SalesRecord.channel
        )
        
        result = await self.db.execute(query)
        rows = result.all()
        
        # Группируем данные по периодам и каналам
        trends_by_period = {}
        channels = set()
        
        for row in rows:
            period = row[0]
            if isinstance(period, datetime):
                period_key = period.isoformat()
            else:
                period_key = str(period)
            
            channel = row[1]
            channels.add(channel)
            
            if period_key not in trends_by_period:
                trends_by_period[period_key] = {}
            
            trends_by_period[period_key][channel] = {
                'total_revenue': float(row[2]) if row[2] else 0.0,
                'total_quantity': float(row[3]) if row[3] else 0.0,
                'total_orders': int(row[4]) if row[4] else 0,
                'unique_customers': int(row[5]) if row[5] else 0
            }
        
        # Формируем список периодов с данными по всем каналам
        trends = []
        for period_key in sorted(trends_by_period.keys()):
            period_data = {
                'period': period_key,
                'channels': {}
            }
            
            for channel in channels:
                channel_data = trends_by_period[period_key].get(channel, {
                    'total_revenue': 0.0,
                    'total_quantity': 0.0,
                    'total_orders': 0,
                    'unique_customers': 0
                })
                period_data['channels'][channel] = channel_data
            
            trends.append(period_data)
        
        return {
            'trends': trends,
            'channels': list(channels),
            'period_type': period_type,
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            }
        }
    
    async def get_channel_performance(
        self,
        start_date: datetime,
        end_date: datetime,
        store_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Производительность каналов продаж
        
        Комплексная метрика производительности каналов
        
        Args:
            start_date: Начальная дата
            end_date: Конечная дата
            store_id: Фильтр по магазину
        
        Returns:
            Словарь с метриками производительности
        """
        # Получаем сравнение каналов
        comparison = await self.get_channel_comparison(
            start_date=start_date,
            end_date=end_date,
            store_id=store_id
        )
        
        # Получаем тренды
        trends = await self.get_channel_trends(
            start_date=start_date,
            end_date=end_date,
            period_type='week',
            store_id=store_id
        )
        
        # Рассчитываем рост/падение по каналам
        channel_growth = {}
        if len(trends['trends']) >= 2:
            first_period = trends['trends'][0]
            last_period = trends['trends'][-1]
            
            for channel in trends['channels']:
                first_revenue = first_period['channels'].get(channel, {}).get('total_revenue', 0.0)
                last_revenue = last_period['channels'].get(channel, {}).get('total_revenue', 0.0)
                
                if first_revenue > 0:
                    growth_percent = ((last_revenue - first_revenue) / first_revenue * 100)
                else:
                    growth_percent = None
                
                channel_growth[channel] = {
                    'growth_percent': growth_percent,
                    'first_period_revenue': first_revenue,
                    'last_period_revenue': last_revenue
                }
        
        return {
            'comparison': comparison,
            'trends': trends,
            'growth': channel_growth,
            'period': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            }
        }
