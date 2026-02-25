"""
Проверка товара 71136-S и его изображений
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

def check_product():
    """Проверка товара"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        print("=" * 80)
        print("ПРОВЕРКА ТОВАРА 71136-S")
        print("=" * 80)
        print()
        
        # Ищем товар по артикулу
        cursor.execute("""
            SELECT 
                id,
                name,
                article,
                external_id,
                images,
                specifications,
                sync_metadata
            FROM products
            WHERE article = '71136-S';
        """)
        product = cursor.fetchone()
        
        if not product:
            print("Товар с артикулом 71136-S не найден в базе")
            return
        
        print(f"Найден товар: {product['name']}")
        print(f"  ID: {product['id']}")
        print(f"  Артикул: {product['article']}")
        print(f"  External ID: {product['external_id']}")
        print()
        
        # Проверяем изображения
        print("ТЕКУЩИЕ ИЗОБРАЖЕНИЯ:")
        print("-" * 80)
        if product['images']:
            print(f"  В поле images: {len(product['images'])} изображений")
            for img in product['images']:
                print(f"    - {img}")
        else:
            print("  В поле images: Нет изображений")
        print()
        
        # Проверяем specifications
        print("SPECIFICATIONS:")
        print("-" * 80)
        if product['specifications']:
            specs = product['specifications']
            print(f"  Тип: {type(specs)}")
            if isinstance(specs, dict):
                for key, value in specs.items():
                    if 'image' in key.lower() or 'картинка' in key.lower():
                        print(f"  {key}: {value}")
        else:
            print("  Нет specifications")
        print()
        
        # Проверяем sync_metadata
        print("SYNC_METADATA:")
        print("-" * 80)
        if product['sync_metadata']:
            metadata = product['sync_metadata']
            print(f"  Тип: {type(metadata)}")
            if isinstance(metadata, dict):
                for key, value in metadata.items():
                    if 'image' in key.lower() or 'картинка' in key.lower():
                        print(f"  {key}: {value}")
        else:
            print("  Нет sync_metadata")
        print()
        
        # Проверяем, есть ли основной товар (родитель)
        print("ПОИСК ОСНОВНОГО ТОВАРА (РОДИТЕЛЯ):")
        print("-" * 80)
        if product['specifications'] and isinstance(product['specifications'], dict):
            parent_id = product['specifications'].get('parent_external_id')
            if parent_id:
                print(f"  Parent external_id: {parent_id}")
                cursor.execute("""
                    SELECT 
                        id,
                        name,
                        article,
                        images
                    FROM products
                    WHERE external_id = %s;
                """, (parent_id,))
                parent = cursor.fetchone()
                if parent:
                    print(f"  Найден родитель: {parent['name']}")
                    print(f"    Артикул: {parent['article']}")
                    if parent['images']:
                        print(f"    Изображений: {len(parent['images'])}")
                    else:
                        print(f"    Изображений: Нет")
                else:
                    print("  Родитель не найден")
            else:
                print("  Parent external_id не указан")
        else:
            print("  Нет specifications для проверки родителя")
        print()
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_product()
