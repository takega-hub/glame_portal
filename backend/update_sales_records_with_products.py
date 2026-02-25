"""
Скрипт для обновления существующих записей в sales_records данными о товарах из таблицы Product
Заполняет пустые поля product_name, product_article, product_category, product_brand
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()


async def update_sales_records_with_products():
    """Обновляет записи в sales_records данными о товарах из таблицы Product"""
    # Получаем параметры подключения из переменных окружения
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL не установлен в переменных окружения")
    
    conn = await asyncpg.connect(db_url)
    
    try:
        # Получаем все товары из таблицы Product
        products_query = await conn.fetch("""
            SELECT external_id, article, name, category, brand 
            FROM products 
            WHERE external_id IS NOT NULL OR article IS NOT NULL
        """)
        
        # Создаем словари для быстрого поиска
        products_by_external_id = {}
        products_by_article = {}
        
        for product in products_query:
            external_id = product['external_id']
            article = product['article']
            
            product_data = {
                'name': product['name'],
                'article': article,
                'category': product['category'],
                'brand': product['brand']
            }
            
            if external_id:
                products_by_external_id[external_id] = product_data
            if article:
                products_by_article[article] = product_data
        
        print(f"Загружено {len(products_by_external_id)} товаров по external_id")
        print(f"Загружено {len(products_by_article)} товаров по артикулу")
        
        # Получаем записи продаж с пустыми полями товара (без лимита, обрабатываем все)
        sales_query = await conn.fetch("""
            SELECT id, product_id, product_article, product_name, product_article as current_article
            FROM sales_records
            WHERE (product_name IS NULL OR product_article IS NULL)
               AND (product_id IS NOT NULL OR product_article IS NOT NULL)
        """)
        
        print(f"\nНайдено {len(sales_query)} записей с пустыми полями товара")
        
        updated = 0
        not_found = 0
        batch_size = 1000
        total_batches = (len(sales_query) + batch_size - 1) // batch_size
        
        print(f"Обработка {len(sales_query)} записей в {total_batches} батчах по {batch_size} записей...\n")
        
        for batch_num in range(0, len(sales_query), batch_size):
            batch = sales_query[batch_num:batch_num + batch_size]
            batch_updated = 0
            batch_not_found = 0
            
            for sale in batch:
                sale_id = sale['id']
                product_id_1c = sale['product_id']
                product_article = sale['current_article']
                
                # Ищем товар по product_id (external_id) или по артикулу
                product_data = None
                if product_id_1c and product_id_1c in products_by_external_id:
                    product_data = products_by_external_id[product_id_1c]
                elif product_article and product_article in products_by_article:
                    product_data = products_by_article[product_article]
                
                if product_data:
                    # Обновляем запись
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
                        product_data['name'],
                        product_data['article'],
                        product_data['category'],
                        product_data['brand'],
                        sale_id
                    )
                    updated += 1
                    batch_updated += 1
                else:
                    not_found += 1
                    batch_not_found += 1
            
            # Показываем прогресс каждые 1000 записей
            if (batch_num // batch_size + 1) % 1 == 0 or batch_num + batch_size >= len(sales_query):
                print(f"Обработано {min(batch_num + batch_size, len(sales_query))}/{len(sales_query)} записей... "
                      f"(обновлено: {updated}, не найдено: {not_found})")
        
        print(f"\nОбновлено записей: {updated}")
        print(f"Не найдено товаров: {not_found}")
        
        # Проверяем результат
        check_query = await conn.fetch("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN product_name IS NOT NULL THEN 1 END) as with_name,
                COUNT(CASE WHEN product_article IS NOT NULL THEN 1 END) as with_article,
                COUNT(CASE WHEN product_category IS NOT NULL THEN 1 END) as with_category,
                COUNT(CASE WHEN product_brand IS NOT NULL THEN 1 END) as with_brand
            FROM sales_records
        """)
        
        stats = check_query[0]
        print(f"\nСтатистика по таблице sales_records:")
        print(f"  Всего записей: {stats['total']}")
        print(f"  С названием товара: {stats['with_name']} ({stats['with_name']/stats['total']*100:.1f}%)")
        print(f"  С артикулом: {stats['with_article']} ({stats['with_article']/stats['total']*100:.1f}%)")
        print(f"  С категорией: {stats['with_category']} ({stats['with_category']/stats['total']*100:.1f}%)")
        print(f"  С брендом: {stats['with_brand']} ({stats['with_brand']/stats['total']*100:.1f}%)")
        
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(update_sales_records_with_products())
