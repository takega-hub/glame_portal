"""
Скрипт для проверки категорий товаров в базе данных
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

def main():
    """Основная функция"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("=" * 80)
        print("ПРОВЕРКА КАТЕГОРИЙ ТОВАРОВ")
        print("=" * 80)
        print()
        
        # Проверяем разделы каталога
        print("РАЗДЕЛЫ КАТАЛОГА (catalog_sections):")
        print("-" * 80)
        cursor.execute("SELECT name, external_id, is_active FROM catalog_sections ORDER BY name;")
        sections = cursor.fetchall()
        for section in sections:
            print(f"  {section['name']:<30} external_id={section['external_id']:<40} active={section['is_active']}")
        print(f"\nВсего разделов: {len(sections)}")
        print()
        
        # Проверяем категории товаров
        print("КАТЕГОРИИ ТОВАРОВ (products.category):")
        print("-" * 80)
        cursor.execute("""
            SELECT 
                category,
                COUNT(*) as count
            FROM products
            WHERE category IS NOT NULL
            GROUP BY category
            ORDER BY count DESC;
        """)
        categories = cursor.fetchall()
        for cat in categories:
            print(f"  {cat['category']:<30} {cat['count']:>5} товаров")
        print(f"\nВсего уникальных категорий: {len(categories)}")
        print()
        
        # Проверяем товары без категории
        cursor.execute("SELECT COUNT(*) as count FROM products WHERE category IS NULL;")
        no_category = cursor.fetchone()
        print(f"Товаров без категории: {no_category['count']}")
        print()
        
        # Проверяем товары с категориями AGafi и SALE
        print("ПОИСК ТОВАРОВ С КАТЕГОРИЯМИ 'AGafi' и 'SALE':")
        print("-" * 80)
        cursor.execute("""
            SELECT 
                name,
                article,
                category,
                external_id
            FROM products
            WHERE category ILIKE '%AGafi%' OR category ILIKE '%SALE%'
            LIMIT 10;
        """)
        products = cursor.fetchall()
        if products:
            for p in products:
                print(f"  {p['name']:<50} article={p['article']:<15} category={p['category']}")
        else:
            print("  Товары с категориями 'AGafi' или 'SALE' не найдены")
        print()
        
        # Проверяем несколько товаров для примера
        print("ПРИМЕРЫ ТОВАРОВ (первые 10):")
        print("-" * 80)
        cursor.execute("""
            SELECT 
                name,
                article,
                category,
                external_id
            FROM products
            WHERE is_active = true
            LIMIT 10;
        """)
        sample_products = cursor.fetchall()
        for p in sample_products:
            print(f"  {p['name']:<50} article={p['article']:<15} category={p['category'] or 'NULL'}")
        print()
        
        # Проверяем, есть ли товары с external_id, которые должны быть в категориях
        print("ПРОВЕРКА СВЯЗИ ТОВАРОВ С РАЗДЕЛАМИ:")
        print("-" * 80)
        cursor.execute("""
            SELECT 
                cs.name as section_name,
                COUNT(p.id) as product_count
            FROM catalog_sections cs
            LEFT JOIN products p ON p.category = cs.name
            GROUP BY cs.name
            ORDER BY cs.name;
        """)
        section_products = cursor.fetchall()
        for sp in section_products:
            print(f"  {sp['section_name']:<30} {sp['product_count']:>5} товаров")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
