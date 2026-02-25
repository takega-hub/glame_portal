#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Скрипт для создания тестовых покупателей
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
import uuid
from datetime import datetime, timedelta
import random

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

# Тестовые покупатели
test_customers = [
    {
        "email": "anna.ivanova@example.com",
        "phone": "79787450654",
        "full_name": "Иванова Анна Петровна",
        "discount_card_number": "79787450654",
        "customer_segment": "VIP",
        "loyalty_points": 5000,
        "total_purchases": 15,
        "total_spent": 2500000,  # 25,000 руб в копейках
        "average_check": 166667,  # ~1,667 руб
        "last_purchase_date": datetime.now() - timedelta(days=5),
    },
    {
        "email": "maria.petrova@example.com",
        "phone": "79161234567",
        "full_name": "Петрова Мария Сергеевна",
        "discount_card_number": "79161234567",
        "customer_segment": "Active",
        "loyalty_points": 2500,
        "total_purchases": 8,
        "total_spent": 1200000,  # 12,000 руб
        "average_check": 150000,  # 1,500 руб
        "last_purchase_date": datetime.now() - timedelta(days=15),
    },
    {
        "email": "elena.sidorova@example.com",
        "phone": "79261234568",
        "full_name": "Сидорова Елена Владимировна",
        "discount_card_number": "79261234568",
        "customer_segment": "Regular",
        "loyalty_points": 800,
        "total_purchases": 3,
        "total_spent": 450000,  # 4,500 руб
        "average_check": 150000,  # 1,500 руб
        "last_purchase_date": datetime.now() - timedelta(days=45),
    },
    {
        "email": "olga.kozlova@example.com",
        "phone": "79361234569",
        "full_name": "Козлова Ольга Александровна",
        "discount_card_number": "79361234569",
        "customer_segment": "Sleeping",
        "loyalty_points": 200,
        "total_purchases": 2,
        "total_spent": 300000,  # 3,000 руб
        "average_check": 150000,  # 1,500 руб
        "last_purchase_date": datetime.now() - timedelta(days=120),
    },
    {
        "email": "tatiana.novikova@example.com",
        "phone": "79461234570",
        "full_name": "Новикова Татьяна Игоревна",
        "discount_card_number": "79461234570",
        "customer_segment": "New",
        "loyalty_points": 100,
        "total_purchases": 1,
        "total_spent": 150000,  # 1,500 руб
        "average_check": 150000,  # 1,500 руб
        "last_purchase_date": datetime.now() - timedelta(days=7),
    },
]

def create_test_customers():
    """Создание тестовых покупателей"""
    print("=" * 60)
    print("Создание тестовых покупателей")
    print("=" * 60)
    
    try:
        with engine.connect() as conn:
            created_count = 0
            updated_count = 0
            
            for customer_data in test_customers:
                # Проверяем, существует ли покупатель
                result = conn.execute(
                    text("SELECT id FROM users WHERE phone = :phone OR discount_card_number = :card"),
                    {"phone": customer_data["phone"], "card": customer_data["discount_card_number"]}
                )
                existing = result.fetchone()
                
                if existing:
                    # Обновляем существующего пользователя
                    user_id = existing[0]
                    conn.execute(
                        text("""
                            UPDATE users 
                            SET full_name = :full_name,
                                discount_card_number = :discount_card_number,
                                customer_segment = :customer_segment,
                                loyalty_points = :loyalty_points,
                                total_purchases = :total_purchases,
                                total_spent = :total_spent,
                                average_check = :average_check,
                                last_purchase_date = :last_purchase_date,
                                is_customer = true,
                                role = 'customer'
                            WHERE id = :id
                        """),
                        {
                            "id": user_id,
                            **customer_data
                        }
                    )
                    updated_count += 1
                    print(f"✓ Обновлен покупатель: {customer_data['full_name']}")
                else:
                    # Создаем нового покупателя
                    user_id = str(uuid.uuid4())
                    conn.execute(
                        text("""
                            INSERT INTO users (
                                id, email, phone, full_name, discount_card_number,
                                customer_segment, loyalty_points, total_purchases,
                                total_spent, average_check, last_purchase_date,
                                is_customer, role, created_at
                            ) VALUES (
                                :id, :email, :phone, :full_name, :discount_card_number,
                                :customer_segment, :loyalty_points, :total_purchases,
                                :total_spent, :average_check, :last_purchase_date,
                                true, 'customer', NOW()
                            )
                        """),
                        {
                            "id": user_id,
                            **customer_data
                        }
                    )
                    created_count += 1
                    print(f"✓ Создан покупатель: {customer_data['full_name']}")
            
            conn.commit()
            
            print("\n" + "=" * 60)
            print(f"✓ Создано покупателей: {created_count}")
            print(f"✓ Обновлено покупателей: {updated_count}")
            print("=" * 60)
            return True
            
    except Exception as e:
        print(f"\n✗ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = create_test_customers()
    sys.exit(0 if success else 1)
