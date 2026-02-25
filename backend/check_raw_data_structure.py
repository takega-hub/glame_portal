"""
Скрипт для проверки структуры raw_data в записях продаж
"""
import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

load_dotenv()


async def check_raw_data_structure():
    """Проверяет структуру raw_data"""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL не установлен в переменных окружения")
    
    conn = await asyncpg.connect(db_url)
    
    try:
        # Получаем несколько примеров raw_data
        sales_query = await conn.fetch("""
            SELECT id, product_id, raw_data
            FROM sales_records
            WHERE raw_data IS NOT NULL
               AND (product_name IS NULL OR product_article IS NULL)
            LIMIT 5
        """)
        
        print(f"Проверка структуры raw_data для {len(sales_query)} записей:\n")
        
        for i, sale in enumerate(sales_query, 1):
            print(f"\n{'='*80}")
            print(f"Запись #{i} (ID: {sale['id']}, product_id: {sale['product_id']})")
            print(f"{'='*80}")
            
            raw_data = sale['raw_data']
            
            # Если это строка, пытаемся распарсить
            if isinstance(raw_data, str):
                try:
                    raw_data = json.loads(raw_data)
                except:
                    print(f"raw_data (строка, не JSON): {raw_data[:200]}...")
                    continue
            
            # Выводим структуру
            if isinstance(raw_data, dict):
                print("Ключи в raw_data:")
                for key in list(raw_data.keys())[:20]:  # Первые 20 ключей
                    value = raw_data[key]
                    if isinstance(value, dict):
                        print(f"  {key}: {{dict с ключами: {list(value.keys())[:5]}}}")
                    elif isinstance(value, list):
                        print(f"  {key}: [list, длина: {len(value)}]")
                    else:
                        value_str = str(value)[:100]
                        print(f"  {key}: {value_str}")
                
                # Ищем возможные поля с названием товара
                print("\nПоиск полей с названием товара:")
                for key in raw_data.keys():
                    if any(word in key.lower() for word in ['name', 'наимен', 'опис', 'description', 'товар', 'product']):
                        print(f"  Найдено поле: {key} = {str(raw_data[key])[:100]}")
            else:
                print(f"raw_data тип: {type(raw_data)}, значение: {str(raw_data)[:200]}")
        
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(check_raw_data_structure())
