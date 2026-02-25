"""
Сервис аналитики покупателей
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc, literal_column
from sqlalchemy.orm import selectinload

from app.models.user import User
from app.models.purchase_history import PurchaseHistory
from app.models.customer_segment import CustomerSegment
from app.models.user_segment import UserSegment

logger = logging.getLogger(__name__)


class CustomerAnalyticsService:
    """Сервис аналитики покупателей"""
    
    def __init__(self, db: AsyncSession):
        self.db = db

    def _col(self, name: str):
        """Безопасный доступ к колонке модели User."""
        col = getattr(User, name, None)
        if col is not None:
            return col
        # Если колонка не найдена, используем literal_column
        return literal_column(name)
    
    async def calculate_rfm_score(
        self,
        user_id: UUID,
        purchases: Optional[List[PurchaseHistory]] = None
    ) -> Dict[str, Any]:
        """
        RFM анализ для покупателя
        """
        try:
            if not purchases:
                # Получаем историю покупок
                stmt = select(PurchaseHistory).where(PurchaseHistory.user_id == user_id)
                result = await self.db.execute(stmt)
                purchases = result.scalars().all()
            
            if not purchases:
                return {
                    "recency": None,
                    "frequency": 0,
                    "monetary": 0,
                    "r_score": 1,
                    "f_score": 1,
                    "m_score": 1,
                    "total_score": 3
                }
            
            now = datetime.utcnow()
            
            # Recency: дней с последней покупки
            last_purchase = max(p.purchase_date for p in purchases)
            recency_days = (now - last_purchase.replace(tzinfo=None)).days if last_purchase.tzinfo else (now - last_purchase).days
            
            # Frequency: количество покупок
            frequency = len(purchases)
            
            # Monetary: общая сумма покупок
            monetary = sum(p.total_amount for p in purchases)
            
            # Скоринг (1-5)
            r_score = self._score_recency(recency_days)
            f_score = self._score_frequency(frequency)
            m_score = self._score_monetary(monetary)
            
            return {
                "recency": recency_days,
                "frequency": frequency,
                "monetary": monetary,
                "r_score": r_score,
                "f_score": f_score,
                "m_score": m_score,
                "total_score": r_score + f_score + m_score
            }
            
        except Exception as e:
            logger.error(f"Ошибка расчета RFM для пользователя {user_id}: {e}")
            return {
                "recency": None,
                "frequency": 0,
                "monetary": 0,
                "r_score": 1,
                "f_score": 1,
                "m_score": 1,
                "total_score": 3
            }
    
    def _score_recency(self, days: int) -> int:
        """Скоринг Recency (меньше дней = выше балл)"""
        if days <= 30:
            return 5
        elif days <= 60:
            return 4
        elif days <= 90:
            return 3
        elif days <= 180:
            return 2
        else:
            return 1
    
    def _score_frequency(self, frequency: int) -> int:
        """Скоринг Frequency (больше покупок = выше балл)"""
        if frequency >= 20:
            return 5
        elif frequency >= 10:
            return 4
        elif frequency >= 5:
            return 3
        elif frequency >= 2:
            return 2
        else:
            return 1
    
    def _score_monetary(self, monetary: int) -> int:
        """Скоринг Monetary (больше сумма = выше балл)"""
        # monetary в копейках
        rubles = monetary / 100
        if rubles >= 100000:
            return 5
        elif rubles >= 50000:
            return 4
        elif rubles >= 20000:
            return 3
        elif rubles >= 10000:
            return 2
        else:
            return 1
    
    async def get_rfm_analysis(
        self,
        segment_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        RFM анализ всех/сегмента покупателей
        """
        try:
            # Получаем пользователей
            if segment_id:
                stmt = (
                    select(User)
                    .join(UserSegment)
                    .where(UserSegment.segment_id == segment_id)
                )
            else:
                is_customer_col = self._col("is_customer")
                stmt = select(User).where(is_customer_col == True)
            
            result = await self.db.execute(stmt)
            users = result.scalars().all()
            
            # Агрегируем RFM данные
            rfm_distribution = {
                "r_scores": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
                "f_scores": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
                "m_scores": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
                "total_scores": {3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0, 10: 0, 11: 0, 12: 0, 13: 0, 14: 0, 15: 0}
            }
            
            for user in users:
                try:
                    rfm_score = getattr(user, "rfm_score", None)
                    # Проверяем, что rfm_score является словарем
                    if rfm_score and isinstance(rfm_score, dict):
                        r_score = rfm_score.get("r_score", 1)
                        f_score = rfm_score.get("f_score", 1)
                        m_score = rfm_score.get("m_score", 1)
                        total_score = r_score + f_score + m_score
                        
                        # Безопасное обновление счетчиков
                        if r_score in rfm_distribution["r_scores"]:
                            rfm_distribution["r_scores"][r_score] = rfm_distribution["r_scores"][r_score] + 1
                        if f_score in rfm_distribution["f_scores"]:
                            rfm_distribution["f_scores"][f_score] = rfm_distribution["f_scores"][f_score] + 1
                        if m_score in rfm_distribution["m_scores"]:
                            rfm_distribution["m_scores"][m_score] = rfm_distribution["m_scores"][m_score] + 1
                        if total_score in rfm_distribution["total_scores"]:
                            rfm_distribution["total_scores"][total_score] = rfm_distribution["total_scores"][total_score] + 1
                except Exception as user_error:
                    logger.warning(f"Ошибка обработки RFM для пользователя {getattr(user, 'id', 'unknown')}: {user_error}")
                    continue
            
            # Безопасный расчет средних значений
            if users:
                r_scores_list = []
                f_scores_list = []
                m_scores_list = []
                
                for u in users:
                    try:
                        rfm_score = getattr(u, "rfm_score", None)
                        if rfm_score and isinstance(rfm_score, dict):
                            r_scores_list.append(rfm_score.get("r_score", 1))
                            f_scores_list.append(rfm_score.get("f_score", 1))
                            m_scores_list.append(rfm_score.get("m_score", 1))
                        else:
                            # Значения по умолчанию, если rfm_score отсутствует или не является словарем
                            r_scores_list.append(1)
                            f_scores_list.append(1)
                            m_scores_list.append(1)
                    except Exception:
                        # В случае ошибки используем значения по умолчанию
                        r_scores_list.append(1)
                        f_scores_list.append(1)
                        m_scores_list.append(1)
                
                users_count = len(r_scores_list)
                avg_rfm = {
                    "r_score": sum(r_scores_list) / users_count if users_count > 0 else 0,
                    "f_score": sum(f_scores_list) / users_count if users_count > 0 else 0,
                    "m_score": sum(m_scores_list) / users_count if users_count > 0 else 0
                }
            else:
                avg_rfm = {
                    "r_score": 0,
                    "f_score": 0,
                    "m_score": 0
                }
            
            return {
                "total_customers": len(users),
                "rfm_distribution": rfm_distribution,
                "average_rfm": avg_rfm
            }
            
        except Exception as e:
            logger.error(f"Ошибка RFM анализа: {e}")
            return {}
    
    async def get_ltv_metrics(
        self,
        user_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        LTV для покупателя или средний LTV
        """
        try:
            total_spent_col = self._col("total_spent")
            is_customer_col = self._col("is_customer")

            if user_id:
                # LTV конкретного покупателя
                stmt = select(User).where(User.id == user_id)
                result = await self.db.execute(stmt)
                user = result.scalar_one_or_none()
                
                if not user:
                    return {}
                
                # LTV = total_spent (уже рассчитан)
                # Средний LTV за период = total_spent / количество месяцев с первой покупки
                months_active = 1
                if user.created_at:
                    try:
                        # Нормализуем дату к UTC aware
                        created_at = user.created_at
                        if created_at.tzinfo is None:
                            created_at = created_at.replace(tzinfo=timezone.utc)
                        else:
                            created_at = created_at.astimezone(timezone.utc)
                        
                        now_utc = datetime.now(timezone.utc)
                        months_active = max(1, (now_utc - created_at).days / 30)
                    except Exception as date_error:
                        logger.warning(f"Ошибка расчета months_active для пользователя {user_id}: {date_error}")
                        months_active = 1
                
                user_total_spent = getattr(user, "total_spent", 0) or 0
                user_total_purchases = getattr(user, "total_purchases", 0) or 0
                return {
                    "ltv": user_total_spent / 100,  # в рублях
                    "ltv_kopecks": user_total_spent,
                    "average_monthly_ltv": (user_total_spent / 100) / months_active if months_active > 0 else 0,
                    "months_active": months_active,
                    "total_purchases": user_total_purchases
                }
            else:
                # Средний LTV всех покупателей
                stmt = select(
                    func.count(User.id).label("total_customers"),
                    func.sum(total_spent_col).label("total_ltv"),
                    func.avg(total_spent_col).label("avg_ltv")
                ).where(is_customer_col == True)
                
                result = await self.db.execute(stmt)
                row = result.first()
                
                if row:
                    return {
                        "total_customers": row.total_customers or 0,
                        "total_ltv": (row.total_ltv or 0) / 100,  # в рублях
                        "average_ltv": (row.avg_ltv or 0) / 100  # в рублях
                    }
                else:
                    return {
                        "total_customers": 0,
                        "total_ltv": 0,
                        "average_ltv": 0
                    }
                
        except Exception as e:
            logger.error(f"Ошибка расчета LTV: {e}", exc_info=True)
            return {
                "total_customers": 0,
                "total_ltv": 0,
                "average_ltv": 0
            }
    
    async def get_customer_segments_stats(self) -> Dict[str, Any]:
        """
        Статистика по сегментам
        """
        try:
            stmt = select(CustomerSegment).where(CustomerSegment.is_active == True)
            result = await self.db.execute(stmt)
            segments = result.scalars().all()
            
            stats = []
            for segment in segments:
                try:
                    # Получаем пользователей сегмента
                    stmt = (
                        select(User)
                        .join(UserSegment)
                        .where(UserSegment.segment_id == segment.id)
                    )
                    result = await self.db.execute(stmt)
                    users = result.scalars().all()
                    
                    if users and len(users) > 0:
                        users_count = len(users)
                        total_spent_sum = sum((getattr(u, "total_spent", 0) or 0) for u in users)
                        total_purchases_sum = sum((getattr(u, "total_purchases", 0) or 0) for u in users)
                        avg_ltv = (total_spent_sum / users_count / 100) if users_count > 0 else 0
                        avg_purchases = (total_purchases_sum / users_count) if users_count > 0 else 0
                    else:
                        avg_ltv = 0
                        avg_purchases = 0
                    
                    stats.append({
                        "segment_id": str(segment.id),
                        "name": segment.name or "",
                        "description": segment.description or "",
                        "customer_count": len(users),
                        "average_ltv": avg_ltv,
                        "average_purchases": avg_purchases,
                        "color": segment.color or ""
                    })
                except Exception as segment_error:
                    logger.warning(f"Ошибка обработки сегмента {segment.id}: {segment_error}")
                    # Добавляем сегмент с нулевыми значениями
                    stats.append({
                        "segment_id": str(segment.id),
                        "name": segment.name or "",
                        "description": segment.description or "",
                        "customer_count": 0,
                        "average_ltv": 0,
                        "average_purchases": 0,
                        "color": segment.color or ""
                    })
            
            return {
                "segments": stats,
                "total_segments": len(segments)
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики сегментов: {e}", exc_info=True)
            return {
                "segments": [],
                "total_segments": 0
            }
    
    async def get_purchase_preferences(
        self,
        user_id: UUID
    ) -> Dict[str, Any]:
        """
        Предпочтения по категориям/брендам
        """
        try:
            stmt = select(User).where(User.id == user_id)
            result = await self.db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                return {}
            
            return user.purchase_preferences or {}
            
        except Exception as e:
            logger.error(f"Ошибка получения предпочтений: {e}")
            return {}
    
    async def get_cohort_analysis(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """
        Когортный анализ
        """
        try:
            # Группируем пользователей по месяцу регистрации
            stmt = (
                select(
                    func.date_trunc('month', User.created_at).label("cohort_month"),
                    func.count(User.id).label("customers"),
                    func.sum(User.total_spent).label("total_revenue")
                )
                .where(
                    and_(
                        User.is_customer == True,
                        User.created_at >= start_date,
                        User.created_at <= end_date
                    )
                )
                .group_by("cohort_month")
                .order_by("cohort_month")
            )
            
            result = await self.db.execute(stmt)
            cohorts = result.all()
            
            return {
                "cohorts": [
                    {
                        "month": str(row.cohort_month),
                        "customers": row.customers,
                        "total_revenue": (row.total_revenue or 0) / 100
                    }
                    for row in cohorts
                ]
            }
            
        except Exception as e:
            logger.error(f"Ошибка когортного анализа: {e}")
            return {}
    
    async def get_churn_risk(
        self,
        user_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Риск оттока (для пользователя или всех)
        """
        try:
            if user_id:
                # Риск для конкретного пользователя
                stmt = select(User).where(User.id == user_id)
                result = await self.db.execute(stmt)
                user = result.scalar_one_or_none()
                
                if not user:
                    return {}
                
                risk_score = 0
                risk_factors = []
                
                # Нормализация текущего времени к UTC aware
                now_utc = datetime.now(timezone.utc)
                
                # Фактор 1: давность последней покупки
                if user.last_purchase_date:
                    # Нормализуем дату к UTC aware
                    last_purchase = user.last_purchase_date
                    if last_purchase.tzinfo is None:
                        last_purchase = last_purchase.replace(tzinfo=timezone.utc)
                    else:
                        last_purchase = last_purchase.astimezone(timezone.utc)
                    
                    days_since_last = (now_utc - last_purchase).days
                    if days_since_last > 180:
                        risk_score += 3
                        risk_factors.append(f"Не покупал {days_since_last} дней")
                    elif days_since_last > 90:
                        risk_score += 2
                        risk_factors.append(f"Не покупал {days_since_last} дней")
                    elif days_since_last > 60:
                        risk_score += 1
                        risk_factors.append(f"Не покупал {days_since_last} дней")
                
                # Фактор 2: низкая частота покупок
                if user.total_purchases > 0 and user.created_at:
                    # Нормализуем created_at к UTC aware
                    created_at = user.created_at
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    else:
                        created_at = created_at.astimezone(timezone.utc)
                    
                    months_active = max(1, (now_utc - created_at).days / 30)
                    purchases_per_month = user.total_purchases / months_active
                    if purchases_per_month < 0.5:
                        risk_score += 2
                        risk_factors.append("Низкая частота покупок")
                
                # Фактор 3: низкий RFM score
                if user.rfm_score:
                    total_score = user.rfm_score.get("total_score", 0)
                    if total_score < 6:
                        risk_score += 2
                        risk_factors.append("Низкий RFM score")
                
                risk_level = "low"
                if risk_score >= 5:
                    risk_level = "high"
                elif risk_score >= 3:
                    risk_level = "medium"
                
                return {
                    "user_id": str(user_id),
                    "risk_score": risk_score,
                    "risk_level": risk_level,
                    "risk_factors": risk_factors
                }
            else:
                # Риск для всех покупателей
                is_customer_col = self._col("is_customer")
                stmt = select(User).where(is_customer_col == True)
                result = await self.db.execute(stmt)
                users = result.scalars().all()
                
                high_risk = 0
                medium_risk = 0
                low_risk = 0
                
                for user in users:
                    try:
                        risk_data = await self.get_churn_risk(user.id)
                        risk_level = risk_data.get("risk_level", "low")
                        if risk_level == "high":
                            high_risk += 1
                        elif risk_level == "medium":
                            medium_risk += 1
                        else:
                            low_risk += 1
                    except Exception as user_error:
                        logger.warning(f"Ошибка расчета риска оттока для пользователя {user.id}: {user_error}")
                        # Считаем как низкий риск, если не удалось рассчитать
                        low_risk += 1
                
                return {
                    "total_customers": len(users),
                    "high_risk": high_risk,
                    "medium_risk": medium_risk,
                    "low_risk": low_risk
                }
                
        except Exception as e:
            logger.error(f"Ошибка расчета риска оттока: {e}")
            return {}
    
    async def get_top_customers(
        self,
        limit: int = 100,
        metric: str = 'total_spent'
    ) -> List[Dict[str, Any]]:
        """
        Топ покупателей
        """
        try:
            order_by_field = self._col("total_spent")
            if metric == 'total_purchases':
                order_by_field = self._col("total_purchases")
            elif metric == 'loyalty_points':
                order_by_field = self._col("loyalty_points")
            
            stmt = (
                select(User)
                .where(self._col("is_customer") == True)
                .order_by(desc(order_by_field))
                .limit(limit)
            )
            
            result = await self.db.execute(stmt)
            users = result.scalars().all()
            
            return [
                {
                    "user_id": str(user.id),
                    "phone": getattr(user, "phone", None),
                    "full_name": getattr(user, "full_name", None),
                    "total_spent": (getattr(user, "total_spent", 0) or 0) / 100,
                    "total_purchases": getattr(user, "total_purchases", 0) or 0,
                    "loyalty_points": getattr(user, "loyalty_points", 0) or 0,
                    "customer_segment": getattr(user, "customer_segment", None),
                    "last_purchase_date": user.last_purchase_date.isoformat() if user.last_purchase_date else None
                }
                for user in users
            ]
            
        except Exception as e:
            logger.error(f"Ошибка получения топ покупателей: {e}")
            return []
