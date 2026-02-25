"""
Скрипт для добавления недостающих колонок в таблицу analytics_events
Используется когда миграции Alembic не работают
"""
import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import quote_plus
import asyncpg
from dotenv import load_dotenv, find_dotenv

# На Windows устанавливаем правильную политику event loop
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

# Загружаем .env из корня проекта
load_dotenv(find_dotenv(usecwd=True), override=False)


async def check_column_exists(conn, table_name: str, column_name: str) -> bool:
    """Проверка существования колонки в таблице"""
    query = """
        SELECT EXISTS (
            SELECT 1 
            FROM information_schema.columns 
            WHERE table_name = $1 
            AND column_name = $2
        )
    """
    result = await conn.fetchval(query, table_name, column_name)
    return result


async def check_index_exists(conn, index_name: str) -> bool:
    """Проверка существования индекса"""
    query = """
        SELECT EXISTS (
            SELECT 1 
            FROM pg_indexes 
            WHERE indexname = $1
        )
    """
    result = await conn.fetchval(query, index_name)
    return result


async def check_constraint_exists(conn, constraint_name: str) -> bool:
    """Проверка существования ограничения (constraint)"""
    query = """
        SELECT EXISTS (
            SELECT 1 
            FROM information_schema.table_constraints 
            WHERE constraint_name = $1
        )
    """
    result = await conn.fetchval(query, constraint_name)
    return result


async def main():
    # Параметры подключения
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "5433"))
    DB_USER = os.getenv("DB_USER", "glame_user")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "glame_password")
    DB_NAME = os.getenv("DB_NAME", "glame_db")
    
    print(f"Подключение к БД: {DB_HOST}:{DB_PORT}/{DB_NAME} как {DB_USER}")
    
    try:
        conn = await asyncpg.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        
        print("[OK] Подключение установлено")
        
        # Проверяем существование таблицы analytics_events
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 
                FROM information_schema.tables 
                WHERE table_name = 'analytics_events'
            )
        """)
        
        if not table_exists:
            print("[ERROR] Таблица 'analytics_events' не существует!")
            await conn.close()
            return
        
        print("[OK] Таблица 'analytics_events' существует")
        
        # Список колонок для добавления
        columns_to_add = [
            {
                "name": "user_id",
                "type": "UUID",
                "nullable": True,
                "index": True,
                "foreign_key": "users(id)"
            },
            {
                "name": "product_id",
                "type": "UUID",
                "nullable": True,
                "index": True,
                "foreign_key": "products(id)"
            },
            {
                "name": "look_id",
                "type": "UUID",
                "nullable": True,
                "index": True,
                "foreign_key": "looks(id)"
            },
            {
                "name": "content_item_id",
                "type": "UUID",
                "nullable": True,
                "index": True,
                "foreign_key": "content_items(id)"
            },
            {
                "name": "channel",
                "type": "VARCHAR(64)",
                "nullable": True,
                "index": True,
                "foreign_key": None
            },
            {
                "name": "utm_source",
                "type": "VARCHAR(255)",
                "nullable": True,
                "index": False,
                "foreign_key": None
            },
            {
                "name": "utm_medium",
                "type": "VARCHAR(255)",
                "nullable": True,
                "index": False,
                "foreign_key": None
            },
            {
                "name": "utm_campaign",
                "type": "VARCHAR(255)",
                "nullable": True,
                "index": False,
                "foreign_key": None
            }
        ]
        
        # Добавляем колонки
        for col in columns_to_add:
            col_name = col["name"]
            col_type = col["type"]
            nullable = "NULL" if col["nullable"] else "NOT NULL"
            
            if await check_column_exists(conn, "analytics_events", col_name):
                print(f"✓ Колонка '{col_name}' уже существует")
            else:
                print(f"Добавление колонки '{col_name}'...")
                await conn.execute(f"""
                    ALTER TABLE analytics_events 
                    ADD COLUMN {col_name} {col_type} {nullable}
                """)
                print(f"[OK] Колонка '{col_name}' добавлена")
            
            # Создаем индекс если нужно
            if col.get("index"):
                index_name = f"ix_analytics_events_{col_name}"
                if await check_index_exists(conn, index_name):
                    print(f"[OK] Индекс '{index_name}' уже существует")
                else:
                    print(f"Создание индекса '{index_name}'...")
                    await conn.execute(f"""
                        CREATE INDEX {index_name} ON analytics_events({col_name})
                    """)
                    print(f"✓ Индекс '{index_name}' создан")
            
            # Создаем внешний ключ если нужно
            if col.get("foreign_key"):
                fk_name = f"fk_analytics_events_{col_name}"
                # Проверяем существование целевой таблицы
                target_table = col["foreign_key"].split("(")[0]
                target_exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT 1 
                        FROM information_schema.tables 
                        WHERE table_name = $1
                    )
                """, target_table)
                
                if not target_exists:
                    print(f"⚠ ПРЕДУПРЕЖДЕНИЕ: Таблица '{target_table}' не существует, внешний ключ не будет создан")
                elif await check_constraint_exists(conn, fk_name):
                    print(f"✓ Внешний ключ '{fk_name}' уже существует")
                else:
                    print(f"Создание внешнего ключа '{fk_name}'...")
                    await conn.execute(f"""
                        ALTER TABLE analytics_events 
                        ADD CONSTRAINT {fk_name} 
                        FOREIGN KEY ({col_name}) 
                        REFERENCES {col['foreign_key']} 
                        ON DELETE SET NULL
                    """)
                    print(f"✓ Внешний ключ '{fk_name}' создан")
        
        # Создаем составные индексы
        composite_indexes = [
            {
                "name": "ix_analytics_events_user_timestamp",
                "columns": ["user_id", "timestamp"]
            },
            {
                "name": "ix_analytics_events_type_timestamp",
                "columns": ["event_type", "timestamp"]
            },
            {
                "name": "ix_analytics_events_channel_timestamp",
                "columns": ["channel", "timestamp"]
            }
        ]
        
        for idx in composite_indexes:
            idx_name = idx["name"]
            if await check_index_exists(conn, idx_name):
                print(f"✓ Составной индекс '{idx_name}' уже существует")
            else:
                # Проверяем, что все колонки существуют
                all_exist = True
                for col in idx["columns"]:
                    if not await check_column_exists(conn, "analytics_events", col):
                        print(f"⚠ Колонка '{col}' не существует, индекс '{idx_name}' не будет создан")
                        all_exist = False
                        break
                
                if all_exist:
                    print(f"Создание составного индекса '{idx_name}'...")
                    cols_str = ", ".join(idx["columns"])
                    await conn.execute(f"""
                        CREATE INDEX {idx_name} ON analytics_events({cols_str})
                    """)
                    print(f"✓ Составной индекс '{idx_name}' создан")
        
        print("\n✅ Все операции выполнены успешно!")
        
        await conn.close()
        
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
