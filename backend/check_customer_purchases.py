"""
Скрипт для проверки истории покупок конкретного покупателя
"""
import asyncio
from sqlalchemy import select, and_, func
from app.database.connection import AsyncSessionLocal, get_db
from app.models.user import User
from app.models.purchase_history import PurchaseHistory


async def check_customer_purchases(phone: str):
    """Проверка истории покупок покупателя"""
    async with AsyncSessionLocal() as db:
        # Находим покупателя по телефону
        stmt = select(User).where(User.phone == phone, User.is_customer == True)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            print(f'❌ Покупатель с телефоном {phone} не найден')
            return
        
        print(f'=== Покупатель: {user.id} ===')
        print(f'Телефон: {user.phone}')
        print(f'1C Customer ID: {user.customer_id_1c}')
        print(f'1C Discount Card ID: {user.discount_card_id_1c}')
        print(f'Полное имя: {user.full_name}')
        
        # Получаем все покупки
        stmt = select(PurchaseHistory).where(PurchaseHistory.user_id == user.id).order_by(PurchaseHistory.purchase_date.desc())
        result = await db.execute(stmt)
        purchases = result.scalars().all()
        
        print(f'\n=== История покупок ({len(purchases)} записей) ===')
        for i, p in enumerate(purchases[:20]):  # Первые 20
            print(f'{i+1}. Дата: {p.purchase_date.date()}, Сумма: {p.total_amount} коп., Товар: {p.product_name or "N/A"}')
        
        # Проверяем уникальные даты
        if purchases:
            dates = [p.purchase_date.date() for p in purchases]
            unique_dates = set(dates)
            print(f'\nУникальных дат: {len(unique_dates)}')
            for d in sorted(unique_dates, reverse=True):
                count = dates.count(d)
                print(f'  {d}: {count} покупок')
            
            # Проверяем последние покупки
            print(f'\n=== Последние 5 покупок ===')
            for p in purchases[-5:]:
                print(f'Дата: {p.purchase_date.date()}, Сумма: {p.total_amount} коп., Товар: {p.product_name or "N/A"}')


if __name__ == "__main__":
    phone = "79787566405"
    asyncio.run(check_customer_purchases(phone))
