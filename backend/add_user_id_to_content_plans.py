"""
Скрипт для добавления поля user_id в таблицу content_plans
Используется когда миграции Alembic не работают
"""
import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import quote_plus
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from dotenv import load_dotenv, find_dotenv

# На Windows устанавливаем правильную политику event loop
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

# Загружаем .env из корня проекта
load_dotenv(find_dotenv(usecwd=True), override=False)


def get_db_url():
    """Получение URL базы данных из переменных окружения"""
    DATABASE_URL = os.getenv("DATABASE_URL")
    
    if DATABASE_URL:
        # Приводим к формату postgresql+psycopg://
        if DATABASE_URL.startswith("postgresql+asyncpg://"):
            DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
        elif DATABASE_URL.startswith("postgresql://"):
            DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
        elif DATABASE_URL.startswith("postgres://"):
            DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
        return DATABASE_URL
    
    # Если DATABASE_URL не задан, формируем из отдельных переменных
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5433")
    DB_USER = os.getenv("DB_USER", "glame_user")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "glame_password")
    DB_NAME = os.getenv("DB_NAME", "glame_db")
    
    # Экранируем пароль для URL
    DB_PASSWORD_ESCAPED = quote_plus(DB_PASSWORD)
    
    return f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD_ESCAPED}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


async def check_column_exists(conn, table_name: str, column_name: str) -> bool:
    """Проверка существования колонки в таблице"""
    query = text("""
        SELECT EXISTS (
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_name = :table_name 
            AND column_name = :column_name
        )
    """)
    result = await conn.execute(query, {"table_name": table_name, "column_name": column_name})
    return result.scalar()


async def check_index_exists(conn, index_name: str) -> bool:
    """Проверка существования индекса"""
    query = text("""
        SELECT EXISTS (
            SELECT 1 
            FROM pg_indexes 
            WHERE indexname = :index_name
        )
    """)
    result = await conn.execute(query, {"index_name": index_name})
    return result.scalar()


async def check_constraint_exists(conn, constraint_name: str) -> bool:
    """Проверка существования ограничения (constraint)"""
    query = text("""
        SELECT EXISTS (
            SELECT 1 
            FROM information_schema.table_constraints 
            WHERE constraint_name = :constraint_name
        )
    """)
    result = await conn.execute(query, {"constraint_name": constraint_name})
    return result.scalar()


async def main():
    db_url = get_db_url()
    # Скрываем пароль в выводе
    display_url = db_url.split('@')[-1] if '@' in db_url else db_url
    print(f"Подключение к БД: {display_url}")
    
    engine = create_async_engine(db_url, echo=False)
    
    try:
        async with engine.begin() as conn:
            # Проверяем существование таблицы content_plans
            table_exists_query = text("""
                SELECT EXISTS (
                    SELECT 1 
                    FROM information_schema.tables 
                    WHERE table_name = 'content_plans'
                )
            """)
            table_exists = await conn.execute(table_exists_query)
            if not table_exists.scalar():
                print("ОШИБКА: Таблица 'content_plans' не существует!")
                print("Сначала создайте таблицы: python backend/create_content_tables.py")
                return
            
            print("✓ Таблица 'content_plans' существует")
            
            # Проверяем существование колонки user_id
            if await check_column_exists(conn, "content_plans", "user_id"):
                print("✓ Колонка 'user_id' уже существует")
            else:
                print("Добавление колонки 'user_id'...")
                await conn.execute(text("""
                    ALTER TABLE content_plans 
                    ADD COLUMN user_id UUID
                """))
                print("✓ Колонка 'user_id' добавлена")
            
            # Проверяем существование индекса
            index_name = "ix_content_plans_user_id"
            if await check_index_exists(conn, index_name):
                print(f"✓ Индекс '{index_name}' уже существует")
            else:
                print(f"Создание индекса '{index_name}'...")
                await conn.execute(text(f"""
                    CREATE INDEX {index_name} ON content_plans(user_id)
                """))
                print(f"✓ Индекс '{index_name}' создан")
            
            # Проверяем существование внешнего ключа
            constraint_name = "fk_content_plans_user_id"
            if await check_constraint_exists(conn, constraint_name):
                print(f"✓ Внешний ключ '{constraint_name}' уже существует")
            else:
                # Проверяем существование таблицы users
                users_exists = await conn.execute(text("""
                    SELECT EXISTS (
                        SELECT 1 
                        FROM information_schema.tables 
                        WHERE table_name = 'users'
                    )
                """))
                
                if not users_exists.scalar():
                    print("⚠ ПРЕДУПРЕЖДЕНИЕ: Таблица 'users' не существует!")
                    print("Внешний ключ не будет создан. Создайте таблицу 'users' сначала.")
                else:
                    print(f"Создание внешнего ключа '{constraint_name}'...")
                    await conn.execute(text(f"""
                        ALTER TABLE content_plans 
                        ADD CONSTRAINT {constraint_name} 
                        FOREIGN KEY (user_id) 
                        REFERENCES users(id) 
                        ON DELETE CASCADE
                    """))
                    print(f"✓ Внешний ключ '{constraint_name}' создан")
            
            await conn.commit()
            print("\n✅ Все операции выполнены успешно!")
            
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
