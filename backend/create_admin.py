#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для создания администратора
Использование: python create_admin.py
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
import getpass
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

def create_admin(email=None, password=None):
    """Создание администратора"""
    print("=" * 60)
    print("Создание администратора GLAME")
    print("=" * 60)
    
    # Запрашиваем данные, если не переданы
    if not email:
        try:
            email = input("\nВведите email администратора: ").strip()
        except EOFError:
            # Если нет интерактивного ввода, используем дефолтные значения
            email = os.getenv("ADMIN_EMAIL", "admin@glame.ru")
            print(f"\nИспользуется email из переменной окружения или дефолтный: {email}")
    
    if not email:
        print("Ошибка: email обязателен")
        return False
    
    if not password:
        try:
            password = getpass.getpass("Введите пароль: ").strip()
            if not password:
                password = os.getenv("ADMIN_PASSWORD", "admin123")
                print(f"Используется пароль из переменной окружения или дефолтный")
        except EOFError:
            password = os.getenv("ADMIN_PASSWORD", "admin123")
            print(f"Используется пароль из переменной окружения или дефолтный")
    
    if not password or len(password) < 6:
        print("Ошибка: пароль должен быть не менее 6 символов")
        return False
    
    if not os.getenv("ADMIN_PASSWORD"):  # Только если не из env
        try:
            password_confirm = getpass.getpass("Подтвердите пароль: ").strip()
            if password != password_confirm:
                print("Ошибка: пароли не совпадают")
                return False
        except EOFError:
            pass  # Пропускаем подтверждение в неинтерактивном режиме
    
    try:
        with engine.connect() as conn:
            # Проверяем, существует ли пользователь (без role, так как может не быть)
            result = conn.execute(
                text("SELECT id, email FROM users WHERE email = :email"),
                {"email": email}
            )
            existing = result.fetchone()
            
            if existing:
                # Обновляем существующего пользователя
                password_hash = hash_password(password)
                conn.execute(
                    text("""
                        UPDATE users 
                        SET password_hash = :password_hash, 
                            role = 'admin',
                            is_customer = false
                        WHERE email = :email
                    """),
                    {"password_hash": password_hash, "email": email}
                )
                conn.commit()
                print(f"\n✓ Пользователь {email} обновлен и назначен администратором")
            else:
                # Создаем нового администратора
                password_hash = hash_password(password)
                user_id = str(uuid.uuid4())
                conn.execute(
                    text("""
                        INSERT INTO users (id, email, password_hash, role, is_customer, loyalty_points, total_purchases, total_spent, created_at)
                        VALUES (:id, :email, :password_hash, 'admin', false, 0, 0, 0, NOW())
                    """),
                    {"id": user_id, "email": email, "password_hash": password_hash}
                )
                conn.commit()
                print(f"\n✓ Администратор {email} успешно создан")
            
            print("\nДанные для входа:")
            print(f"  Email: {email}")
            print(f"  Пароль: [введенный вами пароль]")
            print("\nИспользуйте эти данные для входа на странице /login")
            print("=" * 60)
            return True
            
    except Exception as e:
        print(f"\n✗ Ошибка при создании администратора: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Создание администратора GLAME')
    parser.add_argument('--email', type=str, help='Email администратора')
    parser.add_argument('--password', type=str, help='Пароль администратора')
    args = parser.parse_args()
    
    success = create_admin(email=args.email, password=args.password)
    sys.exit(0 if success else 1)
