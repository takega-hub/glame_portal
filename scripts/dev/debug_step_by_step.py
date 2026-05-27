#!/usr/bin/env python3
import os
import sys

# Проверяем шаг за шагом, что происходит
print("=== Шаг 1: Переменные окружения ===")
print(f"DB_HOST: {os.getenv('DB_HOST')}")
print(f"DB_PORT: {os.getenv('DB_PORT')}")
print(f"DATABASE_URL: {os.getenv('DATABASE_URL')}")

print("\n=== Шаг 2: Логика из connection.py ===")
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("DATABASE_URL не задан, используем отдельные переменные")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5433")
    DB_USER = os.getenv("DB_USER", "glame_user")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "glame_password")
    DB_NAME = os.getenv("DB_NAME", "glame_db")
    
    print(f"DB_HOST (default=localhost): {DB_HOST}")
    print(f"DB_PORT (default=5433): {DB_PORT}")
    
    formed_url = f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    print(f"Сформированный URL: {formed_url}")
else:
    print(f"Используем DATABASE_URL: {DATABASE_URL}")

print("\n=== Шаг 3: Проверка импорта ===")
# Проверим, не импортируется ли старый модуль
if 'app.database.connection' in sys.modules:
    print("Модуль app.database.connection уже загружен")
    import app.database.connection
    print(f"DATABASE_URL из модуля: {app.database.connection.DATABASE_URL}")
else:
    print("Модуль app.database.connection не загружен")