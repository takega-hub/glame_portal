#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для создания таблиц системы покупателей
Создает все таблицы, включая новые для покупателей
Использует синхронный подход для совместимости
"""
import sys
import os

# Устанавливаем кодировку для Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Добавляем путь к app
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import URL
import psycopg2

# Импортируем все модели, чтобы они зарегистрировались в Base.metadata
from app.models import (
    User,
    Product,
    Look,
    Session,
    AnalyticsEvent,
    AnalyticsMetric,
    WebsiteVisit,
    Store,
    StoreVisit,
    KnowledgeDocument,
    ContentPlan,
    ContentItem,
    ContentPublication,
    AppSetting,
    MarketingCampaign,
    # Новые модели для покупателей
    PurchaseHistory,
    LoyaltyTransaction,
    SavedLook,
    CustomerSegment,
    UserSegment,
    CustomerMessage,
)

from app.database.connection import Base

# Используем параметры подключения напрямую, минуя строку DSN
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

# Используем URL объект
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
    print("=" * 60)
    print("Создание таблиц системы покупателей...")
    print("=" * 60)
    
    Base.metadata.create_all(engine)
    
    print("\n✓ Таблицы успешно созданы!")
    
    # Проверяем созданные таблицы
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name
        """))
        tables = [row[0] for row in result]
        
        print(f"\n✓ Всего таблиц в БД: {len(tables)}")
        print("\nНовые таблицы для покупателей:")
        new_tables = ['purchase_history', 'loyalty_transactions', 'saved_looks', 
                     'customer_segments', 'user_segments', 'customer_messages']
        for table in new_tables:
            if table in tables:
                print(f"  ✓ {table}")
            else:
                print(f"  ✗ {table} (не создана)")
        
        print("\n✓ Таблица users расширена полями для покупателей")
        print("=" * 60)
        
except Exception as e:
    print(f"\n✗ Ошибка при создании таблиц: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
