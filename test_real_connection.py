#!/usr/bin/env python3
import os
import sys
sys.path.append('/app')

from app.database.connection import DATABASE_URL, engine

print(f"DATABASE_URL из connection.py: {DATABASE_URL}")
print(f"Engine URL: {engine.url}")

# Проверим переменные окружения
print("\nПеременные окружения:")
for key in ['DB_HOST', 'DB_PORT', 'DB_USER', 'DB_PASSWORD', 'DB_NAME', 'DATABASE_URL']:
    value = os.getenv(key)
    print(f"{key}: {value}")