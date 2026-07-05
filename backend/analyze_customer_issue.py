"""
Диагностический отчет по расхождению данных о покупках покупателя 79787566405
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from uuid import UUID

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database.connection import AsyncSessionLocal
from app.models.user import User
from app.models.purchase_history import PurchaseHistory
from sqlalchemy import select, func, and_


async def analyze_customer_purchases(phone: str):
    """Анализ истории покупок покупателя"""
    async with AsyncSessionLocal() as db:
        # 1. Находим покупателя по телефону
        stmt = select(User).where(User.phone == phone, User.is_customer == True)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            print(f'❌ Покупатель с телефоном {phone} не найден')
            return
        
        print("=" * 80)
        print("ДИАГНОСТИЧЕСКИЙ ОТЧЕТ: Покупатель 79787566405")
        print("=" * 80)
        print()
        print(f"✅ Покупатель найден:")
        print(f"   ID: {user.id}")
        print(f"   Телефон: {user.phone}")
        print(f"   1C Customer ID: {user.customer_id_1c}")
        print(f"   1C Discount Card ID: {user.discount_card_id_1c}")
        print(f"   Полное имя: {user.full_name}")
        print(f"   Последняя покупка в БД: {user.last_purchase_date}")
        print(f"   Количество покупок: {user.total_purchases}")
        print(f"   Общая сумма: {user.total_spent}")
        print()
        
        # 2. Проверяем историю покупок в PurchaseHistory
        print("=" * 80)
        print("ИСТОРИЯ ПОКУПОК В БД (PurchaseHistory):")
        print("=" * 80)
        
        purchase_stmt = (
            select(PurchaseHistory)
            .where(PurchaseHistory.user_id == user.id)
            .order_by(PurchaseHistory.purchase_date.desc())
            .limit(50)
        )
        result = await db.execute(purchase_stmt)
        purchases = result.scalars().all()
        
        if not purchases:
            print('   ❌ Покупок не найдено')
        else:
            print(f'   Найдено {len(purchases)} записей в PurchaseHistory')
            print()
            print(f"   Последние 5 покупок:")
            for i, p in enumerate(purchases[:5], 1):
                print(f"   {i}. {p.purchase_date} | {p.document_id_1c or 'N/A'} | {p.product_id_1c or 'N/A'} | {p.total_amount} коп")
            
            last_purchase = purchases[0]
            print()
            print(f"   Последняя покупка в PurchaseHistory:")
            print(f"      Дата: {last_purchase.purchase_date}")
            print(f"      Документ 1С: {last_purchase.document_id_1c}")
            print(f"      Товар 1С: {last_purchase.product_id_1c}")
            print(f"      Сумма: {last_purchase.total_amount} коп")
        print()
        
        # 3. Анализ проблемы
        print("=" * 80)
        print("АНАЛИЗ ПРОБЛЕМЫ:")
        print("=" * 80)
        print()
        
        # Проверяем дату последней покупки
        if last_purchase.purchase_date:
            now = datetime.now(timezone.utc)
            days_since_last = (now - last_purchase.purchase_date).days
            print(f"📊 Последняя покупка была {days_since_last} дней назад ({last_purchase.purchase_date.date()})")
            print()
        
        # Проверяем, есть ли покупки в 1С после последней в БД
        print("🔍 Возможные причины расхождения:")
        print()
        print("1. Ограничение периода синхронизации:")
        print("   - По умолчанию синхронизируются покупки за последние 365 дней")
        print("   - Если покупки 30.04 и 10.03 были более 365 дней назад, они не попали в синхронизацию")
        print()
        print("2. Ошибка 1С OData API:")
        print("   - 1С Fresh возвращает ошибку 500 при использовании ORDER BY Period")
        print("   - Это предотвращает получение актуальных данных из 1С")
        print()
        print("3. Фильтрация 'ночных' отчетов:")
        print("   - Покупки с временем 20:00-05:00 и типом 'ОтчетОРозничныхПродажах' фильтруются")
        print("   - Это может приводить к пропуску некоторых покупок")
        print()
        
        # Проверка на дубликаты
        print("=" * 80)
        print("ПРОВЕРКА НА ДУБЛИКАТЫ:")
        print("=" * 80)
        
        # Группируем по document_id_1c + product_id_1c + DATE(purchase_date)
        duplicate_check = (
            select(
                PurchaseHistory.document_id_1c,
                PurchaseHistory.product_id_1c,
                func.date(PurchaseHistory.purchase_date).label('purchase_date'),
                func.count().label('count')
            )
            .where(PurchaseHistory.user_id == user.id)
            .group_by(
                PurchaseHistory.document_id_1c,
                PurchaseHistory.product_id_1c,
                func.date(PurchaseHistory.purchase_date)
            )
            .having(func.count() > 1)
        )
        result = await db.execute(duplicate_check)
        duplicates = result.all()
        
        if duplicates:
            print(f"⚠️  Найдено {len(duplicates)} дубликатов:")
            for doc_id, prod_id, p_date, cnt in duplicates[:5]:
                print(f"   - Документ: {doc_id}, Товар: {prod_id}, Дата: {p_date}, Кол-во: {cnt}")
        else:
            print("✅ Дубликатов не найдено")
        print()
        
        # Рекомендации
        print("=" * 80)
        print("РЕКОМЕНДАЦИИ:")
        print("=" * 80)
        print()
        print("1. Для ручного обновления данных:")
        print("   - Откройте карточку покупателя в админ-панели")
        print("   - Нажмите кнопку 'Синхронизировать' (sync=true)")
        print("   - Это обновит историю покупок за последние 730 дней (2 года)")
        print()
        print("2. Для исправления ошибки 1С OData:")
        print("   - Удален $orderby из запросов к 1С OData")
        print("   - Сортировка теперь выполняется на стороне приложения")
        print()
        print("3. Для полной синхронизации:")
        print("   - Используйте API /api/admin/customers/{user_id}?sync=true")
        print("   - Или запустите скрипт sync_purchase_history.py с параметром days=3650")
        print()


def main():
    phone = "79787566405"
    print()
    asyncio.run(analyze_customer_purchases(phone))


if __name__ == "__main__":
    main()
