#!/usr/bin/env python3
import os
import sys
sys.path.append('/app')

# Проверяем переменные окружения
print("=== Переменные окружения ===")
for key in ['DB_HOST', 'DB_PORT', 'DB_USER', 'DB_PASSWORD', 'DB_NAME', 'DATABASE_URL']:
    value = os.getenv(key)
    print(f"{key}: {value}")

print("\n=== Проверка connection.py ===")
from app.database.connection import DATABASE_URL, engine
print(f"DATABASE_URL: {DATABASE_URL}")
print(f"Engine URL: {engine.url}")

# Проверяем, как формируется URL
if not os.getenv("DATABASE_URL"):
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5433")
    DB_USER = os.getenv("DB_USER", "glame_user")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "glame_password")
    DB_NAME = os.getenv("DB_NAME", "glame_db")
    
    formed_url = f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    print(f"Сформированный URL: {formed_url}")
else:
    print("Используется DATABASE_URL из окружения")