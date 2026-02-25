"""
Обновить пути изображений для товара 71136-S на локальные пути
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

def update_images():
    """Обновить пути изображений"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("=" * 80)
        print("ОБНОВЛЕНИЕ ПУТЕЙ ИЗОБРАЖЕНИЙ ДЛЯ ТОВАРА 71136-S")
        print("=" * 80)
        print()
        
        # Ищем товар
        cursor.execute("""
            SELECT 
                id,
                name,
                article,
                images
            FROM products
            WHERE article = '71136-S';
        """)
        product = cursor.fetchone()
        
        if not product:
            print("Товар с артикулом 71136-S не найден")
            return
        
        print(f"Товар: {product['name']}")
        print(f"Текущие изображения: {product['images']}")
        print()
        
        # Новые пути (локальные)
        new_images = [
            "/static/product_images/ec2f3800bbf311f09138fa163e4cc04e_277b494ad0ed11f08e4dfa163e4cc04e.jpeg",
            "/static/product_images/ec2f3800bbf311f09138fa163e4cc04e_27b1896ad0ed11f08e4dfa163e4cc04e.jpeg"
        ]
        
        # Обновляем
        cursor.execute("""
            UPDATE products
            SET images = %s
            WHERE id = %s;
        """, (json.dumps(new_images), product['id']))
        conn.commit()
        
        print("Обновлено на:")
        for img in new_images:
            print(f"  - {img}")
        print()
        print("[OK] Изображения обновлены в базе данных")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    update_images()
