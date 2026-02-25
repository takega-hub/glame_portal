from logging.config import fileConfig
from sqlalchemy import engine_from_config, create_engine
from sqlalchemy import pool
from alembic import context
import os
import sys
from urllib.parse import quote_plus, urlparse, urlunparse
from dotenv import load_dotenv

# Добавляем путь к backend
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../backend'))

# Загружаем .env из корня проекта
env_path = os.path.join(os.path.dirname(__file__), '../../.env')
if os.path.exists(env_path):
    # Загружаем с явным указанием кодировки и обработкой ошибок
    try:
        load_dotenv(env_path, encoding='utf-8', override=False)
    except Exception as e:
        print(f"Warning: Error loading .env file: {e}")
        # Пробуем загрузить без указания кодировки
        try:
            load_dotenv(env_path, override=False)
        except:
            pass
else:
    try:
        load_dotenv(encoding='utf-8')
    except:
        load_dotenv()

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
from app.database.connection import Base
from app.models import (
    User, Product, Look, Session, AnalyticsEvent, AnalyticsMetric, WebsiteVisit, Store, StoreVisit,
    KnowledgeDocument, ContentPlan, ContentItem, ContentPublication, AppSetting, MarketingCampaign
)
from app.models.catalog_section import CatalogSection

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py
def safe_getenv(key, default=None):
    """Безопасное получение переменной окружения с обработкой кодировки"""
    try:
        value = os.getenv(key, default)
        if value is None:
            return default
        # Если это bytes, декодируем
        if isinstance(value, bytes):
            value = value.decode('utf-8', errors='replace')
        # Преобразуем в строку и очищаем
        value = str(value).strip()
        # Убираем BOM и невидимые символы
        value = value.strip('\ufeff').strip('\x00')
        return value
    except Exception:
        return default

def build_database_url():
    """Построение DATABASE_URL с правильным кодированием компонентов"""
    # Получаем компоненты подключения
    DB_HOST = safe_getenv("DB_HOST") or safe_getenv("DATABASE_HOST") or "localhost"
    # В проекте локальный docker postgres обычно проброшен на 5433 (чтобы не конфликтовать с локальным postgres.exe на 5432)
    DB_PORT = safe_getenv("DB_PORT") or safe_getenv("DATABASE_PORT") or "5433"
    DB_USER = safe_getenv("DB_USER") or safe_getenv("DATABASE_USER") or "glame_user"
    DB_PASSWORD = safe_getenv("DB_PASSWORD") or safe_getenv("DATABASE_PASSWORD") or "glame_password"
    DB_NAME = safe_getenv("DB_NAME") or safe_getenv("DATABASE_NAME") or "glame_db"
    
    # Пробуем получить DATABASE_URL целиком
    raw_url = safe_getenv("DATABASE_URL")
    
    if raw_url and raw_url.startswith('postgresql://'):
        # Если DATABASE_URL задан, парсим его и пересобираем с правильным кодированием
        try:
            # Декодируем URL если он в bytes
            if isinstance(raw_url, bytes):
                raw_url = raw_url.decode('utf-8', errors='replace')
            
            parsed = urlparse(raw_url)
            
            # Извлекаем компоненты с безопасной обработкой кодировки
            username = (parsed.username or DB_USER)
            password = (parsed.password or DB_PASSWORD)
            hostname = (parsed.hostname or DB_HOST)
            port = parsed.port or int(DB_PORT)
            database = (parsed.path.lstrip('/') or DB_NAME)
            
            # Убеждаемся, что все компоненты - строки в UTF-8
            if isinstance(username, bytes):
                username = username.decode('utf-8', errors='replace')
            if isinstance(password, bytes):
                password = password.decode('utf-8', errors='replace')
            if isinstance(hostname, bytes):
                hostname = hostname.decode('utf-8', errors='replace')
            if isinstance(database, bytes):
                database = database.decode('utf-8', errors='replace')
            
            # Правильно кодируем username и password (это критично!)
            username_encoded = quote_plus(str(username), safe='')
            password_encoded = quote_plus(str(password), safe='')
            
            # Формируем URL только из ASCII символов (psycopg3 — в образе нет psycopg2)
            database_url = f"postgresql+psycopg://{username_encoded}:{password_encoded}@{hostname}:{port}/{database}"
            
            # Финальная проверка - должен быть только ASCII
            database_url.encode('ascii')
            return database_url
        except UnicodeDecodeError as e:
            print(f"Warning: Unicode error parsing DATABASE_URL: {e}. Building from components.")
        except Exception as e:
            print(f"Warning: Error parsing DATABASE_URL: {e}. Building from components.")
    
    # Если DATABASE_URL не задан или невалидный, строим из компонентов
    try:
        # Убеждаемся, что все компоненты - строки
        DB_USER_str = str(DB_USER) if DB_USER else "glame_user"
        DB_PASSWORD_str = str(DB_PASSWORD) if DB_PASSWORD else "glame_password"
        DB_HOST_str = str(DB_HOST) if DB_HOST else "localhost"
        DB_NAME_str = str(DB_NAME) if DB_NAME else "glame_db"
        
        # Декодируем если это bytes
        if isinstance(DB_USER_str, bytes):
            DB_USER_str = DB_USER_str.decode('utf-8', errors='replace')
        if isinstance(DB_PASSWORD_str, bytes):
            DB_PASSWORD_str = DB_PASSWORD_str.decode('utf-8', errors='replace')
        if isinstance(DB_HOST_str, bytes):
            DB_HOST_str = DB_HOST_str.decode('utf-8', errors='replace')
        if isinstance(DB_NAME_str, bytes):
            DB_NAME_str = DB_NAME_str.decode('utf-8', errors='replace')
        
        # Кодируем компоненты для безопасной передачи
        username_encoded = quote_plus(DB_USER_str, safe='')
        password_encoded = quote_plus(DB_PASSWORD_str, safe='')
        
        # Формируем URL (psycopg3 — в образе нет psycopg2)
        database_url = f"postgresql+psycopg://{username_encoded}:{password_encoded}@{DB_HOST_str}:{DB_PORT}/{DB_NAME_str}"
        
        # Проверяем, что URL содержит только ASCII
        database_url.encode('ascii')
        return database_url
    except UnicodeDecodeError as e:
        print(f"Error: Unicode decode error building database URL: {e}")
        # Fallback на простой вариант
        return "postgresql+psycopg://glame_user:glame_password@localhost:5433/glame_db"
    except Exception as e:
        print(f"Error building database URL: {e}")
        # Fallback на простой вариант (psycopg3)
        return "postgresql+psycopg://glame_user:glame_password@localhost:5433/glame_db"

# Строим URL подключения
database_url = build_database_url()

# Отладочный вывод (скрываем пароль)
try:
    url_parts = database_url.split('@')
    if len(url_parts) > 1:
        print(f"Database connection: postgresql://***:***@{url_parts[1]}")
    else:
        print(f"Database URL built successfully")
except:
    pass

config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Упрощённый путь: используем уже собранный sqlalchemy.url из build_database_url()
    и стандартный engine_from_config. Это устраняет проблемы с кодировкой
    и вложенными asyncio.run().
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
