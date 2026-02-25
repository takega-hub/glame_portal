"""
Скрипт для поиска дубликатов по товару и артикулу (более мягкий критерий).

Находит записи с одинаковыми:
- user_id
- product_article (артикул)
- product_name (название товара)
- total_amount (сумма)
- purchase_date (дата, без учета времени)

Это помогает найти дубликаты, которые могут иметь разные document_id_1c или время.
"""
import asyncio
import sys
from sqlalchemy import select, func, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.database.connection import AsyncSessionLocal
from app.models.purchase_history import PurchaseHistory
from app.models.user import User

async def find_duplicates_by_product(dry_run: bool = True, user_id: str = None):
    """
    Находит дубликаты по товару и артикулу.
    
    Args:
        dry_run: Если True, только показывает дубликаты, не удаляет их
        user_id: Если указан, проверяет только этого пользователя
    """
    async with AsyncSessionLocal() as session:
        print("=" * 80)
        print("ПОИСК ДУБЛИКАТОВ ПО ТОВАРУ И АРТИКУЛУ")
        print("=" * 80)
        
        # Находим группы дубликатов
        # Группируем по user_id, product_article, product_name, total_amount, DATE(purchase_date)
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
        
        # Находим группы с дубликатами по товару
        # Используем DATE() для игнорирования времени
        stmt = text("""
            SELECT 
                user_id,
                product_article,
                product_name,
                total_amount,
                DATE(purchase_date) as purchase_day,
                COUNT(*) as count
            FROM purchase_history
            WHERE product_article IS NOT NULL 
                AND product_article != ''
                AND total_amount >= 500
            GROUP BY 
                user_id,
                product_article,
                product_name,
                total_amount,
                DATE(purchase_date)
            HAVING COUNT(*) > 1
            ORDER BY count DESC, user_id
        """)
        
        result = await session.execute(stmt)
        duplicate_groups = result.all()
        
        if not duplicate_groups:
            print("\n[OK] Дубликатов не найдено!")
            return
        
        print(f"\nНайдено {len(duplicate_groups)} групп дубликатов:\n")
        
        total_duplicates_to_remove = 0
        total_groups_processed = 0
        
        for group in duplicate_groups:
            user_id_val, product_article, product_name, total_amount, purchase_day, count = group
            
            # Получаем все записи этой группы
            stmt = select(PurchaseHistory).where(
                and_(
                    PurchaseHistory.user_id == user_id_val,
                    PurchaseHistory.product_article == product_article,
                    PurchaseHistory.total_amount == total_amount,
                    func.date(PurchaseHistory.purchase_date) == purchase_day
                )
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
            print(f"  Товар: {product_name or '—'}")
            print(f"  Артикул: {product_article}")
            print(f"  Дата покупки: {purchase_day}")
            print(f"  Сумма: {total_amount / 100:.2f} Р")
            print(f"  Количество дубликатов: {len(records)}")
            print(f"\n  Записи:")
            
            # Оставляем первую запись (самую раннюю по created_at)
            keep_record = records[0]
            duplicates_to_remove = records[1:]
            
            print(f"    [KEEP] id={keep_record.id}:")
            print(f"       Создано: {keep_record.created_at}")
            print(f"       Дата покупки: {keep_record.purchase_date}")
            print(f"       Документ 1С: {keep_record.document_id_1c or '—'}")
            
            for dup in duplicates_to_remove:
                print(f"    [DELETE] id={dup.id}:")
                print(f"       Создано: {dup.created_at}")
                print(f"       Дата покупки: {dup.purchase_date}")
                print(f"       Документ 1С: {dup.document_id_1c or '—'}")
                
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
            print(f"\n[OK] Удалено {total_duplicates_to_remove} дубликатов!")
        elif dry_run:
            print(f"\n[INFO] Это был тестовый запуск (dry_run=True).")
            print(f"   Для реального удаления запустите скрипт с параметром --remove")
        else:
            print(f"\n[OK] Нет записей для удаления.")
        
        print("=" * 80)


async def main():
    """Главная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Поиск дубликатов по товару и артикулу')
    parser.add_argument('--remove', action='store_true', help='Удалить дубликаты (по умолчанию только поиск)')
    parser.add_argument('--user-id', type=str, help='Проверить только конкретного пользователя (UUID)')
    
    args = parser.parse_args()
    
    dry_run = not args.remove
    
    if dry_run:
        print("[INFO] РЕЖИМ ТЕСТИРОВАНИЯ: дубликаты будут найдены, но не удалены")
        print("   Для удаления используйте флаг --remove\n")
    else:
        print("[WARNING] РЕЖИМ УДАЛЕНИЯ: дубликаты будут удалены из БД!")
        response = input("Продолжить? (yes/no): ").strip().lower()
        if response not in ['yes', 'y', 'да', 'д']:
            print("Отменено.")
            return
    
    await find_duplicates_by_product(dry_run=dry_run, user_id=args.user_id)


if __name__ == "__main__":
    asyncio.run(main())
