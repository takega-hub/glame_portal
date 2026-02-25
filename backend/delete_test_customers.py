#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для удаления тестовых покупателей
Удаляет всех покупателей с email адресами @example.com

Использование:
    python delete_test_customers.py          # с подтверждением
    python delete_test_customers.py --yes    # без подтверждения
"""
import sys
import os
import argparse

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

def delete_test_customers(auto_confirm=False):
    """Удаление тестовых покупателей с email @example.com"""
    print("=" * 60)
    print("Удаление тестовых покупателей")
    print("=" * 60)
    
    try:
        with engine.connect() as conn:
            # Сначала показываем, что будет удалено
            result = conn.execute(
                text("""
                    SELECT id, email, phone, full_name, is_customer 
                    FROM users 
                    WHERE email LIKE '%@example.com' 
                       OR (is_customer = true AND email IS NULL AND phone IS NOT NULL)
                    ORDER BY email
                """)
            )
            test_customers = result.fetchall()
            
            if not test_customers:
                print("✓ Тестовые покупатели не найдены")
                return True
            
            print(f"\nНайдено тестовых покупателей: {len(test_customers)}")
            print("\nСписок покупателей для удаления:")
            print("-" * 60)
            for customer in test_customers:
                email = customer[1] or "нет email"
                phone = customer[2] or "нет телефона"
                name = customer[3] or "Без имени"
                print(f"  • {name} ({email}, {phone})")
            print("-" * 60)
            
            # Подтверждение
            if not auto_confirm:
                try:
                    response = input("\nУдалить этих покупателей? (yes/no): ").strip().lower()
                    if response not in ['yes', 'y', 'да', 'д']:
                        print("Отменено")
                        return False
                except (EOFError, KeyboardInterrupt):
                    print("\nОтменено")
                    return False
            else:
                print("\nАвтоматическое удаление (--yes)")
            
            # Удаляем связанные данные (если есть)
            # Удаляем историю покупок
            deleted_purchases = conn.execute(
                text("""
                    DELETE FROM purchase_history 
                    WHERE user_id IN (
                        SELECT id FROM users 
                        WHERE email LIKE '%@example.com' 
                           OR (is_customer = true AND email IS NULL AND phone IS NOT NULL)
                    )
                """)
            )
            purchases_count = deleted_purchases.rowcount
            
            # Удаляем транзакции лояльности (если таблица существует)
            try:
                deleted_transactions = conn.execute(
                    text("""
                        DELETE FROM loyalty_transactions 
                        WHERE user_id IN (
                            SELECT id FROM users 
                            WHERE email LIKE '%@example.com' 
                               OR (is_customer = true AND email IS NULL AND phone IS NOT NULL)
                        )
                    """)
                )
                transactions_count = deleted_transactions.rowcount
            except Exception:
                transactions_count = 0
            
            # Удаляем сохраненные образы (если таблица существует)
            try:
                deleted_looks = conn.execute(
                    text("""
                        DELETE FROM saved_looks 
                        WHERE user_id IN (
                            SELECT id FROM users 
                            WHERE email LIKE '%@example.com' 
                               OR (is_customer = true AND email IS NULL AND phone IS NOT NULL)
                        )
                    """)
                )
                looks_count = deleted_looks.rowcount
            except Exception:
                looks_count = 0
            
            # Удаляем самих покупателей
            deleted_users = conn.execute(
                text("""
                    DELETE FROM users 
                    WHERE email LIKE '%@example.com' 
                       OR (is_customer = true AND email IS NULL AND phone IS NOT NULL)
                """)
            )
            users_count = deleted_users.rowcount
            
            conn.commit()
            
            print("\n" + "=" * 60)
            print(f"✓ Удалено покупателей: {users_count}")
            if purchases_count > 0:
                print(f"✓ Удалено записей истории покупок: {purchases_count}")
            if transactions_count > 0:
                print(f"✓ Удалено транзакций лояльности: {transactions_count}")
            if looks_count > 0:
                print(f"✓ Удалено сохраненных образов: {looks_count}")
            print("=" * 60)
            return True
            
    except Exception as e:
        print(f"\n✗ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Удаление тестовых покупателей')
    parser.add_argument('--yes', '-y', action='store_true', 
                       help='Удалить без подтверждения')
    args = parser.parse_args()
    
    success = delete_test_customers(auto_confirm=args.yes)
    sys.exit(0 if success else 1)
