"""
Скрипт для проверки наличия покупателей в базе данных
"""
import asyncio
import sys
from sqlalchemy import select, func
from app.database.connection import AsyncSessionLocal
from app.models.user import User

async def check_customers():
    async with AsyncSessionLocal() as session:
        # Проверяем общее количество пользователей
        stmt = select(func.count(User.id))
        result = await session.execute(stmt)
        total_users = result.scalar()
        print(f"Всего пользователей в базе: {total_users}")
        
        # Проверяем количество покупателей
        is_customer_col = User.__table__.columns.get("is_customer")
        if is_customer_col is not None:
            stmt = select(func.count(User.id)).where(is_customer_col == True)
            result = await session.execute(stmt)
            total_customers = result.scalar()
            print(f"Покупателей (is_customer=True): {total_customers}")
        else:
            print("Колонка is_customer не найдена в таблице users")
        
        # Проверяем пользователей с discount_card_number
        discount_card_col = User.__table__.columns.get("discount_card_number")
        if discount_card_col is not None:
            stmt = select(func.count(User.id)).where(discount_card_col.isnot(None))
            result = await session.execute(stmt)
            customers_with_card = result.scalar()
            print(f"Пользователей с дисконтной картой: {customers_with_card}")
        
        # Получаем несколько примеров
        stmt = select(User).limit(5)
        result = await session.execute(stmt)
        users = result.scalars().all()
        
        print("\nПримеры пользователей:")
        for user in users:
            is_customer = getattr(user, "is_customer", None)
            phone = getattr(user, "phone", None)
            email = getattr(user, "email", None)
            full_name = getattr(user, "full_name", None)
            discount_card = getattr(user, "discount_card_number", None)
            print(f"  - ID: {user.id}, is_customer: {is_customer}, phone: {phone}, email: {email}, name: {full_name}, card: {discount_card}")

if __name__ == "__main__":
    asyncio.run(check_customers())
