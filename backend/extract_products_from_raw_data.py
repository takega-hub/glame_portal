"""
Скрипт для извлечения данных о товарах из raw_data записей продаж
и обновления полей product_name, product_article
"""
import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

load_dotenv()


async def extract_products_from_raw_data():
    """Извлекает данные о товарах из raw_data и обновляет записи"""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL не установлен в переменных окружения")
    
    conn = await asyncpg.connect(db_url)
    
    try:
        # Получаем записи с raw_data, но без названия товара
        sales_query = await conn.fetch("""
            SELECT id, product_id, raw_data
            FROM sales_records
            WHERE (product_name IS NULL OR product_article IS NULL)
               AND raw_data IS NOT NULL
               AND product_id IS NOT NULL
            LIMIT 1000
        """)
        
        print(f"Найдено {len(sales_query)} записей с raw_data для обработки\n")
        
        updated = 0
        no_data = 0
        
        for sale in sales_query:
            sale_id = sale['id']
            product_id = sale['product_id']
            raw_data = sale['raw_data']
            
            # Парсим JSON если это строка
            if isinstance(raw_data, str):
                try:
                    raw_data = json.loads(raw_data)
                except:
                    pass
            
            if not isinstance(raw_data, dict):
                no_data += 1
                continue
            
            # Пытаемся извлечь данные о товаре из различных полей
            product_name = None
            product_article = None
            product_category = None
            product_brand = None
            
            # Возможные пути к данным о товаре в raw_data
            possible_paths = [
                ('Номенклатура', 'Description'),
                ('Номенклатура', 'Наименование'),
                ('Номенклатура', 'Name'),
                ('Номенклатура_Key', 'Description'),
                ('product_name',),
                ('product', 'name'),
                ('product', 'description'),
                ('item', 'name'),
                ('item', 'description'),
            ]
            
            for path in possible_paths:
                value = raw_data
                try:
                    for key in path:
                        if isinstance(value, dict):
                            value = value.get(key)
                        else:
                            value = None
                            break
                    if value and isinstance(value, str) and value.strip():
                        product_name = value.strip()
                        break
                except:
                    continue
            
            # Ищем артикул
            article_paths = [
                ('Номенклатура', 'Артикул'),
                ('Номенклатура', 'Article'),
                ('Номенклатура', 'Код'),
                ('product_article',),
                ('product', 'article'),
                ('item', 'article'),
                ('Артикул',),
            ]
            
            for path in article_paths:
                value = raw_data
                try:
                    for key in path:
                        if isinstance(value, dict):
                            value = value.get(key)
                        else:
                            value = None
                            break
                    if value and isinstance(value, str) and value.strip():
                        product_article = value.strip()
                        break
                except:
                    continue
            
            # Если нашли хотя бы название или артикул, обновляем запись
            if product_name or product_article:
                await conn.execute("""
                    UPDATE sales_records
                    SET 
                        product_name = COALESCE(product_name, $1),
                        product_article = COALESCE(product_article, $2),
                        product_category = COALESCE(product_category, $3),
                        product_brand = COALESCE(product_brand, $4),
                        updated_at = NOW()
                    WHERE id = $5
                """, 
                    product_name,
                    product_article,
                    product_category,
                    product_brand,
                    sale_id
                )
                updated += 1
                
                if updated % 100 == 0:
                    print(f"Обновлено {updated} записей...")
            else:
                no_data += 1
        
        print(f"\nОбновлено записей: {updated}")
        print(f"Не удалось извлечь данные: {no_data}")
        
        # Финальная статистика
        check_query = await conn.fetch("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN product_name IS NOT NULL THEN 1 END) as with_name,
                COUNT(CASE WHEN product_article IS NOT NULL THEN 1 END) as with_article
            FROM sales_records
        """)
        
        stats = check_query[0]
        print(f"\nФинальная статистика:")
        print(f"  Всего записей: {stats['total']}")
        print(f"  С названием товара: {stats['with_name']} ({stats['with_name']/stats['total']*100:.1f}%)")
        print(f"  С артикулом: {stats['with_article']} ({stats['with_article']/stats['total']*100:.1f}%)")
        
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(extract_products_from_raw_data())
