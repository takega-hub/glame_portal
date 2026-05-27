#!/usr/bin/env python3
import os

# Проверяем, какой DATABASE_URL используется
DATABASE_URL = os.getenv("DATABASE_URL")
print(f"DATABASE_URL из окружения: {DATABASE_URL}")

if not DATABASE_URL:
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5433")
    DB_USER = os.getenv("DB_USER", "glame_user")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "glame_password")
    DB_NAME = os.getenv("DB_NAME", "glame_db")
    
    DATABASE_URL = f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    print(f"Сформированный DATABASE_URL: {DATABASE_URL}")
    print(f"DB_HOST: {DB_HOST}")
    print(f"DB_PORT: {DB_PORT}")
else:
    print(f"Используется DATABASE_URL из окружения: {DATABASE_URL}")