"""
Скрипт для проверки товаров с покрытием "Позолота"
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

def check_pokrytie():
    """Проверить товары с покрытием Позолота"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("=" * 80)
        print("ПРОВЕРКА ТОВАРОВ С ПОКРЫТИЕМ 'Позолота'")
        print("=" * 80)
        print()
        
        # Проверяем все значения покрытия
        print("ВСЕ ЗНАЧЕНИЯ ПОКРЫТИЯ:")
        print("-" * 80)
        cursor.execute("""
            SELECT 
                specifications->>'Покрытие' as pokrytie,
                COUNT(*) as count
            FROM products
            WHERE specifications IS NOT NULL
            AND specifications->>'Покрытие' IS NOT NULL
            GROUP BY specifications->>'Покрытие'
            ORDER BY count DESC;
        """)
        pokrytie_values = cursor.fetchall()
        for p in pokrytie_values:
            print(f"  {p['pokrytie']:<30} {p['count']:>5} товаров")
        print()
        
        # Проверяем товары с покрытием "Позолота"
        print("ТОВАРЫ С ПОКРЫТИЕМ 'Позолота':")
        print("-" * 80)
        cursor.execute("""
            SELECT 
                name,
                article,
                specifications->>'Покрытие' as pokrytie
            FROM products
            WHERE specifications IS NOT NULL
            AND specifications->>'Покрытие' = 'Позолота'
            AND is_active = true
            LIMIT 10;
        """)
        products = cursor.fetchall()
        if products:
            print(f"Найдено товаров: {len(products)} (показано первые 10)")
            for p in products:
                print(f"  {p['name']:<50} article={p['article']:<15} pokrytie={p['pokrytie']}")
        else:
            print("  Товары с покрытием 'Позолота' не найдены")
        print()
        
        # Проверяем точное совпадение
        print("ПРОВЕРКА РАЗЛИЧНЫХ ВАРИАНТОВ НАПИСАНИЯ:")
        print("-" * 80)
        variants = ['Позолота', 'позолота', 'ПОЗОЛОТА', 'Позолота ', ' Позолота']
        for variant in variants:
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM products
                WHERE specifications IS NOT NULL
                AND specifications->>'Покрытие' = %s
                AND is_active = true;
            """, (variant,))
            result = cursor.fetchone()
            print(f"  '{variant}': {result['count']} товаров")
        print()
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_pokrytie()
