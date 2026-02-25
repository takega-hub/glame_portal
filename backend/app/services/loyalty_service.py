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
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def calculate_points_for_purchase(
        self, 
        purchase_amount: int, 
        user: User
    ) -> int:
        """
        Расчет баллов за покупку
        Базовые правила из 1С (если есть в метаданных) + дополнительные множители GLAME
        """
        # Базовая ставка: 1% от покупки
        base_rate = 0.01
        points = int(purchase_amount * base_rate)
        
        # Множители GLAME
        multiplier = 1.0
        
        # x1.5 для VIP сегмента
        if user.customer_segment == 'VIP':
            multiplier *= 1.5
        
        # x1.2 если покупка > среднего чека на 50%
        if user.average_check and purchase_amount > user.average_check * 1.5:
            multiplier *= 1.2
        
        # x2 за день рождения (если есть поле birthday в preferences)
        if user.preferences and user.preferences.get("birthday"):
            try:
                birthday = datetime.fromisoformat(user.preferences["birthday"])
                today = datetime.utcnow()
                # Проверяем, что день рождения в течение недели
                if abs((today - birthday.replace(year=today.year)).days) <= 7:
                    multiplier *= 2.0
            except:
                pass
        
        return int(points * multiplier)
    
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
            "name": "Программа лояльности GLAME",
            "description": "Зарабатывайте баллы за каждую покупку и используйте их для получения скидок",
            "rules": {
                "earn": {
                    "base_rate": "1% от суммы покупки",
                    "vip_multiplier": "x1.5 для VIP клиентов",
                    "bonus_multiplier": "x1.2 при покупке выше среднего чека",
                    "birthday_multiplier": "x2 в день рождения"
                },
                "spend": {
                    "rate": "1 балл = 1 рубль скидки",
                    "min_points": "Минимум 100 баллов для использования"
                },
                "expiration": {
                    "default": "Баллы не сгорают",
                    "special": "Бонусные баллы могут иметь срок действия"
                }
            },
            "levels": [
                {
                    "name": "Новый клиент",
                    "min_purchases": 0,
                    "benefits": ["1% баллов от покупки"]
                },
                {
                    "name": "Активный клиент",
                    "min_purchases": 5,
                    "benefits": ["1% баллов от покупки", "Приоритетная поддержка"]
                },
                {
                    "name": "VIP клиент",
                    "min_purchases": 10,
                    "min_total": 50000,
                    "benefits": ["1.5% баллов от покупки", "Эксклюзивные предложения", "Персональный стилист"]
                }
            ]
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
