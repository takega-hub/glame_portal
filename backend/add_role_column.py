#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для добавления колонки role в таблицу users
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

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine.url import URL
import psycopg2

def make_connection():
    """Создает подключение с параметрами напрямую"""
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
    echo=False,
    creator=make_connection,
    connect_args={"client_encoding": "utf8"}
)

def add_role_column():
    """Добавление колонки role и других новых полей в таблицу users"""
    print("=" * 60)
    print("Добавление новых колонок в таблицу users")
    print("=" * 60)
    
    try:
        with engine.connect() as conn:
            # Проверяем существующие колонки
            inspector = inspect(engine)
            columns = [col['name'] for col in inspector.get_columns('users')]
            
            print(f"\nСуществующие колонки: {', '.join(columns)}")
            
            # Список колонок для добавления
            columns_to_add = [
                ("password_hash", "VARCHAR(255)"),  # Добавляем первым, так как может использоваться в других колонках
                ("role", "VARCHAR(50) DEFAULT 'customer'"),
                ("phone", "VARCHAR(20) UNIQUE"),
                ("discount_card_number", "VARCHAR(50) UNIQUE"),
                ("customer_id_1c", "VARCHAR(255)"),
                ("discount_card_id_1c", "VARCHAR(255)"),
                ("full_name", "VARCHAR(255)"),
                ("loyalty_points", "INTEGER DEFAULT 0 NOT NULL"),
                ("total_purchases", "INTEGER DEFAULT 0 NOT NULL"),
                ("total_spent", "INTEGER DEFAULT 0 NOT NULL"),
                ("average_check", "INTEGER"),
                ("last_purchase_date", "TIMESTAMP WITH TIME ZONE"),
                ("customer_segment", "VARCHAR(50)"),
                ("rfm_score", "JSONB"),
                ("purchase_preferences", "JSONB"),
                ("is_customer", "BOOLEAN DEFAULT false NOT NULL"),
                ("synced_at", "TIMESTAMP WITH TIME ZONE"),
            ]
            
            added_count = 0
            for col_name, col_def in columns_to_add:
                if col_name not in columns:
                    try:
                        print(f"Добавляем колонку: {col_name}...")
                        conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}"))
                        conn.commit()
                        print(f"  ✓ Колонка {col_name} добавлена")
                        added_count += 1
                    except Exception as e:
                        print(f"  ✗ Ошибка при добавлении {col_name}: {e}")
                        # Продолжаем с другими колонками
                else:
                    print(f"  - Колонка {col_name} уже существует")
            
            # Создаем индексы
            indexes_to_add = [
                ("ix_users_phone", "phone"),
                ("ix_users_discount_card", "discount_card_number"),
                ("ix_users_customer_id_1c", "customer_id_1c"),
                ("ix_users_is_customer", "is_customer"),
                ("ix_users_role", "role"),
            ]
            
            existing_indexes = [idx['name'] for idx in inspector.get_indexes('users')]
            
            for idx_name, col_name in indexes_to_add:
                if idx_name not in existing_indexes:
                    try:
                        print(f"Создаем индекс: {idx_name}...")
                        conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON users ({col_name})"))
                        conn.commit()
                        print(f"  ✓ Индекс {idx_name} создан")
                    except Exception as e:
                        print(f"  ✗ Ошибка при создании индекса {idx_name}: {e}")
            
            print(f"\n✓ Добавлено колонок: {added_count}")
            print("=" * 60)
            return True
            
    except Exception as e:
        print(f"\n✗ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = add_role_column()
    sys.exit(0 if success else 1)
