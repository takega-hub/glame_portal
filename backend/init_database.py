"""
Скрипт для инициализации базы данных с нуля
Выполняет все миграции и создает необходимые таблицы
"""
import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv, find_dotenv

# Добавляем путь к backend
backend_path = Path(__file__).parent
sys.path.insert(0, str(backend_path))

# Загружаем переменные окружения
load_dotenv(find_dotenv(usecwd=True), override=False)

import asyncpg
from alembic.config import Config
from alembic import command


def get_db_config():
    """Получение конфигурации БД из переменных окружения"""
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "5433"))
    DB_USER = os.getenv("DB_USER", "glame_user")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "glame_password")
    DB_NAME = os.getenv("DB_NAME", "glame_db")
    
    return {
        "host": DB_HOST,
        "port": DB_PORT,
        "user": DB_USER,
        "password": DB_PASSWORD,
        "database": DB_NAME
    }


async def check_postgres_connection():
    """Проверка подключения к PostgreSQL"""
    config = get_db_config()
    
    try:
        # Пробуем подключиться к postgres для создания БД
        conn = await asyncpg.connect(
            host=config["host"],
            port=config["port"],
            user=config["user"],
            password=config["password"],
            database="postgres"  # Подключаемся к системной БД
        )
        await conn.close()
        print("✓ Подключение к PostgreSQL успешно")
        return True
    except Exception as e:
        print(f"✗ Ошибка подключения к PostgreSQL: {e}")
        print(f"  Убедитесь, что PostgreSQL запущен и доступен на {config['host']}:{config['port']}")
        return False


async def create_database_if_not_exists():
    """Создание базы данных если её нет"""
    config = get_db_config()
    
    try:
        # Подключаемся к postgres для создания БД
        conn = await asyncpg.connect(
            host=config["host"],
            port=config["port"],
            user=config["user"],
            password=config["password"],
            database="postgres"
        )
        
        # Проверяем, существует ли БД
        db_exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            config["database"]
        )
        
        if not db_exists:
            print(f"Создание базы данных {config['database']}...")
            await conn.execute(
                f'CREATE DATABASE "{config["database"]}"'
            )
            print(f"✓ База данных {config['database']} создана")
        else:
            print(f"✓ База данных {config['database']} уже существует")
        
        await conn.close()
        return True
    except Exception as e:
        print(f"✗ Ошибка при создании базы данных: {e}")
        return False


def run_migrations():
    """Выполнение миграций Alembic"""
    # Путь к alembic.ini
    alembic_ini_path = backend_path / "alembic.ini"
    
    if not alembic_ini_path.exists():
        print(f"✗ Файл alembic.ini не найден: {alembic_ini_path}")
        return False
    
    try:
        print("Выполнение миграций...")
        alembic_cfg = Config(str(alembic_ini_path))
        
        # Устанавливаем рабочую директорию
        os.chdir(str(backend_path))
        
        # Выполняем миграции до последней версии
        command.upgrade(alembic_cfg, "head")
        
        print("✓ Миграции выполнены успешно")
        return True
    except Exception as e:
        print(f"✗ Ошибка при выполнении миграций: {e}")
        import traceback
        traceback.print_exc()
        return False


async def verify_tables():
    """Проверка создания таблиц"""
    config = get_db_config()
    
    try:
        conn = await asyncpg.connect(
            host=config["host"],
            port=config["port"],
            user=config["user"],
            password=config["password"],
            database=config["database"]
        )
        
        # Получаем список таблиц
        tables = await conn.fetch("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public'
            ORDER BY tablename
        """)
        
        table_names = [t['tablename'] for t in tables]
        
        expected_tables = [
            "users",
            "products",
            "looks",
            "sessions",
            "analytics_events",
            "knowledge_documents",
            "content_plans",
            "content_items",
            "content_publications",
            "app_settings"
        ]
        
        print("\nСозданные таблицы:")
        for table in table_names:
            marker = "✓" if table in expected_tables else "?"
            print(f"  {marker} {table}")
        
        missing_tables = [t for t in expected_tables if t not in table_names]
        if missing_tables:
            print(f"\n⚠ Отсутствующие таблицы: {', '.join(missing_tables)}")
        else:
            print("\n✓ Все ожидаемые таблицы созданы")
        
        await conn.close()
        return len(missing_tables) == 0
    except Exception as e:
        print(f"✗ Ошибка при проверке таблиц: {e}")
        return False


async def main():
    """Основная функция инициализации"""
    print("=" * 60)
    print("Инициализация базы данных GLAME AI Platform")
    print("=" * 60)
    print()
    
    # Проверка подключения
    if not await check_postgres_connection():
        print("\n❌ Не удалось подключиться к PostgreSQL")
        print("   Запустите: docker-compose -f infra/docker-compose.yml up -d postgres")
        return False
    
    # Создание БД
    if not await create_database_if_not_exists():
        print("\n❌ Не удалось создать базу данных")
        return False
    
    # Выполнение миграций
    if not run_migrations():
        print("\n❌ Не удалось выполнить миграции")
        return False
    
    # Проверка таблиц
    if not await verify_tables():
        print("\n⚠ Некоторые таблицы отсутствуют")
    
    print("\n" + "=" * 60)
    print("✓ Инициализация базы данных завершена успешно!")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    # Настройка event loop для Windows
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
