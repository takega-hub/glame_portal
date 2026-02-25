from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
import os
import sys
import asyncio
from urllib.parse import urlparse, urlunparse
from dotenv import load_dotenv, find_dotenv

# На Windows иногда полезно фиксировать event loop policy для async IO
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

# Важно: при запуске из разных директорий load_dotenv() может не найти корневой .env
load_dotenv(find_dotenv(usecwd=True), override=False)

# Получаем DATABASE_URL из переменных окружения
DATABASE_URL = os.getenv("DATABASE_URL")

# Если DATABASE_URL не задан, используем значения по умолчанию
if not DATABASE_URL:
    DB_HOST = os.getenv("DB_HOST", "localhost")
    # В docker-compose Postgres проброшен на 5433 (чтобы не конфликтовать с локальным postgres.exe)
    DB_PORT = os.getenv("DB_PORT", "5433")
    DB_USER = os.getenv("DB_USER", "glame_user")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "glame_password")
    DB_NAME = os.getenv("DB_NAME", "glame_db")
    
    # Формируем async URL через psycopg3 (postgresql+psycopg://)
    DATABASE_URL = f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
else:
    # Если DATABASE_URL задан, приводим драйвер к psycopg3
    raw = DATABASE_URL
    if raw.startswith("postgresql+asyncpg://"):
        raw = raw.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    elif raw.startswith("postgresql://"):
        raw = raw.replace("postgresql://", "postgresql+psycopg://", 1)
    elif raw.startswith("postgres://"):
        raw = raw.replace("postgres://", "postgresql+psycopg://", 1)

    # Авто-фикс для Windows: если в .env остался localhost:5432, а контейнер теперь на 5433
    # (на 5432 часто висит локальный postgres.exe и мы подключаемся не туда).
    try:
        p = urlparse(raw)
        if p.hostname in ("localhost", "127.0.0.1") and (p.port == 5432 or p.port is None):
            # Меняем только порт; остальное оставляем как есть
            netloc = p.netloc
            # netloc может быть user:pass@host:port или user:pass@host
            if "@" in netloc:
                creds, hostpart = netloc.split("@", 1)
                host_only = hostpart.split(":", 1)[0]
                netloc = f"{creds}@{host_only}:5433"
            else:
                host_only = netloc.split(":", 1)[0]
                netloc = f"{host_only}:5433"
            raw = urlunparse((p.scheme, netloc, p.path, p.params, p.query, p.fragment))
    except Exception:
        pass

    DATABASE_URL = raw

# Создаем async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,  # Уменьшаем размер pool для Windows
    max_overflow=10,
)

# Создаем async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

Base = declarative_base()


async def get_db():
    """Dependency для получения async DB сессии"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
