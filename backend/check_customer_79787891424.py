"""
Скрипт для проверки данных покупателя 79787891424
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.connection import AsyncSessionLocal
from app.models.user import User
from app.models.purchase_history import PurchaseHistory


async def check_customer(phone: str):
    """Проверка данных покупателя"""
    
    async with AsyncSessionLocal() as db:
        # 1. Находим покупателя по телефону
        stmt = select(User).where(User.phone == phone, User.is_customer == True)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            print(f'❌ Покупатель с телефоном {phone} не найден')
            return
        
        print("=" * 80)
        print(f"ПРОВЕРКА ДАННЫХ: {phone}")
        print("=" * 80)
        print()
        print(f"Покупатель: {user.full_name}")
        print(f"1C Customer ID: {user.customer_id_1c}")
        print(f"1C Discount Card ID: {user.discount_card_id_1c}")
        print()
        
        # 2. Проверяем текущее состояние
        print("Текущее состояние в БД:")
        print(f"  total_spent: {user.total_spent} коп ({user.total_spent / 100:.2f} руб)")
        print(f"  total_purchases: {user.total_purchases}")
        print(f"  last_purchase_date: {user.last_purchase_date}")
        print()
        
        # 3. Проверяем покупки в БД
        purchases_stmt = select(PurchaseHistory).where(PurchaseHistory.user_id == user.id).order_by(PurchaseHistory.purchase_date)
        purchases_result = await db.execute(purchases_stmt)
        purchases = purchases_result.scalars().all()
        
        print(f"Всего покупок в БД: {len(purchases)}")
        print()
        
        if purchases:
            print("Последние 5 покупок:")
            for p in purchases[-5:]:
                print(f"  {p.purchase_date} | {p.product_name or 'N/A':<40} | {p.total_amount / 100:.2f} руб")
            print()
            
            # Найти запись "Ввод начальных остатков"
            initial_balance = None
            for p in purchases:
                if p.product_name and 'Ввод начальных остатков' in p.product_name:
                    initial_balance = p
                    break
            
            if initial_balance:
                print("✅ Найдена запись \"Ввод начальных остатков\":")
                print(f"  Дата: {initial_balance.purchase_date}")
                print(f"  Документ: {initial_balance.document_id_1c}")
                print(f"  Сумма: {initial_balance.total_amount} коп ({initial_balance.total_amount / 100:.2f} руб)")
            else:
                print("❌ Запись \"Ввод начальных остатков\" НЕ найдена")
        else:
            print("❌ Покупок не найдено")
        
        print()
        print("=" * 80)


def main():
    phone = "79787891424"
    
    print()
    asyncio.run(check_customer(phone))


if __name__ == "__main__":
    main()
