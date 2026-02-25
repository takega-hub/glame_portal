"""
Скрипт для исправления сумм покупок в базе данных.
Удаляет все записи покупок и пересинхронизирует их с правильными суммами.
"""
import asyncio
import sys
import os

# Для Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Добавляем путь к backend
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import delete, select, func
from app.database.connection import AsyncSessionLocal
from app.models.purchase_history import PurchaseHistory
from app.models.user import User
from app.services.customer_sync_service import CustomerSyncService


async def fix_all_purchases():
    """Удаляет все покупки и пересинхронизирует их"""
    print("=" * 60)
    print("ИСПРАВЛЕНИЕ СУММ ПОКУПОК")
    print("=" * 60)
    
    async with AsyncSessionLocal() as session:
        # 1. Считаем текущее состояние
        count_stmt = select(func.count(PurchaseHistory.id))
        result = await session.execute(count_stmt)
        total_before = result.scalar() or 0
        print(f"\nТекущее количество записей покупок: {total_before}")
        
        # 2. Удаляем все записи покупок
        print("\n[1/4] Удаление старых записей покупок...")
        delete_stmt = delete(PurchaseHistory)
        await session.execute(delete_stmt)
        await session.commit()
        print("   [OK] Все записи удалены")
        
        # 3. Сбрасываем метрики пользователей
        print("\n[2/4] Сброс метрик пользователей...")
        users_stmt = select(User).where(User.is_customer == True)
        result = await session.execute(users_stmt)
        users = result.scalars().all()
        
        for user in users:
            user.total_purchases = 0
            user.total_spent = 0
            user.average_check = None
            user.last_purchase_date = None
            user.purchase_preferences = None
        
        await session.commit()
        print(f"   [OK] Сброшены метрики для {len(users)} покупателей")
        
        # 4. Синхронизация
        print("\n[3/4] Синхронизация начального ввода...")
        sync_service = CustomerSyncService(session)
        
        try:
            initial_stats = await sync_service.sync_initial_balances()
            print(f"   [OK] Начальный ввод: создано={initial_stats.get('created', 0)}, обновлено={initial_stats.get('updated', 0)}")
        except Exception as e:
            print(f"   [ERROR] Ошибка синхронизации начального ввода: {e}")
        
        print("\n[4/4] Синхронизация истории покупок...")
        try:
            purchase_stats = await sync_service.sync_purchase_history(days=730)  # 2 года
            print(f"   [OK] Покупки: создано={purchase_stats.get('created', 0)}, обновлено={purchase_stats.get('updated', 0)}")
        except Exception as e:
            print(f"   [ERROR] Ошибка синхронизации покупок: {e}")
        
        # 5. Проверяем результат
        count_stmt = select(func.count(PurchaseHistory.id))
        result = await session.execute(count_stmt)
        total_after = result.scalar() or 0
        
        print("\n" + "=" * 60)
        print("РЕЗУЛЬТАТ:")
        print(f"   Записей до: {total_before}")
        print(f"   Записей после: {total_after}")
        print("=" * 60)


async def fix_single_user(phone: str):
    """Исправляет покупки для одного пользователя"""
    print(f"\nИсправление покупок для пользователя: {phone}")
    
    async with AsyncSessionLocal() as session:
        # Находим пользователя
        stmt = select(User).where(User.phone == phone)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            print(f"[ERROR] Пользователь с телефоном {phone} не найден")
            return
        
        print(f"   Найден: {user.full_name} (ID: {user.id})")
        
        # Удаляем его покупки
        delete_stmt = delete(PurchaseHistory).where(PurchaseHistory.user_id == user.id)
        await session.execute(delete_stmt)
        await session.commit()
        print("   [OK] Покупки удалены")
        
        # Сбрасываем метрики
        user.total_purchases = 0
        user.total_spent = 0
        user.average_check = None
        user.last_purchase_date = None
        user.purchase_preferences = None
        await session.commit()
        print("   [OK] Метрики сброшены")
        
        # Синхронизируем
        sync_service = CustomerSyncService(session)
        
        print("   Синхронизация начального ввода...")
        try:
            initial_stats = await sync_service.sync_initial_balances(user_id=user.id)
            print(f"   [OK] Начальный ввод: создано={initial_stats.get('created', 0)}")
        except Exception as e:
            print(f"   [ERROR] {e}")
        
        print("   Синхронизация покупок...")
        try:
            purchase_stats = await sync_service.sync_purchase_history(user_id=user.id, days=730)
            print(f"   [OK] Покупки: создано={purchase_stats.get('created', 0)}")
        except Exception as e:
            print(f"   [ERROR] {e}")
        
        # Обновляем данные пользователя
        await session.refresh(user)
        print(f"\n   Итого покупок: {user.total_purchases}")
        print(f"   Общая сумма: {(user.total_spent or 0) / 100:,.2f} руб")
        print(f"   Баллы: {user.loyalty_points}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        phone = sys.argv[1]
        asyncio.run(fix_single_user(phone))
    else:
        print("Использование:")
        print("  python fix_purchase_amounts.py           # Исправить всех")
        print("  python fix_purchase_amounts.py 79788398435  # Исправить одного")
        print("\nЗапуск исправления для всех...")
        asyncio.run(fix_all_purchases())
