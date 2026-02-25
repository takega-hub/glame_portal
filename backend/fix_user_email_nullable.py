#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для изменения колонки email на nullable в таблице users
Позволяет создавать покупателей без email адреса
"""
import sys
import os

# Устанавливаем кодировку для Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

from sqlalchemy import create_engine, text
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

def fix_email_nullable():
    """Изменение колонки email на nullable"""
    print("=" * 60)
    print("Изменение колонки email на nullable")
    print("=" * 60)
    
    try:
        with engine.connect() as conn:
            # Удаляем уникальный индекс (если существует)
            print("1. Удаление старого индекса...")
            try:
                conn.execute(text("DROP INDEX IF EXISTS ix_users_email"))
                conn.commit()
                print("   ✓ Индекс удален")
            except Exception as e:
                print(f"   ⚠ Ошибка при удалении индекса: {e}")
            
            # Изменяем колонку email на nullable
            print("2. Изменение колонки email на nullable...")
            conn.execute(text("ALTER TABLE users ALTER COLUMN email DROP NOT NULL"))
            conn.commit()
            print("   ✓ Колонка изменена на nullable")
            
            # Создаем частичный уникальный индекс только для не-NULL значений
            print("3. Создание частичного уникального индекса...")
            conn.execute(text("""
                CREATE UNIQUE INDEX ix_users_email 
                ON users(email) 
                WHERE email IS NOT NULL
            """))
            conn.commit()
            print("   ✓ Частичный уникальный индекс создан")
            
            print("\n" + "=" * 60)
            print("✓ Миграция выполнена успешно!")
            print("=" * 60)
            return True
            
    except Exception as e:
        print(f"\n✗ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = fix_email_nullable()
    sys.exit(0 if success else 1)
