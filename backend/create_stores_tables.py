"""
Скрипт создания таблиц stores и store_visits
"""
import os
import psycopg2
from dotenv import load_dotenv
from pathlib import Path

# Загружаем .env
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")

if not DATABASE_URL:
    print("[ERROR] DATABASE_URL not found")
    exit(1)

# Парсим URL
from urllib.parse import urlparse
parsed = urlparse(DATABASE_URL)

try:
    conn = psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        database=parsed.path[1:],
        user=parsed.username,
        password=parsed.password
    )
    
    cursor = conn.cursor()
    
    # Читаем SQL скрипт
    sql_file = Path(__file__).parent / "sql" / "create_stores_tables.sql"
    with open(sql_file, 'r', encoding='utf-8') as f:
        sql = f.read()
    
    print("[INFO] Creating tables...")
    cursor.execute(sql)
    conn.commit()
    
    print("[OK] Tables created successfully")
    
    cursor.close()
    conn.close()

except Exception as e:
    print(f"[ERROR] {e}")
    exit(1)
