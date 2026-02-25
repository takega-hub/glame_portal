#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для проверки и установки роли пользователя
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

def check_and_fix_roles():
    """Проверка и установка ролей для всех пользователей"""
    print("=" * 60)
    print("Проверка и установка ролей пользователей")
    print("=" * 60)
    
    try:
        with engine.connect() as conn:
            # Получаем всех пользователей
            result = conn.execute(text("SELECT id, email, role FROM users"))
            users = result.fetchall()
            
            print(f"\nНайдено пользователей: {len(users)}\n")
            
            updated_count = 0
            for user_id, email, role in users:
                print(f"Email: {email or 'N/A'}")
                print(f"  Текущая роль: {role or 'НЕ УСТАНОВЛЕНА'}")
                
                # Если роль не установлена, устанавливаем 'admin' для пользователей с email
                if not role and email:
                    new_role = 'admin'  # По умолчанию admin для пользователей с email
                    conn.execute(
                        text("UPDATE users SET role = :role WHERE id = :id"),
                        {"role": new_role, "id": user_id}
                    )
                    conn.commit()
                    print(f"  ✓ Роль установлена: {new_role}")
                    updated_count += 1
                elif not role:
                    # Для пользователей без email устанавливаем 'customer'
                    new_role = 'customer'
                    conn.execute(
                        text("UPDATE users SET role = :role WHERE id = :id"),
                        {"role": new_role, "id": user_id}
                    )
                    conn.commit()
                    print(f"  ✓ Роль установлена: {new_role}")
                    updated_count += 1
                else:
                    print(f"  - Роль уже установлена")
                print()
            
            print("=" * 60)
            print(f"✓ Обновлено пользователей: {updated_count}")
            print("=" * 60)
            return True
            
    except Exception as e:
        print(f"\n✗ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = check_and_fix_roles()
    sys.exit(0 if success else 1)
