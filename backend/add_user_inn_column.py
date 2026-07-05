"""
Скрипт для добавления поля users.inn (ИНН) и уникального индекса по нему
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus, urlparse

env_path = Path(__file__).parent.parent / ".env"
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


def apply() -> bool:
    sql = """
    ALTER TABLE users
        ADD COLUMN IF NOT EXISTS inn VARCHAR(12);

    CREATE UNIQUE INDEX IF NOT EXISTS ux_users_inn_not_null
        ON users (inn)
        WHERE inn IS NOT NULL;

    CREATE INDEX IF NOT EXISTS ix_users_inn
        ON users (inn);
    """
    try:
        engine = create_engine(get_db_url(), echo=False)
        with engine.connect() as conn:
            conn.execute(text(sql))
            conn.commit()
        return True
    except Exception as e:
        print(f"Ошибка при добавлении users.inn: {e}")
        return False


if __name__ == "__main__":
    ok = apply()
    sys.exit(0 if ok else 1)

