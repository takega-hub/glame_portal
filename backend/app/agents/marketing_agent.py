from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from app.agents.base_agent import BaseAgent
from app.services.metrics_service import MetricsService
from app.services.analytics_service import AnalyticsService
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class MarketingAgent(BaseAgent):
    """AI Marketing Agent для анализа кампаний и оптимизации маркетинга"""
    
    BRAND_SYSTEM_PROMPT = """Ты - маркетинговый аналитик бренда GLAME, пространства авторских украшений и аксессуаров.

Твоя задача:
- Анализировать эффективность маркетинговых кампаний
- Предлагать стратегии для улучшения результатов
- Оптимизировать контент-планы на основе аналитики
- Предсказывать вовлеченность аудитории

Будь аналитичным, но практичным. Всегда предлагай конкретные действия."""
    
    def __init__(self, db: AsyncSession):
        super().__init__()
        self.db = db
        self.metrics_service = MetricsService(db)
        self.analytics_service = AnalyticsService(db)
    
    async def analyze_campaign_performance(
        self,
        campaign_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        channel: Optional[str] = None
    ) -> Dict[str, Any]:
        """Анализ эффективности кампании"""
        if not start_date:
            start_date = datetime.now() - timedelta(days=30)
        if not end_date:
            end_date = datetime.now()
        
        # Получаем метрики
        conversion = await self.metrics_service.calculate_conversion(start_date, end_date, channel=channel)
        aov = await self.metrics_service.calculate_aov(start_date, end_date, channel=channel)
        engagement = await self.metrics_service.calculate_engagement(start_date, end_date)
        
        # Формируем промпт для анализа
        prompt = f"""Проанализируй эффективность маркетинговой кампании GLAME.

Период: {start_date.date()} - {end_date.date()}
Канал: {channel or 'все каналы'}

Метрики:
- Конверсия чат → покупка: {conversion.get('conversion_rates', {}).get('chat_to_purchase', 0):.2f}%
- Конверсия чат → товар: {conversion.get('conversion_rates', {}).get('chat_to_product', 0):.2f}%
- Средний чек: {aov.get('aov', 0):.2f} ₽
- Количество заказов: {aov.get('order_count', 0)}
- Средняя длительность сессии: {engagement.get('avg_session_duration_seconds', 0):.0f} сек
- Событий на сессию: {engagement.get('avg_events_per_session', 0):.2f}

События:
- Чаты: {conversion.get('events', {}).get('chat_message', 0)}
- Клики по товарам: {conversion.get('events', {}).get('product_click', 0)}
- Просмотры образов: {conversion.get('events', {}).get('look_view', 0)}
- Покупки: {conversion.get('events', {}).get('purchase', 0)}

Проанализируй и предоставь:
1. Оценку эффективности кампании (отлично/хорошо/требует улучшения)
2. Сильные стороны
3. Слабые места и узкие места
4. Конкретные рекомендации по улучшению
5. Приоритетные действия

Будь конкретным и практичным."""
        
        try:
            analysis = await self.generate_response(
                prompt=prompt,
                system_prompt=self.BRAND_SYSTEM_PROMPT,
                temperature=0.5,
                max_tokens=2000
            )
            
            return {
                "campaign_id": campaign_id,
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                },
                "channel": channel,
                "metrics": {
                    "conversion": conversion,
                    "aov": aov,
                    "engagement": engagement
                },
                "analysis": analysis,
                "overall_score": self._calculate_campaign_score(conversion, aov, engagement)
            }
        except Exception as e:
            logger.error(f"Error analyzing campaign performance: {e}")
            return {
                "campaign_id": campaign_id,
                "error": str(e),
                "analysis": "Не удалось проанализировать кампанию. Проверьте данные."
            }
    
    def _calculate_campaign_score(
        self,
        conversion: Dict[str, Any],
        aov: Dict[str, Any],
        engagement: Dict[str, Any]
    ) -> float:
        """Расчет общей оценки кампании (0-100)"""
        conversion_rate = conversion.get('conversion_rates', {}).get('chat_to_purchase', 0)
        aov_value = aov.get('aov', 0)
        avg_duration = engagement.get('avg_session_duration_seconds', 0)
        
        # Нормализуем метрики (примерные пороги)
        conversion_score = min(conversion_rate * 10, 50)  # 5% конверсия = 50 баллов
        aov_score = min(aov_value / 100, 30)  # 10000₽ = 30 баллов
        engagement_score = min(avg_duration / 60, 20)  # 20 мин = 20 баллов
        
        return conversion_score + aov_score + engagement_score
    
    async def suggest_campaign_strategy(
        self,
        goal: str,
        target_audience: Optional[str] = None,
        budget: Optional[float] = None,
        timeframe: Optional[str] = None
    ) -> Dict[str, Any]:
        """Предложение стратегии кампании"""
        prompt = f"""Предложи маркетинговую стратегию для бренда GLAME.

Цель кампании: {goal}
Целевая аудитория: {target_audience or 'не указана'}
Бюджет: {budget or 'не указан'} ₽
Сроки: {timeframe or 'не указаны'}

Предложи:
1. Общую стратегию кампании
2. Рекомендуемые каналы продвижения
3. Ключевые сообщения и месседжи
4. Контент-стратегию (типы контента, частота)
5. Метрики для отслеживания успеха
6. Ожидаемые результаты

Будь конкретным и практичным. Учитывай специфику бренда GLAME."""
        
        try:
            strategy = await self.generate_response(
                prompt=prompt,
                system_prompt=self.BRAND_SYSTEM_PROMPT,
                temperature=0.7,
                max_tokens=2500
            )
            
            return {
                "goal": goal,
                "target_audience": target_audience,
                "budget": budget,
                "timeframe": timeframe,
                "strategy": strategy
            }
        except Exception as e:
            logger.error(f"Error suggesting campaign strategy: {e}")
            return {
                "goal": goal,
                "error": str(e),
                "strategy": "Не удалось предложить стратегию. Проверьте параметры."
            }
    
    async def optimize_content_plan(
        self,
        plan_id: str,
        current_performance: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Оптимизация контент-плана на основе аналитики"""
        # Получаем данные о производительности контента
        if not current_performance:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            
            content_perf = await self.metrics_service.calculate_offline_online_comparison(start_date, end_date)
        else:
            content_perf = current_performance
        
        prompt = f"""Проанализируй контент-план GLAME и предложи оптимизации.

ID плана: {plan_id}

Текущая производительность контента:
{self._format_performance_data(content_perf)}

Предложи:
1. Оптимальное время публикаций (когда аудитория наиболее активна)
2. Рекомендуемые типы контента (какие форматы работают лучше)
3. Частоту публикаций по каналам
4. Темы и хоки, которые лучше всего резонируют
5. Улучшения для повышения вовлеченности
6. Конкретные изменения в плане

Будь конкретным и практичным."""
        
        try:
            optimization = await self.generate_response(
                prompt=prompt,
                system_prompt=self.BRAND_SYSTEM_PROMPT,
                temperature=0.6,
                max_tokens=2000
            )
            
            return {
                "plan_id": plan_id,
                "current_performance": content_perf,
                "optimization_suggestions": optimization
            }
        except Exception as e:
            logger.error(f"Error optimizing content plan: {e}")
            return {
                "plan_id": plan_id,
                "error": str(e),
                "optimization_suggestions": "Не удалось оптимизировать план. Проверьте данные."
            }
    
    def _format_performance_data(self, performance: Dict[str, Any]) -> str:
        """Форматирование данных о производительности для промпта"""
        if not performance:
            return "Данные о производительности отсутствуют."
        
        return f"""
Онлайн:
- Сессии: {performance.get('online', {}).get('sessions', 0)}
- Покупки: {performance.get('online', {}).get('purchases', 0)}
- Выручка: {performance.get('online', {}).get('revenue', 0):.2f} ₽

Офлайн:
- Посетители: {performance.get('offline', {}).get('visitors', 0)}
- Продажи: {performance.get('offline', {}).get('sales', 0)}
- Выручка: {performance.get('offline', {}).get('revenue', 0):.2f} ₽

Общее:
- Всего посетителей: {performance.get('total', {}).get('visitors', 0)}
- Всего продаж: {performance.get('total', {}).get('sales', 0)}
- Общая выручка: {performance.get('total', {}).get('revenue', 0):.2f} ₽
"""
    
    async def predict_engagement(
        self,
        content_type: str,
        channel: str,
        topic: Optional[str] = None,
        persona: Optional[str] = None,
        cjm_stage: Optional[str] = None
    ) -> Dict[str, Any]:
        """Предсказание вовлеченности для контента"""
        # Получаем исторические данные о похожем контенте
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)
        
        # Получаем события по каналу и типу контента
        events = await self.analytics_service.get_events(
            start_date=start_date,
            end_date=end_date,
            channel=channel,
            limit=1000
        )
        
        # Анализируем исторические данные
        historical_engagement = self._analyze_historical_engagement(events.get("events", []))
        
        prompt = f"""Предскажи вовлеченность для контента GLAME.

Тип контента: {content_type}
Канал: {channel}
Тема: {topic or 'не указана'}
Персона: {persona or 'не указана'}
Этап CJM: {cjm_stage or 'не указан'}

Исторические данные по похожему контенту:
- Средняя вовлеченность: {historical_engagement.get('avg_engagement', 0):.2f}
- Лучшие темы: {', '.join(historical_engagement.get('top_topics', [])[:5])}
- Оптимальное время: {historical_engagement.get('best_time', 'не определено')}

Предскажи:
1. Ожидаемый уровень вовлеченности (низкий/средний/высокий)
2. Ожидаемое количество взаимодействий
3. Вероятность конверсии
4. Рекомендации по улучшению вовлеченности
5. Лучшее время для публикации

Будь конкретным и обоснуй предсказания."""
        
        try:
            prediction = await self.generate_response(
                prompt=prompt,
                system_prompt=self.BRAND_SYSTEM_PROMPT,
                temperature=0.5,
                max_tokens=1500
            )
            
            return {
                "content_type": content_type,
                "channel": channel,
                "topic": topic,
                "persona": persona,
                "cjm_stage": cjm_stage,
                "historical_data": historical_engagement,
                "prediction": prediction,
                "predicted_engagement_score": self._calculate_engagement_score(
                    content_type, channel, historical_engagement
                )
            }
        except Exception as e:
            logger.error(f"Error predicting engagement: {e}")
            return {
                "content_type": content_type,
                "channel": channel,
                "error": str(e),
                "prediction": "Не удалось предсказать вовлеченность. Проверьте данные."
            }
    
    def _analyze_historical_engagement(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Анализ исторических данных о вовлеченности"""
        if not events:
            return {
                "avg_engagement": 0,
                "top_topics": [],
                "best_time": "не определено"
            }
        
        # Подсчитываем события по типам
        event_counts = {}
        topics = {}
        hours = {}
        
        for event in events:
            event_type = event.get("event_type", "")
            event_counts[event_type] = event_counts.get(event_type, 0) + 1
            
            # Извлекаем тему из event_data
            event_data = event.get("event_data", {})
            if isinstance(event_data, dict):
                topic = event_data.get("topic")
                if topic:
                    topics[topic] = topics.get(topic, 0) + 1
            
            # Анализируем время
            timestamp = event.get("timestamp")
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    hour = dt.hour
                    hours[hour] = hours.get(hour, 0) + 1
                except:
                    pass
        
        # Рассчитываем среднюю вовлеченность
        total_events = sum(event_counts.values())
        avg_engagement = total_events / len(events) if events else 0
        
        # Топ темы
        top_topics = sorted(topics.items(), key=lambda x: x[1], reverse=True)[:10]
        top_topics = [topic[0] for topic in top_topics]
        
        # Лучшее время
        best_hour = max(hours.items(), key=lambda x: x[1])[0] if hours else None
        best_time = f"{best_hour}:00" if best_hour is not None else "не определено"
        
        return {
            "avg_engagement": avg_engagement,
            "top_topics": top_topics,
            "best_time": best_time,
            "event_distribution": event_counts
        }
    
    def _calculate_engagement_score(
        self,
        content_type: str,
        channel: str,
        historical_data: Dict[str, Any]
    ) -> float:
        """Расчет предсказанного балла вовлеченности (0-100)"""
        base_score = 50.0
        
        # Корректировки на основе типа контента
        content_multipliers = {
            "post": 1.0,
            "story": 1.2,
            "reels": 1.5,
            "carousel": 1.1,
            "video": 1.3
        }
        base_score *= content_multipliers.get(content_type.lower(), 1.0)
        
        # Корректировки на основе канала
        channel_multipliers = {
            "instagram": 1.2,
            "telegram": 1.0,
            "website": 0.8,
            "email": 0.9
        }
        base_score *= channel_multipliers.get(channel.lower(), 1.0)
        
        # Учитываем исторические данные
        avg_engagement = historical_data.get("avg_engagement", 0)
        if avg_engagement > 0:
            base_score += min(avg_engagement * 10, 30)
        
        return min(base_score, 100.0)
