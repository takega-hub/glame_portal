"""
Скрипт для синхронизации схемы БД с моделями SQLAlchemy
Добавляет недостающие поля в таблицы вручную (без миграций Alembic)
"""
import asyncio
import sys
import os

# Исправление для Windows event loop
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Добавляем путь к модулям
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from typing import Optional
from sqlalchemy import text, inspect, MetaData, Table
from sqlalchemy.dialects.postgresql import UUID, VARCHAR, INTEGER, BOOLEAN, JSON, TIMESTAMP
from app.database.connection import engine, AsyncSessionLocal, Base
from app.models.user import User


async def check_column_exists(table_name: str, column_name: str) -> bool:
    """Проверка существования колонки в таблице"""
    async with AsyncSessionLocal() as session:
        query = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = :table_name 
            AND column_name = :column_name
        """)
        result = await session.execute(query, {"table_name": table_name, "column_name": column_name})
        return result.scalar_one_or_none() is not None


async def get_column_type(table_name: str, column_name: str) -> Optional[str]:
    """Получение типа колонки"""
    async with AsyncSessionLocal() as session:
        query = text("""
            SELECT data_type, character_maximum_length
            FROM information_schema.columns 
            WHERE table_name = :table_name 
            AND column_name = :column_name
        """)
        result = await session.execute(query, {"table_name": table_name, "column_name": column_name})
        row = result.fetchone()
        if row:
            data_type = row[0]
            max_length = row[1]
            if max_length:
                return f"{data_type}({max_length})"
            return data_type
        return None


async def add_column_if_not_exists(table_name: str, column_name: str, column_type: str, nullable: bool = True):
    """Добавление колонки, если она не существует"""
    exists = await check_column_exists(table_name, column_name)
    
    if exists:
        print(f"  [OK] Поле {column_name} уже существует")
        return False
    
    try:
        async with AsyncSessionLocal() as session:
            nullable_str = "NULL" if nullable else "NOT NULL"
            query = text(f"""
                ALTER TABLE {table_name} 
                ADD COLUMN {column_name} {column_type} {nullable_str}
            """)
            await session.execute(query)
            await session.commit()
            print(f"  [OK] Поле {column_name} успешно добавлено")
            return True
    except Exception as e:
        print(f"  [ERROR] Ошибка при добавлении поля {column_name}: {e}")
        return False


async def sync_users_table():
    """Синхронизация таблицы users с моделью User"""
    print("=" * 60)
    print("Синхронизация таблицы users")
    print("=" * 60)
    
    # Поля, которые нужно проверить/добавить
    # Формат: (имя_поля, тип_SQL, nullable)
    fields_to_check = [
        ("city", "VARCHAR(100)", True),
    ]
    
    added_count = 0
    for field_name, field_type, nullable in fields_to_check:
        print(f"\nПроверка поля: {field_name}")
        if await add_column_if_not_exists("users", field_name, field_type, nullable):
            added_count += 1
    
    print("\n" + "=" * 60)
    if added_count > 0:
        print(f"Добавлено полей: {added_count}")
    else:
        print("Все поля уже существуют")
    print("=" * 60)
    
    return added_count


async def main():
    """Основная функция"""
    try:
        print("\nНачало синхронизации схемы БД...")
        
        # Синхронизируем таблицу users
        await sync_users_table()
        
        print("\n" + "=" * 60)
        print("СИНХРОНИЗАЦИЯ ЗАВЕРШЕНА")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[ERROR] Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
