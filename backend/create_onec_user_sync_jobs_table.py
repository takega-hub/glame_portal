"""
Скрипт для создания таблицы onec_user_sync_jobs
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus, urlparse

env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


def get_db_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        parsed = urlparse(database_url)
        username = quote_plus(parsed.username or "glame_user")
        password = quote_plus(parsed.password or "glame_password")
        hostname = parsed.hostname or "localhost"
        port = parsed.port or 5433
        database = parsed.path.lstrip("/") or "glame_db"
        return f"postgresql+psycopg://{username}:{password}@{hostname}:{port}/{database}"

    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5433")
    db_user = os.getenv("DB_USER", "glame_user")
    db_password = os.getenv("DB_PASSWORD", "glame_password")
    db_name = os.getenv("DB_NAME", "glame_db")

    username = quote_plus(db_user)
    password = quote_plus(db_password)
    return f"postgresql+psycopg://{username}:{password}@{db_host}:{db_port}/{db_name}"


def create_onec_user_sync_jobs_table() -> bool:
    sql = """
    CREATE TABLE IF NOT EXISTS onec_user_sync_jobs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id),

        status VARCHAR(32) NOT NULL DEFAULT 'pending',
        attempts INTEGER NOT NULL DEFAULT 0,
        max_attempts INTEGER NOT NULL DEFAULT 8,

        next_attempt_at TIMESTAMP WITH TIME ZONE,
        last_attempt_at TIMESTAMP WITH TIME ZONE,

        last_error VARCHAR(2000),
        request_payload JSONB,
        response_payload JSONB,

        customer_id_1c VARCHAR(64),
        discount_card_id_1c VARCHAR(64),

        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE
    );

    CREATE INDEX IF NOT EXISTS ix_onec_user_sync_jobs_user_id ON onec_user_sync_jobs(user_id);
    CREATE INDEX IF NOT EXISTS ix_onec_user_sync_jobs_status ON onec_user_sync_jobs(status);
    CREATE INDEX IF NOT EXISTS ix_onec_user_sync_jobs_next_attempt_at ON onec_user_sync_jobs(next_attempt_at);
    CREATE INDEX IF NOT EXISTS ix_onec_user_sync_jobs_customer_id_1c ON onec_user_sync_jobs(customer_id_1c);
    CREATE INDEX IF NOT EXISTS ix_onec_user_sync_jobs_user_id_status ON onec_user_sync_jobs(user_id, status);
    """

    db_url = get_db_url()
    try:
        engine = create_engine(db_url, echo=False)
        with engine.connect() as conn:
            conn.execute(text(sql))
            conn.commit()
        return True
    except Exception as e:
        print(f"Ошибка при создании таблицы onec_user_sync_jobs: {e}")
        return False


if __name__ == "__main__":
    ok = create_onec_user_sync_jobs_table()
    sys.exit(0 if ok else 1)

