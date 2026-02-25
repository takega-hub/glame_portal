"""
Тест фильтрации по покрытию "Родий"
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

def test_filter():
    """Тест фильтрации"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("=" * 80)
        print("ТЕСТ ФИЛЬТРАЦИИ ПО ПОКРЫТИЮ 'Родий'")
        print("=" * 80)
        print()
        
        # Проверяем товары с покрытием "Родий" БЕЗ исключения вариантов
        print("1. ВСЕ товары с покрытием 'Родий' (включая варианты):")
        print("-" * 80)
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM products
            WHERE specifications IS NOT NULL
            AND specifications->>'Покрытие' = 'Родий'
            AND is_active = true;
        """)
        result = cursor.fetchone()
        print(f"   Найдено: {result['count']} товаров")
        print()
        
        # Проверяем товары с покрытием "Родий" С исключением вариантов
        print("2. Товары с покрытием 'Родий' БЕЗ вариантов (основные товары):")
        print("-" * 80)
        cursor.execute("""
            SELECT 
                name,
                article,
                specifications->>'Покрытие' as pokrytie,
                specifications->>'parent_external_id' as parent_id
            FROM products
            WHERE specifications IS NOT NULL
            AND specifications->>'Покрытие' = 'Родий'
            AND is_active = true
            AND (
                specifications->>'parent_external_id' IS NULL
                OR specifications->>'parent_external_id' = ''
            )
            LIMIT 10;
        """)
        products = cursor.fetchall()
        print(f"   Найдено: {len(products)} товаров (показано первые 10)")
        for p in products:
            print(f"   {p['name']:<50} article={p['article']:<15} parent_id={p['parent_id'] or 'None'}")
        print()
        
        # Проверяем варианты с покрытием "Родий"
        print("3. ВАРИАНТЫ товаров с покрытием 'Родий':")
        print("-" * 80)
        cursor.execute("""
            SELECT 
                name,
                article,
                specifications->>'Покрытие' as pokrytie,
                specifications->>'parent_external_id' as parent_id
            FROM products
            WHERE specifications IS NOT NULL
            AND specifications->>'Покрытие' = 'Родий'
            AND is_active = true
            AND specifications->>'parent_external_id' IS NOT NULL
            AND specifications->>'parent_external_id' != ''
            LIMIT 10;
        """)
        variants = cursor.fetchall()
        print(f"   Найдено вариантов: {len(variants)} (показано первые 10)")
        for v in variants:
            print(f"   {v['name']:<50} article={v['article']:<15} parent_id={v['parent_id']}")
        print()
        
        # Проверяем основной товар для одного из вариантов
        if variants:
            parent_id = variants[0]['parent_id']
            print(f"4. Основной товар для варианта (parent_external_id={parent_id}):")
            print("-" * 80)
            cursor.execute("""
                SELECT 
                    name,
                    article,
                    specifications->>'Покрытие' as pokrytie
                FROM products
                WHERE external_id = %s
                AND is_active = true;
            """, (parent_id,))
            parent = cursor.fetchone()
            if parent:
                print(f"   {parent['name']:<50} article={parent['article']:<15} pokrytie={parent['pokrytie']}")
            else:
                print("   Основной товар не найден")
        print()
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_filter()
