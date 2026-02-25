#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для создания таблиц в БД напрямую, обходя проблему с кодировкой psycopg2
"""
import sys
import os

# Устанавливаем кодировку для stdout/stderr
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Добавляем текущую директорию в путь
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import URL
import psycopg2
from app.models import (
    User,
    Product,
    Look,
    Session,
    AnalyticsEvent,
    ContentPlan,
    ContentItem,
    ContentPublication,
)
from app.database.connection import Base

# Используем параметры подключения напрямую, минуя строку DSN
# Это обходит проблему с кодировкой в psycopg2 на Windows
def make_connection():
    """Создает подключение с параметрами напрямую (берёт значения из ENV)"""
    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "5433"))
    user = os.getenv("DB_USER", "glame_user")
    password = os.getenv("DB_PASSWORD", "glame_password")
    database = os.getenv("DB_NAME", "glame_db")

    return psycopg2.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        client_encoding='utf8'
    )

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5433"))
DB_USER = os.getenv("DB_USER", "glame_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "glame_password")
DB_NAME = os.getenv("DB_NAME", "glame_db")

# Используем URL объект (значения должны быть ASCII‑only)
db_url = URL.create(
    drivername="postgresql+psycopg2",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME,
)

engine = create_engine(
    db_url,
    echo=True,
    creator=make_connection,
    connect_args={"client_encoding": "utf8"}
)

try:
    print("Creating tables...")
    Base.metadata.create_all(engine)
    print("✓ Tables created successfully!")
    
    # Проверяем созданные таблицы
    with engine.connect() as conn:
        result = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"))
        tables = [row[0] for row in result]
        print(f"✓ Created tables: {', '.join(tables)}")
        
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
