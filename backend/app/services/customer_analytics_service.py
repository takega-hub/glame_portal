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
from app.models.store import Store
from app.models.customer_segment import CustomerSegment
from app.models.user_segment import UserSegment
from sqlalchemy import update

logger = logging.getLogger(__name__)

CENTRUM_STORE_ID_1C = "6c3a8322-a2ab-11f0-96fc-fa163e4cc04e"
YALTA_STORE_ID_1C = "3daee4e4-a2ab-11f0-96fc-fa163e4cc04e"
MEGANOM_STORE_ID_1C = "8cebda58-a2ab-11f0-96fc-fa163e4cc04e"
CLOSED_STORE_REDIRECTS = {
    MEGANOM_STORE_ID_1C: CENTRUM_STORE_ID_1C,
}


def _normalize_city(value: Optional[str]) -> str:
    normalized = (value or "").strip().lower().replace("ё", "е")
    return normalized.replace("c", "с")


def _fallback_store_for_city(city: Optional[str]) -> str:
    city_norm = _normalize_city(city)
    if "ял" in city_norm:
        return YALTA_STORE_ID_1C
    if any(part in city_norm for part in ("сим", "сім", "смф", "сфер", "сифм", "севаст", "севас", "сев")):
        return CENTRUM_STORE_ID_1C
    return CENTRUM_STORE_ID_1C


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
    
    async def refresh_preferred_store_by_count(self, user_id: UUID, commit: bool = True) -> Dict[str, Any]:
        """
        Определяет предпочитаемый магазин по количеству покупок и сохраняет в users.*
        Поля: preferred_store_external_id, preferred_store_name, preferred_store_share, preferred_store_updated_at
        
        Также обновляет город пользователя, если магазин однозначно определяет город:
        - Ялта, Набережная 18 -> Ялта
        - Меганом, Центрум -> Симферополь
        """
        # Считаем покупки по store_id_1c
        rows = await self.db.execute(
            select(
                PurchaseHistory.store_id_1c,
                func.count().label("cnt"),
                func.coalesce(func.sum(PurchaseHistory.total_amount), 0).label("total_amount"),
                func.max(PurchaseHistory.purchase_date).label("last_purchase_date"),
            )
            .where(PurchaseHistory.user_id == user_id, PurchaseHistory.store_id_1c.isnot(None))
            .group_by(PurchaseHistory.store_id_1c)
        )
        stats = rows.all()
        total = sum(r[1] for r in stats) or 0
        if not stats:
            user_row = await self.db.execute(select(User.city).where(User.id == user_id))
            city = user_row.scalar_one_or_none()
            best_store_id_1c = _fallback_store_for_city(city)
            total = 0
            best_cnt = 0
        else:
            # Выбираем магазин с максимальным количеством; при равенстве - по сумме и свежести.
            best = max(
                stats,
                key=lambda x: (
                    int(x.cnt or 0),
                    int(x.total_amount or 0),
                    x.last_purchase_date or datetime.min.replace(tzinfo=timezone.utc),
                ),
            )
            best_store_id_1c = CLOSED_STORE_REDIRECTS.get(best.store_id_1c, best.store_id_1c)
            best_cnt = best.cnt

        # Находим название
        store_row = await self.db.execute(select(Store.name, Store.city).where(Store.external_id == best_store_id_1c))
        store_data = store_row.first()
        name = store_data.name if store_data else None
        store_city = store_data.city if store_data else None
        share = (best_cnt / total) if total else 0.0
        
        # Подготовка значений для обновления
        update_values = {
            "preferred_store_external_id": best_store_id_1c,
            "preferred_store_name": name,
            "preferred_store_share": share,
            "preferred_store_updated_at": func.now(),
        }
        
        # Логика обновления города на основе магазина
        if name:
            normalized_name = name.lower()
            new_city = None
            if store_city:
                new_city = store_city
            elif "ялта" in normalized_name and "набережная" in normalized_name:
                new_city = "Ялта"
            elif "меганом" in normalized_name or "центрум" in normalized_name:
                new_city = "Симферополь"
            
            if new_city:
                update_values["city"] = new_city
                logger.info(f"Обновлен город пользователя {user_id} на основе магазина {name}: {new_city}")

        await self.db.execute(
            update(User)
            .where(User.id == user_id)
            .values(**update_values)
        )
        if commit:
            await self.db.commit()
        return {"user_id": str(user_id), "preferred_store": name or best_store_id_1c, "share": share}
    
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
            
            PACKAGING_THRESHOLD = 500
            store_ids = {p.store_id_1c for p in purchases if p.store_id_1c}
            valid_store_ids: set = set()
            if store_ids:
                stores_rs = await self.db.execute(
                    select(Store.external_id).where(Store.external_id.in_(list(store_ids)))
                )
                valid_store_ids = {row[0] for row in stores_rs.fetchall() if row and row[0]}

            def _is_transfer(ph: PurchaseHistory) -> bool:
                try:
                    name = (ph.product_name or "").lower()
                    if "перенос" in name:
                        return True
                    meta = ph.sync_metadata or {}
                    rt = str(meta.get("Recorder_Type", "")).lower()
                    if "вводначальныхостатков" in rt or "перенос" in rt:
                        return True
                except Exception:
                    pass
                return False

            def _dedup_key(p: PurchaseHistory):
                doc = p.document_id_1c or ""
                prod = p.product_id_1c or (p.product_article or "")
                ts = p.purchase_date.isoformat() if p.purchase_date else ""
                amt = p.total_amount or 0
                return (doc, prod, ts, amt)

            filtered = [p for p in purchases if (p.total_amount or 0) >= PACKAGING_THRESHOLD]
            dedup_map: Dict[Any, PurchaseHistory] = {}
            for p in filtered:
                key = _dedup_key(p)
                cur = dedup_map.get(key)
                prefer_new = False
                if cur is None:
                    prefer_new = True
                else:
                    if (not getattr(cur, "store_id_1c", None)) and getattr(p, "store_id_1c", None):
                        prefer_new = True
                if prefer_new:
                    dedup_map[key] = p
            deduped = [
                p for p in dedup_map.values()
                if (p.store_id_1c and p.store_id_1c in valid_store_ids) or _is_transfer(p)
            ]

            frequency = len(deduped)
            monetary = sum((p.total_amount or 0) for p in deduped)
            
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
