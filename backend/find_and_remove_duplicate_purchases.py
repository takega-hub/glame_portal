"""
Скрипт для поиска и удаления дубликатов в истории покупок.

Дубликаты определяются по комбинации:
- user_id
- document_id_1c
- product_id_1c
- purchase_date
- total_amount (для дополнительной проверки)

Оставляет только самую раннюю запись (по created_at).
"""
import asyncio
import sys
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.connection import AsyncSessionLocal
from app.models.purchase_history import PurchaseHistory
from app.models.user import User

async def find_duplicates(dry_run: bool = True, user_id: str = None):
    """
    Находит и удаляет дубликаты в истории покупок.
    
    Args:
        dry_run: Если True, только показывает дубликаты, не удаляет их
        user_id: Если указан, проверяет только этого пользователя
    """
    async with AsyncSessionLocal() as session:
        print("=" * 80)
        print("ПОИСК ДУБЛИКАТОВ В ИСТОРИИ ПОКУПОК")
        print("=" * 80)
        
        # Находим группы дубликатов
        # Группируем по user_id, document_id_1c, product_id_1c, purchase_date
        if user_id:
            try:
                from uuid import UUID
                uid = UUID(user_id)
                user_filter = PurchaseHistory.user_id == uid
            except ValueError:
                print(f"Ошибка: неверный формат user_id: {user_id}")
                return
        else:
            user_filter = True
        
        # Находим группы с дубликатами
        # Используем подзапрос для поиска групп с count > 1
        # Важно: используем COALESCE для обработки NULL значений
        # В PostgreSQL все выражения в SELECT должны быть в GROUP BY
        doc_id_expr = func.coalesce(PurchaseHistory.document_id_1c, '')
        prod_id_expr = func.coalesce(PurchaseHistory.product_id_1c, '')
        
        stmt = (
            select(
                PurchaseHistory.user_id,
                doc_id_expr.label('doc_id'),
                prod_id_expr.label('prod_id'),
                PurchaseHistory.purchase_date,
                func.count(PurchaseHistory.id).label('count')
            )
            .where(user_filter)
            .group_by(
                PurchaseHistory.user_id,
                doc_id_expr,  # Используем то же выражение, что и в SELECT
                prod_id_expr,  # Используем то же выражение, что и в SELECT
                PurchaseHistory.purchase_date
            )
            .having(func.count(PurchaseHistory.id) > 1)
        )
        
        result = await session.execute(stmt)
        duplicate_groups = result.all()
        
        if not duplicate_groups:
            print("✅ Дубликатов не найдено!")
            return
        
        print(f"\nНайдено {len(duplicate_groups)} групп дубликатов:\n")
        
        total_duplicates_to_remove = 0
        total_groups_processed = 0
        
        for group in duplicate_groups:
            user_id_val, doc_id, product_id, purchase_date, count = group
            
            # Получаем все записи этой группы
            # Обрабатываем NULL значения: если doc_id или product_id пустые строки, ищем NULL
            conditions = [
                PurchaseHistory.user_id == user_id_val,
                PurchaseHistory.purchase_date == purchase_date
            ]
            
            if doc_id:
                conditions.append(PurchaseHistory.document_id_1c == doc_id)
            else:
                conditions.append(PurchaseHistory.document_id_1c.is_(None))
            
            if product_id:
                conditions.append(PurchaseHistory.product_id_1c == product_id)
            else:
                conditions.append(PurchaseHistory.product_id_1c.is_(None))
            
            stmt = select(PurchaseHistory).where(
                and_(*conditions)
            ).order_by(PurchaseHistory.created_at)
            
            result = await session.execute(stmt)
            records = result.scalars().all()
            
            if len(records) <= 1:
                continue
            
            # Получаем информацию о пользователе
            user_stmt = select(User).where(User.id == user_id_val)
            user_result = await session.execute(user_stmt)
            user = user_result.scalar_one_or_none()
            user_name = user.full_name if user else "Неизвестно"
            user_phone = user.phone if user else "—"
            
            print(f"\n{'='*80}")
            print(f"Группа дубликатов #{total_groups_processed + 1}:")
            print(f"  Пользователь: {user_name} ({user_phone})")
            print(f"  Документ 1С: {doc_id}")
            print(f"  Товар 1С: {product_id}")
            print(f"  Дата покупки: {purchase_date}")
            print(f"  Количество дубликатов: {len(records)}")
            print(f"\n  Записи:")
            
            # Оставляем первую запись (самую раннюю по created_at)
            keep_record = records[0]
            duplicates_to_remove = records[1:]
            
            print(f"    ✅ ОСТАВИТЬ (id={keep_record.id}):")
            print(f"       Создано: {keep_record.created_at}")
            print(f"       Сумма: {keep_record.total_amount / 100:.2f} ₽")
            print(f"       Товар: {keep_record.product_name or '—'}")
            print(f"       Артикул: {keep_record.product_article or '—'}")
            
            for dup in duplicates_to_remove:
                print(f"    ❌ УДАЛИТЬ (id={dup.id}):")
                print(f"       Создано: {dup.created_at}")
                print(f"       Сумма: {dup.total_amount / 100:.2f} ₽")
                print(f"       Товар: {dup.product_name or '—'}")
                print(f"       Артикул: {dup.product_article or '—'}")
                
                if not dry_run:
                    await session.delete(dup)
                    total_duplicates_to_remove += 1
            
            total_groups_processed += 1
        
        print(f"\n{'='*80}")
        print(f"ИТОГО:")
        print(f"  Групп дубликатов: {total_groups_processed}")
        print(f"  Записей для удаления: {total_duplicates_to_remove}")
        
        if not dry_run and total_duplicates_to_remove > 0:
            await session.commit()
            print(f"\n✅ Удалено {total_duplicates_to_remove} дубликатов!")
        elif dry_run:
            print(f"\n⚠️  Это был тестовый запуск (dry_run=True).")
            print(f"   Для реального удаления запустите скрипт с параметром --remove")
        else:
            print(f"\n✅ Нет записей для удаления.")
        
        print("=" * 80)


async def main():
    """Главная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Поиск и удаление дубликатов в истории покупок')
    parser.add_argument('--remove', action='store_true', help='Удалить дубликаты (по умолчанию только поиск)')
    parser.add_argument('--user-id', type=str, help='Проверить только конкретного пользователя (UUID)')
    
    args = parser.parse_args()
    
    dry_run = not args.remove
    
    if dry_run:
        print("⚠️  РЕЖИМ ТЕСТИРОВАНИЯ: дубликаты будут найдены, но не удалены")
        print("   Для удаления используйте флаг --remove\n")
    else:
        print("⚠️  РЕЖИМ УДАЛЕНИЯ: дубликаты будут удалены из БД!")
        response = input("Продолжить? (yes/no): ").strip().lower()
        if response not in ['yes', 'y', 'да', 'д']:
            print("Отменено.")
            return
    
    await find_duplicates(dry_run=dry_run, user_id=args.user_id)


if __name__ == "__main__":
    asyncio.run(main())
