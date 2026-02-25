"""
Тест API фильтрации по покрытию через прямой SQL запрос
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

def test_api_filter():
    """Тест фильтрации как в API"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("=" * 80)
        print("ТЕСТ ФИЛЬТРАЦИИ КАК В API (с исключением вариантов)")
        print("=" * 80)
        print()
        
        # Имитируем запрос как в API
        # 1. is_active = True
        # 2. Исключаем варианты (parent_external_id is null or empty)
        # 3. Фильтр по покрытию "Родий"
        
        query = """
            SELECT 
                name,
                article,
                specifications->>'Покрытие' as pokrytie,
                specifications->>'parent_external_id' as parent_id,
                is_active
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
        """
        
        print("SQL запрос:")
        print(query)
        print()
        
        cursor.execute(query)
        products = cursor.fetchall()
        
        print(f"Результат: найдено {len(products)} товаров")
        print("-" * 80)
        for p in products:
            print(f"  {p['name']:<50} article={p['article']:<15} pokrytie={p['pokrytie']}")
        print()
        
        # Проверяем без фильтра по покрытию
        query2 = """
            SELECT COUNT(*) as count
            FROM products
            WHERE is_active = true
            AND (
                specifications IS NULL
                OR specifications->>'parent_external_id' IS NULL
                OR specifications->>'parent_external_id' = ''
            );
        """
        cursor.execute(query2)
        total = cursor.fetchone()['count']
        print(f"Всего основных товаров (без вариантов): {total}")
        print()
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_api_filter()
