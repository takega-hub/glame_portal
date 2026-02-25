"""
Сервис для расчёта приоритета товаров для выкладки на сайт
Комплексная оценка на основе оборачиваемости, маржи, трендов и остатков
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, case

from app.models.sales_record import SalesRecord
from app.models.product_stock import ProductStock
from app.models.product import Product
from app.models.website_priority import WebsitePriority
from app.services.product_turnover_service import ProductTurnoverService
from app.services.product_analytics_service import ProductAnalyticsService

logger = logging.getLogger(__name__)


class WebsitePriorityService:
    """Сервис для расчёта приоритета товаров для сайта"""
    
    # Веса компонентов приоритета (обновлено: фото и остатки - главные приоритеты)
    IMAGE_WEIGHT = 0.40     # 40% - наличие фото (главный приоритет)
    STOCK_WEIGHT = 0.30     # 30% - наличие остатков (главный приоритет)
    TURNOVER_WEIGHT = 0.15  # 15% - оборачиваемость
    MARGIN_WEIGHT = 0.10    # 10% - маржа
    TREND_WEIGHT = 0.05     # 5% - тренд
    SEASONALITY_WEIGHT = 0.0  # 0% - сезонность (отключена)
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.turnover_service = ProductTurnoverService(db)
        self.analytics_service = ProductAnalyticsService(db)
    
    async def calculate_priority(
        self,
        analysis_period_days: int = 90,
        min_turnover_rate: float = 0.1,
        min_stock: float = 1.0
    ) -> int:
        """
        Рассчитывает приоритет товаров для выкладки на сайт
        
        Args:
            analysis_period_days: Период анализа в днях (по умолчанию 90)
            min_turnover_rate: Минимальный коэффициент оборачиваемости
            min_stock: Минимальный остаток для включения в расчёт
        
        Returns:
            Количество обработанных товаров
        """
        logger.info(f"Начало расчёта приоритетов товаров для сайта (период: {analysis_period_days} дней)")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=analysis_period_days)
        
        # Получаем данные об оборачиваемости
        turnover_data = await self.turnover_service.calculate_turnover(
            start_date=start_date,
            end_date=end_date
        )
        
        # Получаем данные о продажах для расчёта трендов
        sales_data = await self.analytics_service.get_top_products(
            start_date=start_date - timedelta(days=analysis_period_days),  # Для сравнения трендов
            end_date=end_date,
            limit=10000  # Большой лимит для получения всех товаров
        )
        
        # Получаем данные об остатках
        # ProductStock использует product_id (UUID), нужно связать через Product
        stock_query = select(
            Product.external_id.label('product_id_1c'),
            func.sum(ProductStock.available_quantity).label('total_stock')
        ).join(
            Product, ProductStock.product_id == Product.id
        ).where(
            Product.external_id.isnot(None)
        ).group_by(Product.external_id)
        
        stock_result = await self.db.execute(stock_query)
        stock_data = {row[0]: float(row[1] or 0.0) for row in stock_result.all() if row[0]}
        
        # Создаём словарь для быстрого доступа к данным
        # get_top_products возвращает product_id_1c (ID из 1С)
        turnover_map = {item.get('product_id_1c'): item for item in turnover_data if item.get('product_id_1c')}
        sales_map = {item.get('product_id_1c'): item for item in sales_data if item.get('product_id_1c')}
        
        # Собираем все уникальные товары
        all_products = set()
        all_products.update(turnover_map.keys())
        all_products.update(sales_map.keys())
        
        priorities = []
        
        for product_id_1c in all_products:
            turnover_info = turnover_map.get(product_id_1c, {})
            sales_info = sales_map.get(product_id_1c, {})
            current_stock = stock_data.get(product_id_1c, 0.0)
            
            # ОБЯЗАТЕЛЬНОЕ ТРЕБОВАНИЕ: товар должен иметь фото для размещения на сайте
            # Проверяем наличие фото ПЕРВЫМ делом
            product_check = await self.db.execute(
                select(Product.images).where(Product.external_id == product_id_1c)
            )
            product_images = product_check.scalar()
            has_images = product_images and isinstance(product_images, list) and len(product_images) > 0
            
            if not has_images:
                continue  # Пропускаем товары БЕЗ ФОТО - они не могут быть рекомендованы для размещения на сайте
            
            # Пропускаем товары с очень низкой оборачиваемостью (если нет остатков)
            turnover_rate = turnover_info.get('turnover_rate', 0.0) or 0.0
            if turnover_rate < min_turnover_rate and current_stock < min_stock:
                continue  # Пропускаем товары без остатков и с низкой оборачиваемостью
            
            # Рассчитываем компоненты приоритета
            priority_data = await self._calculate_priority_components(
                product_id_1c=product_id_1c,
                turnover_info=turnover_info,
                sales_info=sales_info,
                current_stock=current_stock,
                start_date=start_date,
                end_date=end_date
            )
            
            if priority_data:
                priorities.append(priority_data)
        
        # Сохраняем приоритеты в БД
        if priorities:
            await self._save_priorities(priorities)
        
        logger.info(f"Расчёт приоритетов завершён. Обработано товаров: {len(priorities)}")
        return len(priorities)
    
    async def _calculate_priority_components(
        self,
        product_id_1c: str,
        turnover_info: Dict[str, Any],
        sales_info: Dict[str, Any],
        current_stock: float,
        start_date: datetime,
        end_date: datetime
    ) -> Optional[Dict[str, Any]]:
        """Рассчитывает компоненты приоритета для товара"""
        
        # Получаем информацию о товаре
        product_query = select(Product).where(Product.external_id == product_id_1c)
        product_result = await self.db.execute(product_query)
        product = product_result.scalar_one_or_none()
        
        if not product:
            return None
        
        # ОБЯЗАТЕЛЬНОЕ ТРЕБОВАНИЕ: товар должен иметь фото
        has_images = False
        if product.images:
            if isinstance(product.images, list):
                has_images = len(product.images) > 0
            elif isinstance(product.images, str):
                has_images = len(product.images.strip()) > 0
        
        if not has_images:
            return None  # Товары без фото не могут быть рекомендованы для размещения на сайте
        
        # 1. Оценка оборачиваемости (0-1)
        turnover_rate = turnover_info.get('turnover_rate', 0.0) or 0.0
        turnover_days = turnover_info.get('turnover_days', 999.0) or 999.0
        # Нормализуем: высокая оборачиваемость = высокий приоритет
        # Используем обратную зависимость от дней оборачиваемости
        turnover_score = min(1.0, max(0.0, 1.0 - (turnover_days / 365.0))) if turnover_days > 0 else 0.0
        
        # 2. Оценка маржинальности (0-1)
        avg_margin = sales_info.get('avg_margin_percent', 0.0) or 0.0
        # Нормализуем: маржа от 0% до 50% = 0 до 1
        margin_score = min(1.0, max(0.0, avg_margin / 50.0)) if avg_margin else 0.0
        
        # 3. Оценка выручки (0-1) - используем общую выручку
        total_revenue = sales_info.get('total_revenue', 0.0) or 0.0
        # Нормализуем относительно максимальной выручки (берем топ-1 как 1.0)
        # Для упрощения используем логарифмическую шкалу
        revenue_score = min(1.0, max(0.0, (total_revenue / 100000.0) ** 0.5)) if total_revenue > 0 else 0.0
        
        # 4. Оценка наличия фото (0-1) - ГЛАВНЫЙ ПРИОРИТЕТ
        # Проверяем наличие изображений
        has_images = False
        image_score = 0.0
        if product.images:
            if isinstance(product.images, list):
                has_images = len(product.images) > 0
            elif isinstance(product.images, str):
                has_images = len(product.images.strip()) > 0
        
        image_score = 1.0 if has_images else 0.0
        
        # 5. Оценка наличия остатков (0-1) - ГЛАВНЫЙ ПРИОРИТЕТ
        # Товар должен быть в наличии
        stock_score = 1.0 if current_stock > 0 else 0.0
        
        # 6. Оценка тренда продаж (0-1)
        # Сравниваем продажи за первую и вторую половину периода
        mid_date = start_date + (end_date - start_date) / 2
        trend_score = await self._calculate_trend_score(product_id_1c, start_date, mid_date, end_date)
        
        # 7. Оценка сезонности (0-1) - упрощенная версия
        seasonality_score = 0.5  # По умолчанию нейтральная оценка
        
        # Рассчитываем общий приоритет с новыми весами
        priority_score = (
            image_score * self.IMAGE_WEIGHT +           # 40% - фото (главный)
            stock_score * self.STOCK_WEIGHT +           # 30% - остатки (главный)
            turnover_score * self.TURNOVER_WEIGHT +     # 15% - оборачиваемость
            margin_score * self.MARGIN_WEIGHT +         # 10% - маржа
            revenue_score * (self.TREND_WEIGHT * 0.5) + # 2.5% - выручка (часть тренда)
            trend_score * (self.TREND_WEIGHT * 0.5) +   # 2.5% - тренд
            seasonality_score * self.SEASONALITY_WEIGHT  # 0% - сезонность
        ) * 100  # Приводим к шкале 0-100
        
        # Определяем класс приоритета
        if priority_score >= 70:
            priority_class = "high"
        elif priority_score >= 40:
            priority_class = "medium"
        else:
            priority_class = "low"
        
        # Рекомендация: товар рекомендуется, если есть остатки ИЛИ хороший приоритет
        # (фото уже проверено выше - товары без фото не доходят до этого этапа)
        is_recommended = current_stock > 0 or priority_score >= 40
        recommendation_reason = self._get_recommendation_reason(
            priority_score, turnover_score, margin_score, trend_score, stock_score, has_images
        )
        
        return {
            'product_id_1c': product_id_1c,
            'product_id': product.id if product else None,
            'product_name': product.name if product else None,
            'product_article': product.article if product else None,
            'category': product.category if product else None,
            'brand': product.brand if product else None,
            'priority_score': priority_score,
            'priority_class': priority_class,
            # image_score не сохраняется в БД, так как это поле отсутствует в модели WebsitePriority
            # Информация о фото получается из Product при запросе через get_prioritized_products
            'turnover_score': turnover_score,
            'revenue_score': revenue_score,
            'margin_score': margin_score,
            'stock_score': stock_score,
            'trend_score': trend_score,
            'seasonality_score': seasonality_score,
            'is_recommended': is_recommended,
            'recommendation_reason': recommendation_reason
        }
    
    async def _calculate_trend_score(
        self,
        product_id_1c: str,
        start_date: datetime,
        mid_date: datetime,
        end_date: datetime
    ) -> float:
        """Рассчитывает оценку тренда продаж (растущий/падающий)"""
        try:
            # Продажи за первую половину периода
            first_half_query = select(
                func.sum(SalesRecord.revenue).label('revenue')
            ).where(
                and_(
                    SalesRecord.product_id == product_id_1c,
                    SalesRecord.sale_date >= start_date,
                    SalesRecord.sale_date < mid_date
                )
            )
            first_result = await self.db.execute(first_half_query)
            first_revenue = first_result.scalar() or 0.0
            
            # Продажи за вторую половину периода
            second_half_query = select(
                func.sum(SalesRecord.revenue).label('revenue')
            ).where(
                and_(
                    SalesRecord.product_id == product_id_1c,
                    SalesRecord.sale_date >= mid_date,
                    SalesRecord.sale_date <= end_date
                )
            )
            second_result = await self.db.execute(second_half_query)
            second_revenue = second_result.scalar() or 0.0
            
            # Рассчитываем рост
            if first_revenue > 0:
                growth_rate = (second_revenue - first_revenue) / first_revenue
                # Нормализуем: рост 50%+ = 1.0, падение 50%+ = 0.0
                trend_score = min(1.0, max(0.0, 0.5 + growth_rate))
            elif second_revenue > 0:
                trend_score = 1.0  # Новый товар с продажами
            else:
                trend_score = 0.0  # Нет продаж
            
            return trend_score
        except Exception as e:
            logger.warning(f"Ошибка расчёта тренда для товара {product_id_1c}: {e}")
            return 0.5  # Нейтральная оценка при ошибке
    
    def _get_recommendation_reason(
        self,
        priority_score: float,
        turnover_score: float,
        margin_score: float,
        trend_score: float,
        stock_score: float,
        has_images: bool
    ) -> str:
        """Формирует причину рекомендации"""
        reasons = []
        
        # Фото всегда есть (товары без фото отфильтрованы выше)
        reasons.append("есть фото")
        
        # Остатки - главный приоритет
        if stock_score > 0:
            reasons.append("есть в наличии")
        else:
            reasons.append("нет остатков")
        
        # Дополнительные причины
        if turnover_score > 0.7:
            reasons.append("высокая оборачиваемость")
        if margin_score > 0.7:
            reasons.append("высокая маржинальность")
        if trend_score > 0.7:
            reasons.append("растущий спрос")
        
        if not reasons:
            return "стандартный приоритет"
        
        return ", ".join(reasons)
    
    async def _save_priorities(self, priorities: List[Dict[str, Any]]):
        """Сохраняет приоритеты в БД"""
        try:
            # Используем цикл для вставки/обновления, так как уникальный индекс может отсутствовать
            for priority_data in priorities:
                product_id_1c = priority_data.get('product_id_1c')
                if not product_id_1c:
                    continue
                
                # Проверяем существование записи
                existing_query = select(WebsitePriority).where(
                    WebsitePriority.product_id_1c == product_id_1c
                )
                existing_result = await self.db.execute(existing_query)
                existing = existing_result.scalar_one_or_none()
                
                if existing:
                    # Обновляем существующую запись
                    for key, value in priority_data.items():
                        if key != 'product_id_1c' and hasattr(existing, key):
                            setattr(existing, key, value)
                    existing.updated_at = datetime.now(timezone.utc)
                else:
                    # Создаём новую запись - фильтруем только существующие поля модели
                    valid_fields = {
                        k: v for k, v in priority_data.items()
                        if hasattr(WebsitePriority, k)
                    }
                    new_priority = WebsitePriority(**valid_fields)
                    self.db.add(new_priority)
            
            await self.db.commit()
            logger.info(f"Сохранено {len(priorities)} приоритетов в БД")
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Ошибка сохранения приоритетов: {e}", exc_info=True)
            raise
    
    async def get_prioritized_products(
        self,
        limit: int = 500,  # Увеличено с 100 до 500 для большего количества товаров
        min_priority: float = 30.0,  # Снижено с 50.0 до 30.0 для большего охвата
        category: Optional[str] = None,
        only_recommended: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Получает список приоритетных товаров для выкладки на сайт
        
        Args:
            limit: Максимальное количество товаров
            min_priority: Минимальный приоритет
            category: Фильтр по категории
            only_recommended: Только рекомендованные товары
        
        Returns:
            Список товаров с приоритетами
        """
        # Делаем LEFT JOIN с Product для получения информации о фото
        query = select(
            WebsitePriority,
            Product.images.label('product_images')
        ).outerjoin(
            Product,
            WebsitePriority.product_id == Product.id
        ).where(
            WebsitePriority.priority_score >= min_priority
        )
        
        if only_recommended:
            query = query.where(WebsitePriority.is_recommended == True)
        
        if category:
            query = query.where(WebsitePriority.category == category)
        
        query = query.order_by(desc(WebsitePriority.priority_score)).limit(limit)
        
        result = await self.db.execute(query)
        rows = result.all()
        
        # Фильтруем товары БЕЗ ФОТО - они не могут быть рекомендованы для размещения на сайте
        filtered_rows = [
            (p, product_images) for p, product_images in rows
            if self._check_has_images(product_images)
        ]
        
        return [
            {
                'product_id_1c': p.product_id_1c,
                'product_id': str(p.product_id) if p.product_id else None,
                'product_name': p.product_name,
                'product_article': p.product_article,
                'category': p.category,
                'brand': p.brand,
                'priority_score': p.priority_score,
                'priority_class': p.priority_class,
                'turnover_score': p.turnover_score,
                'revenue_score': p.revenue_score,
                'margin_score': p.margin_score,
                'stock_score': p.stock_score,
                'trend_score': p.trend_score,
                'is_recommended': p.is_recommended,
                'recommendation_reason': p.recommendation_reason,
                'has_images': True,  # Все товары в этом списке имеют фото (отфильтровано выше)
                'image_score': 1.0
            }
            for p, product_images in filtered_rows
        ]
    
    def _check_has_images(self, images) -> bool:
        """Проверяет наличие изображений"""
        if not images:
            return False
        if isinstance(images, list):
            return len(images) > 0
        if isinstance(images, str):
            return len(images.strip()) > 0
        return False
    
    async def get_hidden_gems(
        self,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Получает "скрытые жемчужины" - товары с потенциалом, но низким текущим приоритетом
        
        Критерии:
        - Высокая маржа
        - Растущий тренд
        - Но низкая текущая выручка или оборачиваемость
        """
        query = select(WebsitePriority).where(
            and_(
                WebsitePriority.margin_score >= 0.6,  # Высокая маржа
                WebsitePriority.trend_score >= 0.6,   # Растущий тренд
                WebsitePriority.priority_score < 60.0  # Но не топ-приоритет
            )
        ).order_by(
            desc(WebsitePriority.trend_score),
            desc(WebsitePriority.margin_score)
        ).limit(limit)
        
        result = await self.db.execute(query)
        gems = result.scalars().all()
        
        return [
            {
                'product_id_1c': g.product_id_1c,
                'product_id': str(g.product_id) if g.product_id else None,
                'product_name': g.product_name,
                'product_article': g.product_article,
                'category': g.category,
                'brand': g.brand,
                'priority_score': g.priority_score,
                'margin_score': g.margin_score,
                'trend_score': g.trend_score,
                'recommendation_reason': "высокий потенциал роста"
            }
            for g in gems
        ]
