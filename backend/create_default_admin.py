#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для создания администратора с дефолтными данными
Использование: python create_default_admin.py
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
import bcrypt
import uuid

def hash_password(password: str) -> str:
    """Хеширование пароля с помощью bcrypt"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

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

# Дефолтные данные администратора
DEFAULT_EMAIL = "admin@glame.ru"
DEFAULT_PASSWORD = "admin123"

def create_default_admin():
    """Создание администратора с дефолтными данными"""
    print("=" * 60)
    print("Создание администратора GLAME (дефолтные данные)")
    print("=" * 60)
    print(f"\nEmail: {DEFAULT_EMAIL}")
    print(f"Пароль: {DEFAULT_PASSWORD}")
    print("\n⚠️  ВНИМАНИЕ: Используйте эти данные для первого входа!")
    print("   После входа рекомендуется изменить пароль.")
    print("=" * 60)
    
    try:
        with engine.connect() as conn:
            # Проверяем, существует ли пользователь
            result = conn.execute(
                text("SELECT id, email, role FROM users WHERE email = :email"),
                {"email": DEFAULT_EMAIL}
            )
            existing = result.fetchone()
            
            if existing:
                # Обновляем существующего пользователя
                password_hash = hash_password(DEFAULT_PASSWORD)
                conn.execute(
                    text("""
                        UPDATE users 
                        SET password_hash = :password_hash, 
                            role = 'admin',
                            is_customer = false
                        WHERE email = :email
                    """),
                    {"password_hash": password_hash, "email": DEFAULT_EMAIL}
                )
                conn.commit()
                print(f"\n✓ Пользователь {DEFAULT_EMAIL} обновлен и назначен администратором")
            else:
                # Создаем нового администратора
                password_hash = hash_password(DEFAULT_PASSWORD)
                user_id = str(uuid.uuid4())
                conn.execute(
                    text("""
                        INSERT INTO users (id, email, password_hash, role, is_customer, loyalty_points, total_purchases, total_spent, created_at)
                        VALUES (:id, :email, :password_hash, 'admin', false, 0, 0, 0, NOW())
                    """),
                    {"id": user_id, "email": DEFAULT_EMAIL, "password_hash": password_hash}
                )
                conn.commit()
                print(f"\n✓ Администратор {DEFAULT_EMAIL} успешно создан")
            
            print("\n" + "=" * 60)
            print("Данные для входа:")
            print(f"  Email: {DEFAULT_EMAIL}")
            print(f"  Пароль: {DEFAULT_PASSWORD}")
            print("\nИспользуйте эти данные для входа на странице /login")
            print("=" * 60)
            return True
            
    except Exception as e:
        print(f"\n✗ Ошибка при создании администратора: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = create_default_admin()
    sys.exit(0 if success else 1)
