"""
Скрипт для добавления уникального индекса в таблицу purchase_history
для предотвращения дубликатов на уровне БД.

Уникальный индекс по комбинации:
- user_id
- document_id_1c (с учетом NULL)
- product_id_1c (с учетом NULL)
- purchase_date
"""
import asyncio
from sqlalchemy import text
from app.database.connection import AsyncSessionLocal

async def add_unique_index():
    """Добавляет уникальный индекс для предотвращения дубликатов"""
    async with AsyncSessionLocal() as session:
        try:
            print("=" * 80)
            print("ДОБАВЛЕНИЕ УНИКАЛЬНОГО ИНДЕКСА В purchase_history")
            print("=" * 80)
            
            # Проверяем, существует ли уже индекс
            check_index_sql = text("""
                SELECT indexname 
                FROM pg_indexes 
                WHERE tablename = 'purchase_history' 
                AND indexname = 'uq_purchase_history_unique'
            """)
            
            result = await session.execute(check_index_sql)
            existing_index = result.scalar_one_or_none()
            
            if existing_index:
                print("[INFO] Старый индекс найден. Удаляем для пересоздания с DATE()...")
                drop_index_sql = text("DROP INDEX IF EXISTS uq_purchase_history_unique")
                await session.execute(drop_index_sql)
                await session.commit()
            
            print("\nПроверка на существующие дубликаты...")
            # Сначала удаляем дубликаты (оставляем самую раннюю запись по created_at)
            delete_duplicates_sql = text("""
                DELETE FROM purchase_history
                WHERE id NOT IN (
                    SELECT DISTINCT ON (
                        user_id,
                        COALESCE(document_id_1c, ''),
                        COALESCE(product_id_1c, ''),
                        CAST(purchase_date AT TIME ZONE 'UTC' AS DATE)
                    ) id
                    FROM purchase_history
                    ORDER BY 
                        user_id,
                        COALESCE(document_id_1c, ''),
                        COALESCE(product_id_1c, ''),
                        CAST(purchase_date AT TIME ZONE 'UTC' AS DATE),
                        created_at ASC
                )
            """)
            
            result = await session.execute(delete_duplicates_sql)
            deleted_count = result.rowcount
            if deleted_count > 0:
                print(f"[INFO] Удалено {deleted_count} дубликатов перед созданием индекса")
            else:
                print("[INFO] Дубликатов не найдено")
            
            await session.commit()
            
            print("\nСоздание уникального индекса...")
            print("Индекс использует DATE(purchase_date) для сравнения только по дню (без времени)")
            
            # Создаем уникальный индекс с использованием COALESCE для NULL значений
            # PostgreSQL требует, чтобы NULL значения обрабатывались специально
            # Используем CAST для сравнения только по дню, без учета времени
            # CAST является IMMUTABLE для timestamp with time zone
            create_index_sql = text("""
                CREATE UNIQUE INDEX uq_purchase_history_unique 
                ON purchase_history (
                    user_id,
                    COALESCE(document_id_1c, ''),
                    COALESCE(product_id_1c, ''),
                    CAST(purchase_date AT TIME ZONE 'UTC' AS DATE)
                )
            """)
            
            await session.execute(create_index_sql)
            await session.commit()
            
            print("[OK] Уникальный индекс успешно создан!")
            print("\nТеперь дубликаты будут предотвращаться на уровне БД.")
            print("Проверка по дате выполняется только в пределах одного дня (без учета времени).")
            print("=" * 80)
            
        except Exception as e:
            await session.rollback()
            print(f"[ERROR] Ошибка при создании индекса: {e}")
            raise


async def remove_unique_index():
    """Удаляет уникальный индекс (если нужно)"""
    async with AsyncSessionLocal() as session:
        try:
            print("Удаление уникального индекса...")
            
            drop_index_sql = text("DROP INDEX IF EXISTS uq_purchase_history_unique")
            await session.execute(drop_index_sql)
            await session.commit()
            
            print("[OK] Индекс удален!")
            
        except Exception as e:
            await session.rollback()
            print(f"❌ Ошибка при удалении индекса: {e}")
            raise


async def main():
    """Главная функция"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Управление уникальным индексом purchase_history')
    parser.add_argument('--remove', action='store_true', help='Удалить индекс')
    
    args = parser.parse_args()
    
    if args.remove:
        await remove_unique_index()
    else:
        await add_unique_index()


if __name__ == "__main__":
    asyncio.run(main())
