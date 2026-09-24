"""
Применяет SQL-миграцию операционного CRM-раздела продавца.

Запуск из корня проекта:
    python backend/apply_crm_tasks_migration.py

Скрипт читает DATABASE_URL или DB_* из .env, не печатает пароль/токен и
использует backend/sql/create_crm_tasks.sql как единственный источник DDL.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import quote_plus, urlparse

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = Path(__file__).resolve().parent
SQL_PATH = BACKEND_ROOT / "sql" / "create_crm_tasks.sql"


def load_environment() -> None:
    for env_path in (PROJECT_ROOT / ".env", BACKEND_ROOT / ".env"):
        if env_path.exists():
            load_dotenv(env_path, override=False)


def get_db_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        parsed = urlparse(database_url)
        username = quote_plus(parsed.username or "glame_user")
        pwd = quote_plus(parsed.password or os.getenv("DB_PASSWORD", ""))
        hostname = parsed.hostname or "localhost"
        port = parsed.port or 5433
        database = parsed.path.lstrip("/") or "glame_db"
        return f"postgresql+psycopg://{username}:{pwd}@{hostname}:{port}/{database}"

    username = quote_plus(os.getenv("DB_USER", "glame_user"))
    pwd = quote_plus(os.getenv("DB_PASSWORD", ""))
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5433")
    database = os.getenv("DB_NAME", "glame_db")
    return f"postgresql+psycopg://{username}:{pwd}@{host}:{port}/{database}"


def redacted_db_target(db_url: str) -> str:
    parsed = urlparse(db_url.replace("postgresql+psycopg://", "postgresql://", 1))
    return f"{parsed.scheme}:***@{parsed.hostname}:{parsed.port}{parsed.path}"


def apply_crm_tasks_migration() -> bool:
    load_environment()
    if not SQL_PATH.exists():
        print(f"❌ SQL файл не найден: {SQL_PATH}")
        return False

    sql = SQL_PATH.read_text(encoding="utf-8")
    db_url = get_db_url()
    print(f"Подключение к БД: {redacted_db_target(db_url)}")

    try:
        engine = create_engine(db_url, echo=False)
        with engine.connect() as conn:
            conn.execute(text(sql))
            conn.commit()
        print("✅ CRM таблицы crm_tasks и crm_task_events готовы")
        return True
    except Exception as exc:
        print(f"❌ Ошибка применения CRM миграции: {exc}")
        return False


if __name__ == "__main__":
    sys.exit(0 if apply_crm_tasks_migration() else 1)
