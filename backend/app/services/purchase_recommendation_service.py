"""
Сервис для расчёта рекомендаций по закупкам товаров
Рассчитывает оптимальное количество товаров для заказа на основе оборачиваемости и остатков
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc
import json

from app.models.sales_record import SalesRecord
from app.models.product_stock import ProductStock
from app.models.product import Product
from app.models.purchase_recommendation import PurchaseRecommendation
from app.services.product_turnover_service import ProductTurnoverService
from app.services.product_analytics_service import ProductAnalyticsService

logger = logging.getLogger(__name__)


class PurchaseRecommendationService:
    """Сервис для расчёта рекомендаций по закупкам"""
    
    # Параметры для расчёта оптимального запаса
    DEFAULT_LEAD_TIME_DAYS = 14  # Срок поставки по умолчанию (дни)
    SAFETY_STOCK_MULTIPLIER = 1.5  # Коэффициент страхового запаса
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.turnover_service = ProductTurnoverService(db)
        self.analytics_service = ProductAnalyticsService(db)
    
    async def calculate_recommendations(
        self,
        analysis_period_days: int = 90,
        lead_time_days: int = DEFAULT_LEAD_TIME_DAYS,
        min_avg_daily_sales: float = 0.1
    ) -> int:
        """
        Рассчитывает рекомендации по закупкам для всех товаров
        
        Args:
            analysis_period_days: Период анализа продаж в днях
            lead_time_days: Срок поставки в днях
            min_avg_daily_sales: Минимальные средние продажи в день для включения
        
        Returns:
            Количество обработанных товаров
        """
        logger.info(f"Начало расчёта рекомендаций по закупкам (период: {analysis_period_days} дней)")
        
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
        
        # Получаем данные об остатках для вариантов товаров
        stock_query = select(
            Product.article,
            Product.name,
            Product.category,
            Product.brand,
            func.sum(ProductStock.available_quantity).label('total_stock')
        ).join(
            Product, ProductStock.product_id == Product.id
        ).where(
            Product.external_id.isnot(None),
            Product.article.isnot(None),
            # Только варианты (с parent_external_id)
            or_(
                Product.specifications['parent_external_id'].isnot(None),
                Product.sync_metadata['parent_external_id'].isnot(None)
            )
        ).group_by(
            Product.article,
            Product.name,
            Product.category,
            Product.brand
        )
        
        stock_result = await self.db.execute(stock_query)
        stock_data = {}
        for row in stock_result.all():
            if row[0]:  # article
                stock_data[row[0]] = {
                    'article': row[0],
                    'name': row[1],
                    'category': row[2],
                    'brand': row[3],
                    'total_stock': float(row[4] or 0.0)
                }
        
        # Создаём словари для быстрого доступа (по артикулу, а не по external_id)
        turnover_map = {item.get('product_article'): item for item in turnover_data if item.get('product_article')}
        sales_map = {item.get('product_article'): item for item in sales_data if item.get('product_article')}
        
        # Собираем все уникальные артикулы
        all_articles = set()
        all_articles.update(turnover_map.keys())
        all_articles.update(sales_map.keys())
        all_articles.update(stock_data.keys())
        
        recommendations = []
        
        for article in all_articles:
            turnover_info = turnover_map.get(article, {})
            sales_info = sales_map.get(article, {})
            stock_info = stock_data.get(article, {})
            current_stock = int(stock_info.get('total_stock', 0.0))
            
            # Рассчитываем рекомендацию
            recommendation = await self._calculate_recommendation(
                product_article=article,
                product_name=stock_info.get('name') or sales_info.get('product_name') or turnover_info.get('product_name'),
                product_category=stock_info.get('category') or sales_info.get('category'),
                product_brand=stock_info.get('brand') or sales_info.get('brand'),
                turnover_info=turnover_info,
                sales_info=sales_info,
                current_stock=current_stock,
                analysis_period_days=analysis_period_days,
                lead_time_days=lead_time_days,
                min_avg_daily_sales=min_avg_daily_sales
            )
            
            if recommendation:
                recommendations.append(recommendation)
        
        # Сохраняем рекомендации в БД
        if recommendations:
            await self._save_recommendations(recommendations)
        
        logger.info(f"Расчёт рекомендаций завершён. Обработано товаров: {len(recommendations)}")
        return len(recommendations)
    
    async def _calculate_recommendation(
        self,
        product_article: str,
        product_name: Optional[str],
        product_category: Optional[str],
        product_brand: Optional[str],
        turnover_info: Dict[str, Any],
        sales_info: Dict[str, Any],
        current_stock: int,
        analysis_period_days: int,
        lead_time_days: int,
        min_avg_daily_sales: float
    ) -> Optional[Dict[str, Any]]:
        """Рассчитывает рекомендацию по закупке для товара"""
        import math
        
        if not product_name:
            return None
        
        # Рассчитываем средние продажи в день
        total_quantity = sales_info.get('total_quantity', 0.0) or 0.0
        avg_daily_sales = total_quantity / analysis_period_days if analysis_period_days > 0 else 0.0
        
        # Пропускаем товары с очень низкими продажами
        if avg_daily_sales < min_avg_daily_sales:
            return None
        
        # Получаем метрики оборачиваемости
        turnover_rate = turnover_info.get('turnover_rate', 0.0) or 0.0
        turnover_days = turnover_info.get('turnover_days', 0.0) or 0.0
        
        # Рассчитываем дни остатка
        days_of_stock = current_stock / avg_daily_sales if avg_daily_sales > 0 else 999.0
        
        # Рассчитываем оптимальный остаток
        # Оптимальный запас = (Средние продажи в день × Срок поставки) + Страховой запас
        safety_stock = avg_daily_sales * self.SAFETY_STOCK_MULTIPLIER * (lead_time_days ** 0.5)
        
        # Используем math.ceil для округления вверх, чтобы гарантировать минимальный заказ
        # Для товаров с низкими продажами (< 1 шт/день) гарантируем минимум 1 шт
        optimal_stock_raw = (avg_daily_sales * lead_time_days) + safety_stock
        optimal_stock = max(1, math.ceil(optimal_stock_raw)) if optimal_stock_raw > 0 else 0
        
        # Рассчитываем точку заказа (также округляем вверх)
        reorder_point_raw = (avg_daily_sales * lead_time_days) + safety_stock
        reorder_point = max(1, math.ceil(reorder_point_raw)) if reorder_point_raw > 0 else 0
        
        # Рассчитываем количество для заказа
        if current_stock < reorder_point:
            reorder_quantity = max(1, optimal_stock - current_stock)  # Минимум 1 шт к заказу
        else:
            reorder_quantity = 0
        
        # Определяем уровень срочности
        if days_of_stock < lead_time_days:
            urgency_level = "critical"
        elif days_of_stock < lead_time_days * 1.5:
            urgency_level = "high"
        elif days_of_stock < lead_time_days * 2:
            urgency_level = "medium"
        else:
            urgency_level = "low"
        
        # Рекомендуемая дата заказа
        if reorder_quantity > 0:
            if urgency_level == "critical":
                recommended_date = datetime.now(timezone.utc)
            elif urgency_level == "high":
                recommended_date = datetime.now(timezone.utc) + timedelta(days=1)
            else:
                recommended_date = datetime.now(timezone.utc) + timedelta(days=3)
        else:
            recommended_date = None
        
        return {
            'product_article': product_article,
            'product_name': product_name,
            'category': product_category,
            'brand': product_brand,
            'current_stock': current_stock,
            'recommended_stock': optimal_stock,
            'reorder_quantity': reorder_quantity,  # В модели поле называется 'reorder_quantity'
            'reorder_point': reorder_point,
            'days_of_stock': days_of_stock,  # В модели поле называется 'days_of_stock'
            'avg_daily_sales': avg_daily_sales,
            'turnover_rate': turnover_rate,
            'turnover_days': turnover_days,
            'urgency_level': urgency_level,
            'recommended_date': recommended_date  # В модели поле называется 'recommended_date'
        }
    
    async def _calculate_store_distribution(
        self,
        product_id_1c: str,
        total_quantity: int
    ) -> Optional[Dict[str, Any]]:
        """Рассчитывает распределение заказа по магазинам на основе продаж"""
        try:
            # Получаем продажи по магазинам за последние 90 дней
            end_date = datetime.now()
            start_date = end_date - timedelta(days=90)
            
            sales_by_store_query = select(
                SalesRecord.store_id,
                func.sum(SalesRecord.quantity).label('total_sales')
            ).where(
                and_(
                    SalesRecord.product_id == product_id_1c,
                    SalesRecord.sale_date >= start_date,
                    SalesRecord.sale_date <= end_date
                )
            ).group_by(SalesRecord.store_id)
            
            result = await self.db.execute(sales_by_store_query)
            store_sales = {row[0]: float(row[1] or 0.0) for row in result.all() if row[0]}
            
            if not store_sales:
                return None
            
            # Рассчитываем долю каждого магазина
            total_sales = sum(store_sales.values())
            if total_sales == 0:
                return None
            
            distribution = {}
            for store_id, sales in store_sales.items():
                share = sales / total_sales
                quantity = int(total_quantity * share)
                if quantity > 0:
                    distribution[store_id] = {
                        'quantity': quantity,
                        'share': share,
                        'sales': sales
                    }
            
            return distribution
        except Exception as e:
            logger.warning(f"Ошибка расчёта распределения по магазинам для {product_id_1c}: {e}")
            return None
    
    async def _save_recommendations(self, recommendations: List[Dict[str, Any]]):
        """Сохраняет рекомендации в БД"""
        try:
            # Используем цикл для вставки/обновления
            for rec_data in recommendations:
                product_article = rec_data.get('product_article')
                if not product_article:
                    continue
                
                # Проверяем существование записи по артикулу
                existing_query = select(PurchaseRecommendation).where(
                    PurchaseRecommendation.product_article == product_article
                )
                existing_result = await self.db.execute(existing_query)
                existing = existing_result.scalar_one_or_none()
                
                if existing:
                    # Обновляем существующую запись
                    for key, value in rec_data.items():
                        if hasattr(existing, key):
                            setattr(existing, key, value)
                    existing.updated_at = datetime.now(timezone.utc)
                else:
                    # Создаём новую запись
                    new_rec = PurchaseRecommendation(**rec_data)
                    self.db.add(new_rec)
            
            await self.db.commit()
            logger.info(f"Сохранено {len(recommendations)} рекомендаций в БД")
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Ошибка сохранения рекомендаций: {e}", exc_info=True)
            raise
    
    async def get_recommendations(
        self,
        limit: int = 100,
        urgency_level: Optional[str] = None,
        category: Optional[str] = None,
        only_reorder: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Получает рекомендации по закупкам
        
        Args:
            limit: Максимальное количество рекомендаций
            urgency_level: Фильтр по уровню срочности (critical, high, medium, low)
            category: Фильтр по категории
            only_reorder: Только товары, требующие заказа
        
        Returns:
            Список рекомендаций
        """
        query = select(PurchaseRecommendation)
        
        if only_reorder:
            query = query.where(PurchaseRecommendation.reorder_quantity > 0)
        
        if urgency_level:
            query = query.where(PurchaseRecommendation.urgency_level == urgency_level)
        
        if category:
            query = query.where(PurchaseRecommendation.category == category)
        
        query = query.order_by(
            desc(PurchaseRecommendation.urgency_level == 'critical'),
            desc(PurchaseRecommendation.urgency_level == 'high'),
            desc(PurchaseRecommendation.days_of_stock)
        ).limit(limit)
        
        result = await self.db.execute(query)
        recommendations = result.scalars().all()
        
        return [
            {
                'product_id_1c': r.product_id_1c,
                'product_id': str(r.product_id) if r.product_id else None,
                'product_name': r.product_name,
                'product_article': r.product_article,
                'category': r.category,
                'brand': r.brand,
                'current_stock': r.current_stock,
                'recommended_stock': r.recommended_stock,
                'reorder_quantity': r.reorder_quantity,
                'reorder_point': r.reorder_point,
                'days_of_stock': r.days_of_stock,
                'avg_daily_sales': r.avg_daily_sales,
                'turnover_rate': r.turnover_rate,
                'turnover_days': r.turnover_days,
                'urgency_level': r.urgency_level,
                'store_distribution': json.loads(r.store_distribution) if r.store_distribution else None,
                'recommended_date': r.recommended_date.isoformat() if r.recommended_date else None
            }
            for r in recommendations
        ]
    
    async def get_reorder_alerts(
        self,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Получает товары для срочного заказа"""
        return await self.get_recommendations(
            limit=limit,
            urgency_level='critical',
            only_reorder=True
        )
    
    async def get_dead_stock(
        self,
        limit: int = 50,
        min_days: int = 180
    ) -> List[Dict[str, Any]]:
        """
        Получает неликвидные товары (с очень низкой оборачиваемостью)
        
        Args:
            limit: Максимальное количество товаров
            min_days: Минимальное количество дней оборачиваемости для включения
        """
        query = select(PurchaseRecommendation).where(
            and_(
                PurchaseRecommendation.turnover_days >= min_days,
                PurchaseRecommendation.current_stock > 0
            )
        ).order_by(
            desc(PurchaseRecommendation.turnover_days)
        ).limit(limit)
        
        result = await self.db.execute(query)
        dead_stock = result.scalars().all()
        
        return [
            {
                'product_id_1c': d.product_id_1c,
                'product_id': str(d.product_id) if d.product_id else None,
                'product_name': d.product_name,
                'product_article': d.product_article,
                'category': d.category,
                'brand': d.brand,
                'current_stock': d.current_stock,
                'turnover_days': d.turnover_days,
                'days_of_stock': d.days_of_stock
            }
            for d in dead_stock
        ]
