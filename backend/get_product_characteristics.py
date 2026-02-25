"""
Скрипт для получения всех уникальных значений характеристик товаров
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

def get_characteristics():
    """Получить все уникальные значения характеристик"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Получаем все товары с specifications
        cursor.execute("""
            SELECT specifications 
            FROM products 
            WHERE specifications IS NOT NULL 
            AND is_active = true;
        """)
        products = cursor.fetchall()
        
        # Собираем все характеристики
        characteristics = {}
        
        for product in products:
            if product['specifications']:
                specs = product['specifications']
                if isinstance(specs, str):
                    specs = json.loads(specs)
                
                if isinstance(specs, dict):
                    for key, value in specs.items():
                        # Пропускаем служебные поля
                        if key in ['parent_external_id', 'characteristic_id', 'quantity', 'barcode']:
                            continue
                        
                        if key not in characteristics:
                            characteristics[key] = set()
                        
                        if value and isinstance(value, (str, int, float)):
                            characteristics[key].add(str(value))
        
        # Преобразуем в список и сортируем
        result = {}
        for key, values in characteristics.items():
            result[key] = sorted(list(values))
        
        print("Характеристики товаров:")
        print("=" * 80)
        for key, values in sorted(result.items()):
            print(f"\n{key}:")
            for value in values[:20]:  # Показываем первые 20 значений
                print(f"  - {value}")
            if len(values) > 20:
                print(f"  ... и еще {len(values) - 20} значений")
        
        cursor.close()
        conn.close()
        
        return result
        
    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return {}

if __name__ == "__main__":
    get_characteristics()
