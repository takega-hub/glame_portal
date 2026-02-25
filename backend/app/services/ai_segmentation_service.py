"""
AI сервис сегментации покупателей
"""
import logging
import json
from typing import List, Dict, Any, Optional
from datetime import timedelta
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.user import User
from app.models.customer_segment import CustomerSegment
from app.models.user_segment import UserSegment
from app.services.llm_service import LLMService
from app.services.customer_analytics_service import CustomerAnalyticsService

logger = logging.getLogger(__name__)


class AISegmentationService:
    """AI сервис сегментации покупателей"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm_service = LLMService()
        self.analytics_service = CustomerAnalyticsService(db)
    
    async def auto_segment_customers(self) -> Dict[str, Any]:
        """
        Автоматическая сегментация всех покупателей через LLM
        """
        stats = {
            "segments_created": 0,
            "customers_segmented": 0,
            "errors": 0
        }
        
        try:
            # Получаем всех покупателей с метриками
            stmt = select(User).where(User.is_customer == True)
            result = await self.db.execute(stmt)
            users = result.scalars().all()
            
            if not users:
                return stats
            
            # Подготавливаем данные для LLM
            customers_data = []
            for user in users:
                customer_data = {
                    "user_id": str(user.id),
                    "total_purchases": user.total_purchases,
                    "total_spent": user.total_spent / 100,  # в рублях
                    "average_check": user.average_check / 100 if user.average_check else 0,
                    "loyalty_points": user.loyalty_points,
                    "customer_segment": user.customer_segment,
                    "rfm_score": user.rfm_score or {}
                }
                
                if user.purchase_preferences:
                    customer_data["favorite_categories"] = user.purchase_preferences.get("favorite_categories", [])
                    customer_data["favorite_brands"] = user.purchase_preferences.get("favorite_brands", [])
                
                if user.last_purchase_date:
                    from datetime import datetime
                    days_since_last = (datetime.utcnow() - user.last_purchase_date.replace(tzinfo=None)).days if user.last_purchase_date.tzinfo else (datetime.utcnow() - user.last_purchase_date).days
                    customer_data["days_since_last_purchase"] = days_since_last
                
                customers_data.append(customer_data)
            
            # Генерируем промпт для LLM
            prompt = f"""Проанализируй покупателей и создай сегменты на основе их поведения:

Данные покупателей:
{json.dumps(customers_data[:100], ensure_ascii=False, indent=2)}  # Ограничиваем до 100 для промпта

Задачи:
1. Определи 5-8 сегментов на основе поведения покупателей
2. Для каждого сегмента укажи:
   - Название (короткое, понятное, на русском)
   - Описание (1-2 предложения)
   - Правила попадания (RFM, предпочтения, поведение) в формате JSON
   - Рекомендации по работе с сегментом (2-3 пункта)

Верни результат в формате JSON:
{{
  "segments": [
    {{
      "name": "Название сегмента",
      "description": "Описание",
      "rules": {{
        "min_purchases": 5,
        "min_total": 50000,
        "max_recency_days": 90,
        "rfm_min_score": 8
      }},
      "recommendations": ["рекомендация 1", "рекомендация 2"]
    }}
  ]
}}"""
            
            # Вызываем LLM
            response = await self.llm_service.generate(
                prompt=prompt,
                system_prompt="Ты - эксперт по сегментации клиентов. Анализируй данные и создавай практичные сегменты.",
                temperature=0.7,
                max_tokens=3000
            )
            
            # Парсим ответ
            try:
                # Пытаемся извлечь JSON из ответа
                if "```json" in response:
                    json_start = response.find("```json") + 7
                    json_end = response.find("```", json_start)
                    response = response[json_start:json_end].strip()
                elif "```" in response:
                    json_start = response.find("```") + 3
                    json_end = response.find("```", json_start)
                    response = response[json_start:json_end].strip()
                
                segments_data = json.loads(response)
            except json.JSONDecodeError as e:
                logger.error(f"Ошибка парсинга JSON ответа LLM: {e}")
                logger.error(f"Ответ LLM: {response[:500]}")
                # Fallback: создаем базовые сегменты
                segments_data = self._create_fallback_segments()
            
            # Создаем или обновляем сегменты
            for segment_info in segments_data.get("segments", []):
                try:
                    segment_name = segment_info.get("name")
                    if not segment_name:
                        continue
                    
                    # Проверяем, существует ли сегмент
                    stmt = select(CustomerSegment).where(CustomerSegment.name == segment_name)
                    result = await self.db.execute(stmt)
                    segment = result.scalar_one_or_none()
                    
                    if not segment:
                        # Создаем новый сегмент
                        segment = CustomerSegment(
                            name=segment_name,
                            description=segment_info.get("description", ""),
                            rules=segment_info.get("rules", {}),
                            is_auto_generated=True,
                            color=self._get_segment_color(segment_name)
                        )
                        self.db.add(segment)
                        await self.db.flush()
                        stats["segments_created"] += 1
                    else:
                        # Обновляем существующий
                        segment.description = segment_info.get("description", segment.description)
                        segment.rules = segment_info.get("rules", segment.rules)
                    
                    # Назначаем пользователей в сегмент
                    assigned_count = await self._assign_users_to_segment(segment, segment_info.get("rules", {}), users)
                    stats["customers_segmented"] += assigned_count
                    
                except Exception as e:
                    logger.error(f"Ошибка создания сегмента {segment_info.get('name')}: {e}")
                    stats["errors"] += 1
                    continue
            
            await self.db.commit()
            
        except Exception as e:
            logger.error(f"Ошибка автоматической сегментации: {e}")
            await self.db.rollback()
            raise
        
        return stats
    
    async def _assign_users_to_segment(
        self,
        segment: CustomerSegment,
        rules: Dict[str, Any],
        all_users: List[User]
    ) -> int:
        """Назначение пользователей в сегмент на основе правил"""
        assigned_count = 0
        
        try:
            for user in all_users:
                if self._user_matches_rules(user, rules):
                    # Проверяем, не назначен ли уже пользователь в этот сегмент
                    stmt = select(UserSegment).where(
                        and_(
                            UserSegment.user_id == user.id,
                            UserSegment.segment_id == segment.id
                        )
                    )
                    result = await self.db.execute(stmt)
                    existing = result.scalar_one_or_none()
                    
                    if not existing:
                        user_segment = UserSegment(
                            user_id=user.id,
                            segment_id=segment.id,
                            assigned_by="ai",
                            confidence_score=0.8
                        )
                        self.db.add(user_segment)
                        assigned_count += 1
            
            # Обновляем счетчик сегмента
            segment.customer_count = assigned_count
            
        except Exception as e:
            logger.error(f"Ошибка назначения пользователей в сегмент: {e}")
        
        return assigned_count
    
    def _user_matches_rules(self, user: User, rules: Dict[str, Any]) -> bool:
        """Проверка соответствия пользователя правилам сегмента"""
        try:
            # Проверка минимального количества покупок
            if "min_purchases" in rules:
                if user.total_purchases < rules["min_purchases"]:
                    return False
            
            # Проверка минимальной суммы покупок
            if "min_total" in rules:
                min_total_kopecks = int(rules["min_total"] * 100)
                if user.total_spent < min_total_kopecks:
                    return False
            
            # Проверка давности последней покупки
            if "max_recency_days" in rules and user.last_purchase_date:
                from datetime import datetime
                days_since_last = (datetime.utcnow() - user.last_purchase_date.replace(tzinfo=None)).days if user.last_purchase_date.tzinfo else (datetime.utcnow() - user.last_purchase_date).days
                if days_since_last > rules["max_recency_days"]:
                    return False
            
            # Проверка RFM score
            if "rfm_min_score" in rules and user.rfm_score:
                total_score = user.rfm_score.get("total_score", 0)
                if total_score < rules["rfm_min_score"]:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка проверки правил для пользователя {user.id}: {e}")
            return False
    
    def _get_segment_color(self, segment_name: str) -> str:
        """Получение цвета для сегмента"""
        colors = {
            "VIP": "#FFD700",
            "Активные": "#4CAF50",
            "Регулярные": "#2196F3",
            "Спящие": "#9E9E9E",
            "Новые": "#FF9800"
        }
        
        for key, color in colors.items():
            if key.lower() in segment_name.lower():
                return color
        
        return "#757575"
    
    def _create_fallback_segments(self) -> Dict[str, Any]:
        """Создание базовых сегментов при ошибке LLM"""
        return {
            "segments": [
                {
                    "name": "VIP",
                    "description": "VIP клиенты с высоким LTV",
                    "rules": {
                        "min_purchases": 10,
                        "min_total": 50000,
                        "rfm_min_score": 12
                    },
                    "recommendations": ["Персональные предложения", "Приоритетная поддержка"]
                },
                {
                    "name": "Активные",
                    "description": "Активные покупатели",
                    "rules": {
                        "min_purchases": 5,
                        "max_recency_days": 90
                    },
                    "recommendations": ["Регулярные рассылки", "Специальные предложения"]
                },
                {
                    "name": "Спящие",
                    "description": "Клиенты, которые давно не покупали",
                    "rules": {
                        "min_purchases": 1,
                        "max_recency_days": 180
                    },
                    "recommendations": ["Реактивационные кампании", "Специальные скидки"]
                }
            ]
        }
    
    async def segment_customer(self, user_id: UUID) -> Optional[str]:
        """
        Сегментация конкретного покупателя
        """
        try:
            stmt = select(User).where(User.id == user_id)
            result = await self.db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user or not user.is_customer:
                return None
            
            # Получаем все активные сегменты
            stmt = select(CustomerSegment).where(CustomerSegment.is_active == True)
            result = await self.db.execute(stmt)
            segments = result.scalars().all()
            
            # Находим подходящий сегмент
            for segment in segments:
                if segment.rules and self._user_matches_rules(user, segment.rules):
                    # Назначаем пользователя в сегмент
                    stmt = select(UserSegment).where(
                        and_(
                            UserSegment.user_id == user_id,
                            UserSegment.segment_id == segment.id
                        )
                    )
                    result = await self.db.execute(stmt)
                    existing = result.scalar_one_or_none()
                    
                    if not existing:
                        user_segment = UserSegment(
                            user_id=user_id,
                            segment_id=segment.id,
                            assigned_by="ai",
                            confidence_score=0.8
                        )
                        self.db.add(user_segment)
                        await self.db.commit()
                    
                    return segment.name
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка сегментации покупателя {user_id}: {e}")
            await self.db.rollback()
            return None
    
    async def generate_segment_insights(self, segment_id: UUID) -> str:
        """
        AI инсайты по сегменту
        """
        try:
            # Получаем сегмент
            stmt = select(CustomerSegment).where(CustomerSegment.id == segment_id)
            result = await self.db.execute(stmt)
            segment = result.scalar_one_or_none()
            
            if not segment:
                return "Сегмент не найден"
            
            # Получаем пользователей сегмента
            stmt = (
                select(User)
                .join(UserSegment)
                .where(UserSegment.segment_id == segment_id)
            )
            result = await self.db.execute(stmt)
            users = result.scalars().all()
            
            if not users:
                return "В сегменте нет покупателей"
            
            # Агрегируем данные
            avg_ltv = sum(u.total_spent for u in users) / len(users) / 100
            avg_frequency = sum(u.total_purchases for u in users) / len(users)
            
            # Топ категории и бренды
            categories = {}
            brands = {}
            for user in users:
                if user.purchase_preferences:
                    for cat in user.purchase_preferences.get("favorite_categories", []):
                        categories[cat] = categories.get(cat, 0) + 1
                    for brand in user.purchase_preferences.get("favorite_brands", []):
                        brands[brand] = brands.get(brand, 0) + 1
            
            top_categories = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:5]
            top_brands = sorted(brands.items(), key=lambda x: x[1], reverse=True)[:5]
            
            # Риск оттока
            churn_data = await self.analytics_service.get_churn_risk()
            high_risk_count = sum(1 for u in users if u.rfm_score and u.rfm_score.get("total_score", 0) < 6)
            
            # Генерируем промпт
            prompt = f"""Проанализируй сегмент покупателей и дай маркетинговые рекомендации:

Сегмент: {segment.name}
Описание: {segment.description}

Статистика:
- Размер: {len(users)} покупателей
- Средний LTV: {avg_ltv:.2f} руб
- Средняя частота покупок: {avg_frequency:.2f}
- Топ категории: {[cat for cat, _ in top_categories]}
- Топ бренды: {[brand for brand, _ in top_brands]}
- Риск оттока: {high_risk_count} покупателей

Задачи:
1. Дай характеристику сегмента (поведение, предпочтения)
2. Определи риски и возможности
3. Предложи 3-5 конкретных маркетинговых действий
4. Предложи товары/образы, которые заинтересуют этот сегмент

Ответ должен быть структурированным и практичным."""
            
            response = await self.llm_service.generate(
                prompt=prompt,
                system_prompt="Ты - эксперт по маркетингу и анализу клиентской базы. Дай практичные рекомендации.",
                temperature=0.7,
                max_tokens=2000
            )
            
            return response
            
        except Exception as e:
            logger.error(f"Ошибка генерации инсайтов для сегмента {segment_id}: {e}")
            return f"Ошибка генерации инсайтов: {str(e)}"
    
    async def predict_next_purchase(self, user_id: UUID) -> Dict[str, Any]:
        """
        Предсказание следующей покупки
        """
        try:
            stmt = select(User).where(User.id == user_id)
            result = await self.db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                return {}
            
            # Простое предсказание на основе истории
            if user.last_purchase_date:
                from datetime import datetime
                days_since_last = (datetime.utcnow() - user.last_purchase_date.replace(tzinfo=None)).days if user.last_purchase_date.tzinfo else (datetime.utcnow() - user.last_purchase_date).days
                
                # Средний интервал между покупками
                if user.total_purchases > 1:
                    avg_interval = days_since_last / (user.total_purchases - 1) if user.total_purchases > 1 else 30
                    predicted_days = int(avg_interval)
                else:
                    predicted_days = 30
                
                predicted_date = datetime.utcnow() + timedelta(days=predicted_days)
                
                return {
                    "predicted_date": predicted_date.isoformat(),
                    "predicted_days": predicted_days,
                    "confidence": 0.7 if user.total_purchases >= 3 else 0.5
                }
            
            return {}
            
        except Exception as e:
            logger.error(f"Ошибка предсказания покупки для пользователя {user_id}: {e}")
            return {}
