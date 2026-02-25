"""
Скрипт для применения миграции content_plans таблиц
"""
import os
import sys
from pathlib import Path

# Добавляем путь к backend
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus, urlparse

# Загружаем переменные окружения
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

def get_db_url():
    """Получает URL подключения к БД"""
    DATABASE_URL = os.getenv("DATABASE_URL")
    
    if DATABASE_URL:
        # Парсим и пересобираем URL
        parsed = urlparse(DATABASE_URL)
        username = quote_plus(parsed.username or "glame_user")
        password = quote_plus(parsed.password or "glame_password")
        hostname = parsed.hostname or "localhost"
        port = parsed.port or 5433
        database = parsed.path.lstrip('/') or "glame_db"
        return f"postgresql+psycopg://{username}:{password}@{hostname}:{port}/{database}"
    
    # Используем значения по умолчанию
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5433")
    DB_USER = os.getenv("DB_USER", "glame_user")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "glame_password")
    DB_NAME = os.getenv("DB_NAME", "glame_db")
    
    username = quote_plus(DB_USER)
    password = quote_plus(DB_PASSWORD)
    return f"postgresql+psycopg://{username}:{password}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def create_content_tables():
    """Создает таблицы content_plans, content_items, content_publications"""
    
    sql = """
    -- Создание таблицы content_plans
    CREATE TABLE IF NOT EXISTS content_plans (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name VARCHAR(255),
        status VARCHAR(50) NOT NULL DEFAULT 'draft',
        start_date TIMESTAMP WITH TIME ZONE NOT NULL,
        end_date TIMESTAMP WITH TIME ZONE NOT NULL,
        timezone VARCHAR(64) NOT NULL DEFAULT 'Europe/Moscow',
        inputs JSONB,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE
    );

    -- Индексы для content_plans
    CREATE INDEX IF NOT EXISTS ix_content_plans_status ON content_plans(status);
    CREATE INDEX IF NOT EXISTS ix_content_plans_start_date ON content_plans(start_date);
    CREATE INDEX IF NOT EXISTS ix_content_plans_end_date ON content_plans(end_date);

    -- Создание таблицы content_items
    CREATE TABLE IF NOT EXISTS content_items (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        plan_id UUID NOT NULL REFERENCES content_plans(id),
        scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL,
        timezone VARCHAR(64) NOT NULL DEFAULT 'Europe/Moscow',
        channel VARCHAR(64) NOT NULL,
        content_type VARCHAR(64) NOT NULL DEFAULT 'post',
        topic VARCHAR(500),
        hook VARCHAR(500),
        cta VARCHAR(500),
        persona VARCHAR(500),
        cjm_stage VARCHAR(64),
        goal VARCHAR(500),
        spec JSONB,
        generated JSONB,
        generated_text TEXT,
        status VARCHAR(50) NOT NULL DEFAULT 'planned',
        published_at TIMESTAMP WITH TIME ZONE,
        publication_metadata JSONB,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE
    );

    -- Индексы для content_items
    CREATE INDEX IF NOT EXISTS ix_content_items_plan_id ON content_items(plan_id);
    CREATE INDEX IF NOT EXISTS ix_content_items_scheduled_at ON content_items(scheduled_at);
    CREATE INDEX IF NOT EXISTS ix_content_items_status ON content_items(status);
    CREATE INDEX IF NOT EXISTS ix_content_items_channel ON content_items(channel);

    -- Создание таблицы content_publications
    CREATE TABLE IF NOT EXISTS content_publications (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        item_id UUID NOT NULL REFERENCES content_items(id),
        provider VARCHAR(64) NOT NULL DEFAULT 'glame',
        status VARCHAR(50) NOT NULL DEFAULT 'created',
        external_id VARCHAR(255),
        request_payload JSONB,
        response_payload JSONB,
        error_message TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    -- Индексы для content_publications
    CREATE INDEX IF NOT EXISTS ix_content_publications_item_id ON content_publications(item_id);
    CREATE INDEX IF NOT EXISTS ix_content_publications_status ON content_publications(status);
    """
    
    db_url = get_db_url()
    print(f"Подключение к БД: {db_url.split('@')[1] if '@' in db_url else '***'}")
    
    try:
        engine = create_engine(db_url, echo=False)
        with engine.connect() as conn:
            # Выполняем SQL
            conn.execute(text(sql))
            conn.commit()
            print("✅ Таблицы content_plans, content_items, content_publications успешно созданы!")
            return True
    except Exception as e:
        print(f"❌ Ошибка при создании таблиц: {e}")
        return False

if __name__ == "__main__":
    success = create_content_tables()
    sys.exit(0 if success else 1)
