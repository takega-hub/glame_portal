"""
Скрипт для восстановления записи "Ввод начальных остатков" для любого покупателя
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.connection import AsyncSessionLocal
from app.models.user import User
from app.models.purchase_history import PurchaseHistory
from sqlalchemy import select


async def restore_initial_balance(phone: str):
    """Восстановление записи 'Ввод начальных остатков' """
    
    async with AsyncSessionLocal() as db:
        # 1. Находим покупателя по телефону
        stmt = select(User).where(User.phone == phone, User.is_customer == True)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            print(f'❌ Покупатель с телефоном {phone} не найден')
            return
        
        print("=" * 80)
        print(f"ВОССТАНОВЛЕНИЕ 'ВВОДА НАЧАЛЬНЫХ ОСТАТКОВ': {phone}")
        print("=" * 80)
        print()
        print(f"Покупатель: {user.full_name}")
        print()
        
        # 2. Проверяем текущее состояние
        print("Текущее состояние:")
        print(f"  total_spent: {user.total_spent} коп ({user.total_spent / 100:.2f} руб)")
        print(f"  total_purchases: {user.total_purchases}")
        print()
        
        # 3. Проверяем, есть ли запись в БД
        purchases_stmt = select(PurchaseHistory).where(
            PurchaseHistory.user_id == user.id,
            PurchaseHistory.document_id_1c == "7f519352-bce5-11f0-9138-fa163e4cc04e"
        )
        purchases_result = await db.execute(purchases_stmt)
        existing = purchases_result.scalars().first()
        
        if existing:
            print("✅ Запись 'Ввод начальных остатков' уже есть в БД")
            print(f"  Дата: {existing.purchase_date}")
            print(f"  Сумма: {existing.total_amount} коп ({existing.total_amount / 100:.2f} руб)")
            return
        
        # 4. Создаем запись "Ввод начальных остатков"
        print("Создание записи 'Ввод начальных остатков'...")
        
        initial_balance = PurchaseHistory(
            id=uuid4(),
            user_id=user.id,
            document_id_1c="7f519352-bce5-11f0-9138-fa163e4cc04e",
            store_id_1c=None,
            product_id=None,
            product_id_1c="84190322-bb1c-11f0-836e-fa163e4cc04e",
            product_article=None,
            product_name="Ввод начальных остатков 1 от 08.11.2025",
            purchase_date=datetime(2025, 11, 8, 0, 0, 0, tzinfo=timezone.utc),
            quantity=1,
            price=23236000,  # 232,360 руб в копейках
            total_amount=23236000,  # 232,360 руб в копейках
            category=None,
            brand=None,
        )
        
        db.add(initial_balance)
        await db.commit()
        
        print("✅ Запись создана")
        print()
        
        # 5. Пересчитываем метрики
        print("Пересчёт метрик покупателя...")
        
        # Пересчитываем метрики
        purchases_stmt = select(PurchaseHistory).where(PurchaseHistory.user_id == user.id)
        purchases_result = await db.execute(purchases_stmt)
        purchases = purchases_result.scalars().all()
        
        total_purchases = len(purchases)
        total_spent = sum(p.total_amount for p in purchases)
        average_check = total_spent / total_purchases if total_purchases > 0 else 0
        
        last_purchase_date = max((p.purchase_date for p in purchases), default=None)
        
        user.total_purchases = total_purchases
        user.total_spent = total_spent
        user.average_check = int(average_check) if average_check else None
        user.last_purchase_date = last_purchase_date
        
        await db.commit()
        
        print(f"  Всего покупок: {total_purchases}")
        print(f"  Общая сумма: {total_spent / 100:.2f} руб")
        print(f"  Последняя покупка: {last_purchase_date}")
        
        print()
        print("=" * 80)
        print("✅ ВОССТАНОВЛЕНИЕ ЗАВЕРШЕНО")
        print("=" * 80)
        print()
        print("Восстановлена запись:")
        print("  Дата: 2025-11-08")
        print("  Документ: 7f519352-bce5-11f0-9138-fa163e4cc04e")
        print("  Сумма: 232,360.00 руб")


def main():
    # Телефон для проверки (можно изменить)
    phone = "79787891424"
    
    print()
    asyncio.run(restore_initial_balance(phone))


if __name__ == "__main__":
    main()
