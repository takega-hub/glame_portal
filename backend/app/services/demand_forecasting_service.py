"""
Сервис для прогнозирования спроса на товары
Использует исторические данные о продажах для прогнозирования будущего спроса
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta, date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, case
from sqlalchemy.dialects.postgresql import insert as pg_insert
import statistics

from app.models.sales_record import SalesRecord
from app.models.product import Product

logger = logging.getLogger(__name__)


class DemandForecastingService:
    """Сервис для прогнозирования спроса на товары"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def forecast_demand(
        self,
        product_id_1c: Optional[str] = None,
        category: Optional[str] = None,
        forecast_days: int = 30,
        history_days: int = 90
    ) -> List[Dict[str, Any]]:
        """
        Прогнозирует спрос на товары на указанное количество дней вперёд
        
        Args:
            product_id_1c: Фильтр по конкретному товару
            category: Фильтр по категории
            forecast_days: Количество дней для прогноза
            history_days: Количество дней истории для анализа
        
        Returns:
            Список прогнозов по товарам
        """
        logger.info(f"Начало прогнозирования спроса на {forecast_days} дней вперёд")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=history_days)
        
        # Получаем исторические данные о продажах
        # Создаем выражение один раз для использования в SELECT, GROUP BY и ORDER BY
        sale_date_trunc = func.date(SalesRecord.sale_date)
        
        query = select(
            SalesRecord.product_id.label('product_id_1c'),
            sale_date_trunc.label('sale_date'),
            func.sum(SalesRecord.quantity).label('daily_quantity'),
            # Получаем данные о товаре из SalesRecord (берем первое непустое значение)
            func.max(SalesRecord.product_name).label('product_name'),
            func.max(SalesRecord.product_article).label('product_article'),
            func.max(SalesRecord.product_category).label('product_category'),
            func.max(SalesRecord.product_brand).label('product_brand')
        ).where(
            and_(
                SalesRecord.sale_date >= start_date,
                SalesRecord.sale_date <= end_date
            )
        )
        
        if product_id_1c:
            query = query.where(SalesRecord.product_id == product_id_1c)
        
        if category:
            query = query.where(SalesRecord.product_category == category)
        
        query = query.group_by(
            SalesRecord.product_id,
            sale_date_trunc
        ).order_by(
            SalesRecord.product_id,
            sale_date_trunc
        )
        
        result = await self.db.execute(query)
        sales_data = result.all()
        
        # Группируем данные по товарам и собираем информацию о товаре
        product_sales = {}
        product_info = {}  # Храним информацию о товаре
        
        for row in sales_data:
            product_id = row[0]
            sale_date = row[1]
            quantity = float(row[2] or 0.0)
            
            if product_id not in product_sales:
                product_sales[product_id] = []
                # Сохраняем информацию о товаре из первой записи
                product_info[product_id] = {
                    'product_name': row[3],
                    'product_article': row[4],
                    'product_category': row[5],
                    'product_brand': row[6]
                }
            
            product_sales[product_id].append({
                'date': sale_date,
                'quantity': quantity
            })
        
        # Рассчитываем прогнозы для каждого товара
        forecasts = []
        for product_id, sales_history in product_sales.items():
            forecast = await self._calculate_product_forecast(
                product_id_1c=product_id,
                sales_history=sales_history,
                forecast_days=forecast_days,
                start_date=start_date,
                end_date=end_date,
                product_info=product_info.get(product_id, {})
            )
            
            if forecast:
                forecasts.append(forecast)
        
        # Сортируем по прогнозируемому спросу
        forecasts.sort(key=lambda x: x.get('forecasted_demand', 0), reverse=True)
        
        logger.info(f"Прогнозирование завершено. Обработано товаров: {len(forecasts)}")
        return forecasts
    
    async def _calculate_product_forecast(
        self,
        product_id_1c: str,
        sales_history: List[Dict[str, Any]],
        forecast_days: int,
        start_date: datetime,
        end_date: datetime,
        product_info: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Рассчитывает прогноз спроса для конкретного товара"""
        
        if len(sales_history) < 7:  # Минимум неделя данных
            return None
        
        # Получаем информацию о товаре
        # Сначала используем данные из SalesRecord (если есть)
        product_name = None
        product_article = None
        product_category = None
        product_brand = None
        product_db_id = None
        
        if product_info:
            product_name = product_info.get('product_name')
            product_article = product_info.get('product_article')
            product_category = product_info.get('product_category')
            product_brand = product_info.get('product_brand')
        
        # Если данных нет в SalesRecord, пытаемся найти в Product
        if not product_name or not product_article:
            product_query = select(Product).where(Product.external_id == product_id_1c)
            product_result = await self.db.execute(product_query)
            product = product_result.scalar_one_or_none()
            
            if product:
                product_db_id = str(product.id)
                if not product_name:
                    product_name = product.name
                if not product_article:
                    product_article = product.article
                if not product_category:
                    product_category = product.category
                if not product_brand:
                    product_brand = product.brand
        else:
            # Если данные есть в SalesRecord, все равно попробуем найти product.id для связи
            product_query = select(Product).where(Product.external_id == product_id_1c)
            product_result = await self.db.execute(product_query)
            product = product_result.scalar_one_or_none()
            if product:
                product_db_id = str(product.id)
        
        # Создаём полный временной ряд (заполняем пропуски нулями)
        date_range = {}
        current_date = start_date.date()
        end_date_only = end_date.date()
        
        while current_date <= end_date_only:
            date_range[current_date] = 0.0
            current_date += timedelta(days=1)
        
        # Заполняем реальными данными
        for sale in sales_history:
            sale_date = sale['date'] if isinstance(sale['date'], date) else sale['date'].date()
            if sale_date in date_range:
                date_range[sale_date] = sale['quantity']
        
        # Рассчитываем различные метрики
        daily_values = list(date_range.values())
        
        # 1. Простое среднее
        simple_avg = statistics.mean(daily_values) if daily_values else 0.0
        
        # 2. Взвешенное среднее (более свежие данные имеют больший вес)
        weighted_avg = self._calculate_weighted_average(daily_values)
        
        # 3. Скользящее среднее за последние 7 дней
        last_7_days = daily_values[-7:] if len(daily_values) >= 7 else daily_values
        moving_avg_7 = statistics.mean(last_7_days) if last_7_days else 0.0
        
        # 4. Скользящее среднее за последние 30 дней
        last_30_days = daily_values[-30:] if len(daily_values) >= 30 else daily_values
        moving_avg_30 = statistics.mean(last_30_days) if last_30_days else 0.0
        
        # 5. Тренд (линейная регрессия)
        trend = self._calculate_trend(daily_values)
        
        # 6. Сезонность (день недели)
        weekday_pattern = self._calculate_weekday_pattern(sales_history)
        
        # 7. Прогноз на основе комбинации методов
        # Используем взвешенную комбинацию: 40% взвешенное среднее, 30% тренд, 20% скользящее среднее 7 дней, 10% сезонность
        base_forecast = (
            weighted_avg * 0.4 +
            (simple_avg + trend * forecast_days) * 0.3 +
            moving_avg_7 * 0.2 +
            simple_avg * 0.1  # Базовое значение для сезонности
        )
        
        # Применяем сезонность
        seasonal_adjustment = self._get_seasonal_adjustment(weekday_pattern, forecast_days)
        forecasted_demand = base_forecast * forecast_days * seasonal_adjustment
        
        # Рассчитываем доверительный интервал (простая оценка на основе стандартного отклонения)
        std_dev = statistics.stdev(daily_values) if len(daily_values) > 1 else 0.0
        confidence_interval = {
            'lower': max(0, forecasted_demand - 1.96 * std_dev * (forecast_days ** 0.5)),
            'upper': forecasted_demand + 1.96 * std_dev * (forecast_days ** 0.5)
        }
        
        # Рассчитываем точность прогноза (на основе вариативности)
        coefficient_of_variation = (std_dev / simple_avg) if simple_avg > 0 else 1.0
        forecast_accuracy = max(0, min(100, 100 - (coefficient_of_variation * 50)))
        
        # Определяем сезонность
        seasonality = self._detect_seasonality(daily_values)
        
        # В тестовом режиме: если нет названия, используем product_id_1c для идентификации
        if not product_name and product_id_1c:
            product_name = f"Товар {product_id_1c[:8]}..." if len(product_id_1c) > 8 else f"Товар {product_id_1c}"
            logger.debug(f"Товар {product_id_1c}: название не найдено, используем ID для идентификации")
        
        if not product_article and product_id_1c:
            # Пытаемся извлечь артикул из product_id, если это возможно
            product_article = product_id_1c[:20]  # Первые 20 символов как временный артикул
            logger.debug(f"Товар {product_id_1c}: артикул не найден, используем часть ID")
        
        # Логируем информацию о товаре для отладки
        if not product_name or not product_article:
            logger.warning(f"Товар {product_id_1c}: неполная информация - name={product_name}, article={product_article}, category={product_category}")
        
        return {
            'product_id_1c': product_id_1c,
            'product_id': product_db_id,
            'product_name': product_name or f"Товар {product_id_1c[:8]}...",
            'product_article': product_article or product_id_1c[:20],
            'category': product_category,
            'brand': product_brand,
            'forecast_days': forecast_days,
            'forecasted_demand': round(forecasted_demand, 2),
            'forecasted_daily_avg': round(forecasted_demand / forecast_days, 2),
            'confidence_interval': {
                'lower': round(confidence_interval['lower'], 2),
                'upper': round(confidence_interval['upper'], 2)
            },
            'forecast_accuracy': round(forecast_accuracy, 1),
            'trend': round(trend, 4),
            'seasonality': seasonality,
            'historical_avg_daily': round(simple_avg, 2),
            'weighted_avg_daily': round(weighted_avg, 2),
            'moving_avg_7_days': round(moving_avg_7, 2),
            'moving_avg_30_days': round(moving_avg_30, 2),
            'volatility': round(coefficient_of_variation, 3)
        }
    
    def _calculate_weighted_average(self, values: List[float]) -> float:
        """Рассчитывает взвешенное среднее (более свежие значения имеют больший вес)"""
        if not values:
            return 0.0
        
        n = len(values)
        total_weight = 0.0
        weighted_sum = 0.0
        
        for i, value in enumerate(values):
            weight = (i + 1) / n  # Линейное увеличение веса
            weighted_sum += value * weight
            total_weight += weight
        
        return weighted_sum / total_weight if total_weight > 0 else 0.0
    
    def _calculate_trend(self, values: List[float]) -> float:
        """Рассчитывает тренд (наклон линейной регрессии)"""
        if len(values) < 2:
            return 0.0
        
        n = len(values)
        x = list(range(n))
        y = values
        
        # Простая линейная регрессия
        x_mean = statistics.mean(x)
        y_mean = statistics.mean(y)
        
        numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            return 0.0
        
        slope = numerator / denominator
        return slope
    
    def _calculate_weekday_pattern(self, sales_history: List[Dict[str, Any]]) -> Dict[int, float]:
        """Рассчитывает паттерн продаж по дням недели"""
        weekday_sales = {i: [] for i in range(7)}  # 0 = понедельник, 6 = воскресенье
        
        for sale in sales_history:
            sale_date = sale['date'] if isinstance(sale['date'], date) else sale['date'].date()
            weekday = sale_date.weekday()
            weekday_sales[weekday].append(sale['quantity'])
        
        weekday_avg = {}
        for weekday, sales in weekday_sales.items():
            weekday_avg[weekday] = statistics.mean(sales) if sales else 0.0
        
        return weekday_avg
    
    def _get_seasonal_adjustment(self, weekday_pattern: Dict[int, float], forecast_days: int) -> float:
        """Рассчитывает сезонную корректировку на основе дня недели"""
        if not weekday_pattern or all(v == 0 for v in weekday_pattern.values()):
            return 1.0
        
        # Рассчитываем среднее по всем дням недели
        avg_weekday = statistics.mean(weekday_pattern.values()) if weekday_pattern else 0.0
        
        if avg_weekday == 0:
            return 1.0
        
        # Рассчитываем среднюю корректировку для прогнозируемого периода
        today = datetime.now()
        total_adjustment = 0.0
        
        for i in range(forecast_days):
            forecast_date = today + timedelta(days=i)
            weekday = forecast_date.weekday()
            weekday_avg = weekday_pattern.get(weekday, avg_weekday)
            adjustment = weekday_avg / avg_weekday if avg_weekday > 0 else 1.0
            total_adjustment += adjustment
        
        return total_adjustment / forecast_days if forecast_days > 0 else 1.0
    
    def _detect_seasonality(self, values: List[float]) -> str:
        """Определяет тип сезонности на основе данных"""
        if len(values) < 14:  # Минимум 2 недели
            return "недостаточно данных"
        
        # Проверяем наличие недельного паттерна
        weekly_variance = self._calculate_weekly_variance(values)
        
        if weekly_variance > 0.3:
            return "недельная сезонность"
        elif weekly_variance > 0.1:
            return "слабая сезонность"
        else:
            return "стабильный спрос"
    
    def _calculate_weekly_variance(self, values: List[float]) -> float:
        """Рассчитывает вариативность по неделям"""
        if len(values) < 7:
            return 0.0
        
        # Разбиваем на недели
        weeks = []
        for i in range(0, len(values), 7):
            week_values = values[i:i+7]
            if week_values:
                weeks.append(statistics.mean(week_values))
        
        if len(weeks) < 2:
            return 0.0
        
        # Рассчитываем коэффициент вариации между неделями
        mean_weekly = statistics.mean(weeks)
        if mean_weekly == 0:
            return 0.0
        
        std_weekly = statistics.stdev(weeks) if len(weeks) > 1 else 0.0
        coefficient_of_variation = std_weekly / mean_weekly if mean_weekly > 0 else 0.0
        
        return coefficient_of_variation
    
    async def get_seasonal_forecast(
        self,
        category: Optional[str] = None,
        months_ahead: int = 3
    ) -> Dict[str, Any]:
        """
        Прогнозирует сезонный спрос на несколько месяцев вперёд
        
        Args:
            category: Фильтр по категории
            months_ahead: Количество месяцев для прогноза
        
        Returns:
            Словарь с сезонными прогнозами
        """
        logger.info(f"Начало сезонного прогнозирования на {months_ahead} месяцев вперёд")
        
        # Получаем данные за последний год для анализа сезонности
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        
        # Создаем выражение один раз для использования в SELECT, GROUP BY и ORDER BY
        month_trunc = func.date_trunc('month', SalesRecord.sale_date)
        
        query = select(
            month_trunc.label('month'),
            func.sum(SalesRecord.quantity).label('monthly_quantity')
        ).where(
            SalesRecord.sale_date >= start_date,
            SalesRecord.sale_date <= end_date
        )
        
        if category:
            query = query.where(SalesRecord.product_category == category)
        
        query = query.group_by(
            month_trunc
        ).order_by(
            month_trunc
        )
        
        result = await self.db.execute(query)
        monthly_data = result.all()
        
        if not monthly_data:
            return {
                "status": "no_data",
                "message": "Недостаточно данных для сезонного прогноза"
            }
        
        # Рассчитываем средние продажи по месяцам
        monthly_avg = {}
        for row in monthly_data:
            month = row[0]
            quantity = float(row[1] or 0.0)
            month_key = month.strftime('%Y-%m')
            monthly_avg[month_key] = quantity
        
        # Прогнозируем на будущие месяцы
        forecasts = []
        current_month = datetime.now().replace(day=1)
        
        for i in range(months_ahead):
            forecast_month = (current_month + timedelta(days=32 * i)).replace(day=1)
            month_key = forecast_month.strftime('%Y-%m')
            
            # Используем среднее значение за аналогичные месяцы прошлых лет
            # Упрощённая версия - используем среднее за все месяцы
            avg_monthly = statistics.mean(monthly_avg.values()) if monthly_avg else 0.0
            
            forecasts.append({
                'month': month_key,
                'forecasted_demand': round(avg_monthly, 2),
                'confidence': 'medium'
            })
        
        return {
            "status": "success",
            "forecast_months": months_ahead,
            "forecasts": forecasts,
            "historical_avg": round(statistics.mean(monthly_avg.values()) if monthly_avg else 0.0, 2)
        }
    
    async def get_demand_trends(
        self,
        product_id_1c: Optional[str] = None,
        category: Optional[str] = None,
        days: int = 90
    ) -> Dict[str, Any]:
        """
        Анализирует тренды спроса за указанный период
        
        Returns:
            Словарь с анализом трендов
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Создаем выражение один раз для использования в SELECT, GROUP BY и ORDER BY
        week_trunc = func.date_trunc('week', SalesRecord.sale_date)
        
        query = select(
            week_trunc.label('week'),
            func.sum(SalesRecord.quantity).label('weekly_quantity')
        ).where(
            SalesRecord.sale_date >= start_date,
            SalesRecord.sale_date <= end_date
        )
        
        if product_id_1c:
            query = query.where(SalesRecord.product_id == product_id_1c)
        
        if category:
            query = query.where(SalesRecord.product_category == category)
        
        query = query.group_by(
            week_trunc
        ).order_by(
            week_trunc
        )
        
        result = await self.db.execute(query)
        weekly_data = result.all()
        
        if not weekly_data or len(weekly_data) < 2:
            return {
                "status": "insufficient_data",
                "message": "Недостаточно данных для анализа трендов"
            }
        
        weekly_values = [float(row[1] or 0.0) for row in weekly_data]
        
        # Рассчитываем тренд
        trend = self._calculate_trend(weekly_values)
        
        # Определяем направление тренда
        if trend > 0.1:
            trend_direction = "растущий"
        elif trend < -0.1:
            trend_direction = "падающий"
        else:
            trend_direction = "стабильный"
        
        # Рассчитываем процент изменения
        first_half = statistics.mean(weekly_values[:len(weekly_values)//2]) if weekly_values else 0.0
        second_half = statistics.mean(weekly_values[len(weekly_values)//2:]) if weekly_values else 0.0
        
        percent_change = ((second_half - first_half) / first_half * 100) if first_half > 0 else 0.0
        
        return {
            "status": "success",
            "period_days": days,
            "trend_direction": trend_direction,
            "trend_value": round(trend, 4),
            "percent_change": round(percent_change, 2),
            "first_half_avg": round(first_half, 2),
            "second_half_avg": round(second_half, 2),
            "overall_avg": round(statistics.mean(weekly_values), 2)
        }
