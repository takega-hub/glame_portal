"""
Скрипт для проверки брендов товаров в базе данных
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
import json

# Добавляем путь к app
sys.path.insert(0, os.path.dirname(__file__))

# Загружаем .env
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")

if not DATABASE_URL:
    print("[ERROR] DATABASE_URL not found")
    sys.exit(1)

def check_brands():
    """Проверить бренды товаров"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("=" * 80)
        print("ПРОВЕРКА БРЕНДОВ ТОВАРОВ")
        print("=" * 80)
        print()
        
        # Проверяем бренды в поле brand
        print("БРЕНДЫ В ПОЛЕ brand:")
        print("-" * 80)
        cursor.execute("""
            SELECT 
                brand,
                COUNT(*) as count
            FROM products
            WHERE brand IS NOT NULL
            GROUP BY brand
            ORDER BY count DESC;
        """)
        brands = cursor.fetchall()
        for b in brands:
            print(f"  {b['brand']:<30} {b['count']:>5} товаров")
        print(f"\nВсего уникальных брендов в поле brand: {len(brands)}")
        print()
        
        # Проверяем бренды в specifications['Бренд']
        print("БРЕНДЫ В specifications['Бренд']:")
        print("-" * 80)
        cursor.execute("""
            SELECT 
                specifications->>'Бренд' as brand,
                COUNT(*) as count
            FROM products
            WHERE specifications IS NOT NULL
            AND specifications->>'Бренд' IS NOT NULL
            GROUP BY specifications->>'Бренд'
            ORDER BY count DESC;
        """)
        specs_brands = cursor.fetchall()
        for b in specs_brands:
            print(f"  {b['brand']:<30} {b['count']:>5} товаров")
        print(f"\nВсего уникальных брендов в specifications: {len(specs_brands)}")
        print()
        
        # Проверяем товары с брендом AGafi
        print("ТОВАРЫ С БРЕНДОМ 'AGafi' (в поле brand):")
        print("-" * 80)
        cursor.execute("""
            SELECT 
                name,
                article,
                brand
            FROM products
            WHERE brand = 'AGafi'
            LIMIT 10;
        """)
        agafi_brand = cursor.fetchall()
        if agafi_brand:
            for p in agafi_brand:
                print(f"  {p['name']:<50} article={p['article']:<15} brand={p['brand']}")
        else:
            print("  Товары с брендом 'AGafi' в поле brand не найдены")
        print()
        
        # Проверяем товары с брендом AGafi в specifications
        print("ТОВАРЫ С БРЕНДОМ 'AGafi' (в specifications['Бренд']):")
        print("-" * 80)
        cursor.execute("""
            SELECT 
                name,
                article,
                specifications->>'Бренд' as brand
            FROM products
            WHERE specifications IS NOT NULL
            AND specifications->>'Бренд' = 'AGafi'
            LIMIT 10;
        """)
        agafi_specs = cursor.fetchall()
        if agafi_specs:
            for p in agafi_specs:
                print(f"  {p['name']:<50} article={p['article']:<15} brand={p['brand']}")
        else:
            print("  Товары с брендом 'AGafi' в specifications не найдены")
        print()
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_brands()
