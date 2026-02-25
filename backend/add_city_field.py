"""
Скрипт для ручного добавления поля city в таблицу users
Используется, когда миграции Alembic недоступны
"""
import asyncio
import sys
import os

# Исправление для Windows event loop
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Добавляем путь к модулям
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text, inspect
from app.database.connection import engine, AsyncSessionLocal


async def check_column_exists(table_name: str, column_name: str) -> bool:
    """Проверка существования колонки в таблице"""
    async with AsyncSessionLocal() as session:
        # Для PostgreSQL
        query = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = :table_name 
            AND column_name = :column_name
        """)
        result = await session.execute(query, {"table_name": table_name, "column_name": column_name})
        return result.scalar_one_or_none() is not None


async def add_city_column():
    """Добавление поля city в таблицу users"""
    print("=" * 60)
    print("Добавление поля city в таблицу users")
    print("=" * 60)
    
    try:
        # Проверяем, существует ли колонка
        exists = await check_column_exists("users", "city")
        
        if exists:
            print("[OK] Поле city уже существует в таблице users")
            return
        
        print("[INFO] Поле city не найдено, добавляем...")
        
        async with AsyncSessionLocal() as session:
            # Добавляем колонку
            query = text("""
                ALTER TABLE users 
                ADD COLUMN city VARCHAR(100) NULL
            """)
            await session.execute(query)
            await session.commit()
            
            print("[OK] Поле city успешно добавлено в таблицу users")
            
            # Проверяем результат
            exists_after = await check_column_exists("users", "city")
            if exists_after:
                print("[OK] Подтверждено: поле city существует")
            else:
                print("[ERROR] Поле city не было добавлено")
                
    except Exception as e:
        print(f"[ERROR] Ошибка при добавлении поля city: {e}")
        import traceback
        traceback.print_exc()
        raise


async def main():
    """Основная функция"""
    try:
        await add_city_column()
        print("\n" + "=" * 60)
        print("ГОТОВО")
        print("=" * 60)
    except Exception as e:
        print(f"\n[ERROR] Критическая ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
