"""
Сервис программы лояльности
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from app.models.user import User
from app.models.loyalty_transaction import LoyaltyTransaction
from app.models.purchase_history import PurchaseHistory

logger = logging.getLogger(__name__)


class LoyaltyService:
    """Сервис программы лояльности"""

    LOYALTY_LEVELS = [
        {
            "name": "Бонусная 3%",
            "bonus_percent": 3,
            "min_total": 0,
            "max_total": 50000,
            "condition": "Сумма покупок за все время меньше 50 000 руб.",
            "benefits": ["3% баллами от суммы покупки"],
        },
        {
            "name": "Бонусная 5%",
            "bonus_percent": 5,
            "min_total": 50000,
            "max_total": 150000,
            "condition": "Сумма покупок за все время от 50 000 до 149 999 руб.",
            "benefits": ["5% баллами от суммы покупки"],
        },
        {
            "name": "Бонусная 7%",
            "bonus_percent": 7,
            "min_total": 150000,
            "max_total": 300000,
            "condition": "Сумма покупок за все время от 150 000 до 299 999 руб.",
            "benefits": ["7% баллами от суммы покупки"],
        },
        {
            "name": "Бонусная 10%",
            "bonus_percent": 10,
            "min_total": 300000,
            "max_total": None,
            "condition": "Сумма покупок за все время от 300 000 руб.",
            "benefits": ["10% баллами от суммы покупки"],
        },
    ]
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def calculate_points_for_purchase(
        self, 
        purchase_amount: int, 
        user: User
    ) -> int:
        """
        Расчет баллов за покупку по программе "Бонусная".
        purchase_amount и user.total_spent хранятся в копейках, баллы считаем в рублях.
        """
        bonus_percent = self.get_bonus_percent_for_total(user.total_spent or 0)
        return int((purchase_amount / 100) * (bonus_percent / 100))

    def get_bonus_percent_for_total(self, total_spent_kopecks: int) -> int:
        """Процент начисления по сумме покупок за все время."""
        total_spent_rub = max(0, int(total_spent_kopecks or 0)) / 100
        for level in reversed(self.LOYALTY_LEVELS):
            if total_spent_rub >= float(level["min_total"]):
                return int(level["bonus_percent"])
        return int(self.LOYALTY_LEVELS[0]["bonus_percent"])
    
    async def earn_points(
        self,
        user_id: UUID,
        points: int,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None,
        related_purchase_id: Optional[UUID] = None,
        source: str = "platform",
        source_id: Optional[str] = None,
        expires_days: Optional[int] = None
    ) -> LoyaltyTransaction:
        """
        Начисление баллов
        """
        try:
            # Получаем пользователя
            stmt = select(User).where(User.id == user_id)
            result = await self.db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                raise ValueError(f"Пользователь {user_id} не найден")
            
            # Вычисляем новый баланс
            new_balance = user.loyalty_points + points
            
            # Определяем срок действия
            expires_at = None
            if expires_days:
                expires_at = datetime.utcnow() + timedelta(days=expires_days)
            
            # Создаем транзакцию
            transaction = LoyaltyTransaction(
                user_id=user_id,
                transaction_type="earn",
                points=points,
                balance_after=new_balance,
                reason=reason,
                description=metadata.get("description") if metadata else None,
                related_purchase_id=related_purchase_id,
                source=source,
                source_id=source_id,
                expires_at=expires_at
            )
            
            # Обновляем баланс пользователя
            user.loyalty_points = new_balance
            
            self.db.add(transaction)
            await self.db.commit()
            
            logger.info(f"Начислено {points} баллов пользователю {user_id}, баланс: {new_balance}")
            
            return transaction
            
        except Exception as e:
            logger.error(f"Ошибка начисления баллов: {e}")
            await self.db.rollback()
            raise
    
    async def spend_points(
        self,
        user_id: UUID,
        points: int,
        reason: str,
        description: Optional[str] = None
    ) -> LoyaltyTransaction:
        """
        Списание баллов
        """
        try:
            # Получаем пользователя
            stmt = select(User).where(User.id == user_id)
            result = await self.db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                raise ValueError(f"Пользователь {user_id} не найден")
            
            if user.loyalty_points < points:
                raise ValueError(f"Недостаточно баллов. Текущий баланс: {user.loyalty_points}, требуется: {points}")
            
            # Вычисляем новый баланс
            new_balance = user.loyalty_points - points
            
            # Создаем транзакцию
            transaction = LoyaltyTransaction(
                user_id=user_id,
                transaction_type="spend",
                points=-points,
                balance_after=new_balance,
                reason=reason,
                description=description,
                source="platform"
            )
            
            # Обновляем баланс пользователя
            user.loyalty_points = new_balance
            
            self.db.add(transaction)
            await self.db.commit()
            
            logger.info(f"Списано {points} баллов у пользователя {user_id}, баланс: {new_balance}")
            
            return transaction
            
        except Exception as e:
            logger.error(f"Ошибка списания баллов: {e}")
            await self.db.rollback()
            raise
    
    async def get_loyalty_balance(self, user_id: UUID) -> int:
        """
        Получение баланса баллов
        """
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            return 0
        
        return user.loyalty_points
    
    async def get_loyalty_transactions(
        self,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0
    ) -> List[LoyaltyTransaction]:
        """
        История транзакций
        """
        stmt = (
            select(LoyaltyTransaction)
            .where(LoyaltyTransaction.user_id == user_id)
            .order_by(desc(LoyaltyTransaction.created_at))
            .limit(limit)
            .offset(offset)
        )
        
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    def get_loyalty_program_info(self) -> Dict[str, Any]:
        """
        Описание программы лояльности
        """
        return {
            "name": "Бонусная",
            "description": "Начисляем бонусные баллы за покупки по уровню клиента. Чем больше сумма покупок за все время, тем выше процент начисления.",
            "rules": {
                "earn": {
                    "base_rate": "3% баллами до 50 000 руб. покупок за все время",
                    "level_50000": "5% баллами от 50 000 до 149 999 руб.",
                    "level_150000": "7% баллами от 150 000 до 299 999 руб.",
                    "level_300000": "10% баллами от 300 000 руб."
                },
                "spend": {
                    "rate": "1 балл = 1 рубль скидки",
                    "card": "Действует при предъявлении бонусной карты"
                },
                "expiration": {
                    "default": "Срок действия бонусов определяется правилами 1С"
                }
            },
            "levels": self.LOYALTY_LEVELS
        }

    def get_loyalty_level_progress(self, total_spent_kopecks: int) -> Dict[str, Any]:
        """
        Расчет текущего уровня и остатка суммы покупок до следующего уровня.
        total_spent_kopecks хранится в БД в копейках, наружу отдаем рубли.
        """
        total_spent_rub = max(0, int(total_spent_kopecks or 0)) / 100
        current_level = self.LOYALTY_LEVELS[0]
        next_level = None

        for idx, level in enumerate(self.LOYALTY_LEVELS):
            min_total = float(level["min_total"])
            max_total = level["max_total"]
            if total_spent_rub >= min_total and (max_total is None or total_spent_rub < float(max_total)):
                current_level = level
                if idx + 1 < len(self.LOYALTY_LEVELS):
                    next_level = self.LOYALTY_LEVELS[idx + 1]
                break

        if next_level:
            next_min_total = float(next_level["min_total"])
            current_min_total = float(current_level["min_total"])
            remaining_total = max(0.0, next_min_total - total_spent_rub)
            span = max(1.0, next_min_total - current_min_total)
            progress = (total_spent_rub - current_min_total) / span
        else:
            remaining_total = 0.0
            progress = 1.0

        return {
            "current_total": total_spent_rub,
            "current_level": current_level,
            "next_level": next_level,
            "remaining_total": remaining_total,
            "progress": max(0.0, min(1.0, progress)),
        }
    
    async def expire_old_points(self) -> Dict[str, Any]:
        """
        Автоматическое списание просроченных баллов (cron job)
        """
        stats = {
            "expired": 0,
            "points_expired": 0,
            "errors": 0
        }
        
        try:
            # Находим все транзакции с истекающими баллами
            now = datetime.utcnow()
            stmt = (
                select(LoyaltyTransaction)
                .where(
                    and_(
                        LoyaltyTransaction.transaction_type == "earn",
                        LoyaltyTransaction.expires_at.isnot(None),
                        LoyaltyTransaction.expires_at <= now
                    )
                )
            )
            
            result = await self.db.execute(stmt)
            expired_transactions = result.scalars().all()
            
            # Группируем по пользователям
            user_expired_points = {}
            for transaction in expired_transactions:
                user_id = transaction.user_id
                if user_id not in user_expired_points:
                    user_expired_points[user_id] = 0
                user_expired_points[user_id] += transaction.points
            
            # Списываем просроченные баллы
            for user_id, points in user_expired_points.items():
                try:
                    await self.spend_points(
                        user_id=user_id,
                        points=points,
                        reason="expire",
                        description=f"Списание просроченных баллов"
                    )
                    stats["expired"] += 1
                    stats["points_expired"] += points
                except Exception as e:
                    logger.error(f"Ошибка списания просроченных баллов для пользователя {user_id}: {e}")
                    stats["errors"] += 1
            
            await self.db.commit()
            
        except Exception as e:
            logger.error(f"Ошибка при списании просроченных баллов: {e}")
            await self.db.rollback()
            raise
        
        return stats
