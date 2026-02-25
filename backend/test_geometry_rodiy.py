"""
Тест товаров с брендом Geometry И покрытием Родий
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

# Добавляем путь к app
sys.path.insert(0, os.path.dirname(__file__))

# Загружаем .env
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")

if not DATABASE_URL:
    print("[ERROR] DATABASE_URL not found")
    sys.exit(1)

def test_filter():
    """Тест фильтрации"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("=" * 80)
        print("ТЕСТ: ТОВАРЫ С БРЕНДОМ Geometry И ПОКРЫТИЕМ Родий")
        print("=" * 80)
        print()
        
        # Проверяем товары с покрытием "Родий"
        print("1. Товары с покрытием 'Родий' (основные, без вариантов):")
        print("-" * 80)
        cursor.execute("""
            SELECT 
                name,
                article,
                brand,
                specifications->>'Бренд' as spec_brand,
                specifications->>'Покрытие' as pokrytie
            FROM products
            WHERE is_active = true
            AND (
                specifications IS NULL
                OR specifications->>'parent_external_id' IS NULL
                OR specifications->>'parent_external_id' = ''
            )
            AND specifications IS NOT NULL
            AND LOWER(specifications->>'Покрытие') = LOWER('Родий')
            LIMIT 20;
        """)
        products = cursor.fetchall()
        print(f"Найдено: {len(products)} товаров")
        for p in products:
            print(f"  {p['name']:<50} brand={p['brand'] or p['spec_brand']:<15} pokrytie={p['pokrytie']}")
        print()
        
        # Проверяем товары с брендом "Geometry"
        print("2. Товары с брендом 'Geometry' (основные, без вариантов):")
        print("-" * 80)
        cursor.execute("""
            SELECT 
                name,
                article,
                brand,
                specifications->>'Бренд' as spec_brand,
                specifications->>'Покрытие' as pokrytie
            FROM products
            WHERE is_active = true
            AND (
                specifications IS NULL
                OR specifications->>'parent_external_id' IS NULL
                OR specifications->>'parent_external_id' = ''
            )
            AND (
                brand IS NOT NULL AND LOWER(brand) = LOWER('Geometry')
                OR specifications IS NOT NULL AND LOWER(specifications->>'Бренд') = LOWER('Geometry')
            )
            LIMIT 20;
        """)
        products = cursor.fetchall()
        print(f"Найдено: {len(products)} товаров")
        for p in products:
            print(f"  {p['name']:<50} brand={p['brand'] or p['spec_brand']:<15} pokrytie={p['pokrytie']}")
        print()
        
        # Проверяем товары с брендом "Geometry" И покрытием "Родий"
        print("3. Товары с брендом 'Geometry' И покрытием 'Родий' (основные):")
        print("-" * 80)
        cursor.execute("""
            SELECT 
                name,
                article,
                brand,
                specifications->>'Бренд' as spec_brand,
                specifications->>'Покрытие' as pokrytie
            FROM products
            WHERE is_active = true
            AND (
                specifications IS NULL
                OR specifications->>'parent_external_id' IS NULL
                OR specifications->>'parent_external_id' = ''
            )
            AND specifications IS NOT NULL
            AND (
                brand IS NOT NULL AND LOWER(brand) = LOWER('Geometry')
                OR specifications IS NOT NULL AND LOWER(specifications->>'Бренд') = LOWER('Geometry')
            )
            AND LOWER(specifications->>'Покрытие') = LOWER('Родий')
            LIMIT 20;
        """)
        products = cursor.fetchall()
        print(f"Найдено: {len(products)} товаров")
        for p in products:
            print(f"  {p['name']:<50} brand={p['brand'] or p['spec_brand']:<15} pokrytie={p['pokrytie']}")
        print()
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_filter()
