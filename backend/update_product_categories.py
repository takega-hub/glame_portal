"""
Скрипт для обновления категорий у существующих товаров
Устанавливает категорию SALE или AGAFI для товаров без категории
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

def update_categories():
    """Обновить категории у товаров"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Получаем разделы SALE и AGAFI
        cursor.execute("""
            SELECT name, external_id 
            FROM catalog_sections 
            WHERE name IN ('SALE', 'AGAFI', 'AGafi')
            ORDER BY name
            LIMIT 1;
        """)
        section = cursor.fetchone()
        
        if not section:
            print("[ERROR] Разделы SALE или AGAFI не найдены в базе данных")
            cursor.close()
            conn.close()
            return
        
        default_category = section['name']
        print(f"[INFO] Используется раздел по умолчанию: {default_category}")
        
        # Находим товары без категории
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM products 
            WHERE category IS NULL OR category = '';
        """)
        result = cursor.fetchone()
        products_count = result['count']
        
        print(f"[INFO] Найдено {products_count} товаров без категории")
        
        if products_count == 0:
            print("[INFO] Все товары уже имеют категории")
            cursor.close()
            conn.close()
            return
        
        # Обновляем категории
        cursor.execute("""
            UPDATE products 
            SET category = %s
            WHERE category IS NULL OR category = '';
        """, (default_category,))
        
        updated_count = cursor.rowcount
        conn.commit()
        
        print(f"[OK] Обновлено {updated_count} товаров с категорией '{default_category}'")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"[ERROR] Ошибка при обновлении категорий: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    update_categories()
