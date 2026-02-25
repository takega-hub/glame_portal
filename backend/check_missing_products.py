"""
Скрипт для проверки записей продаж без названия товара и артикула
Показывает примеры записей и возможные причины
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()


async def check_missing_products():
    """Проверяет записи продаж без данных о товарах"""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL не установлен в переменных окружения")
    
    conn = await asyncpg.connect(db_url)
    
    try:
        # Получаем записи без названия товара или артикула
        sales_query = await conn.fetch("""
            SELECT 
                id, 
                sale_date,
                product_id, 
                product_article, 
                product_name,
                store_id,
                revenue,
                quantity
            FROM sales_records
            WHERE (product_name IS NULL OR product_article IS NULL)
               AND (product_id IS NOT NULL OR product_article IS NOT NULL)
            ORDER BY sale_date DESC
            LIMIT 50
        """)
        
        print(f"\nНайдено {len(sales_query)} примеров записей без данных о товаре (показаны первые 50):\n")
        print(f"{'Дата':<12} {'Product ID (1C)':<40} {'Артикул':<20} {'Название':<30} {'Магазин':<40}")
        print(f"{'-'*150}")
        
        for sale in sales_query:
            product_id = sale['product_id'] or 'NULL'
            article = sale['product_article'] or 'NULL'
            name = sale['product_name'] or 'NULL'
            store_id = sale['store_id'] or 'NULL'
            date_str = sale['sale_date'].strftime('%Y-%m-%d') if sale['sale_date'] else 'N/A'
            
            print(f"{date_str:<12} {str(product_id)[:38]:<40} {str(article)[:18]:<20} {str(name)[:28]:<30} {str(store_id)[:38]:<40}")
        
        # Проверяем, есть ли эти product_id в таблице Product
        if sales_query:
            product_ids = [s['product_id'] for s in sales_query if s['product_id']]
            articles = [s['product_article'] for s in sales_query if s['product_article']]
            
            if product_ids:
                products_check = await conn.fetch("""
                    SELECT external_id, article, name
                    FROM products
                    WHERE external_id = ANY($1::text[])
                """, product_ids)
                
                print(f"\n\nПроверка product_id в таблице Product:")
                print(f"  Искали {len(set(product_ids))} уникальных product_id")
                print(f"  Найдено в Product: {len(products_check)}")
                
                if products_check:
                    print(f"\n  Примеры найденных товаров:")
                    for p in products_check[:10]:
                        print(f"    {p['external_id']} -> {p['name']} ({p['article']})")
            
            if articles:
                articles_check = await conn.fetch("""
                    SELECT external_id, article, name
                    FROM products
                    WHERE article = ANY($1::text[])
                """, [a for a in articles if a])
                
                print(f"\n\nПроверка артикулов в таблице Product:")
                print(f"  Искали {len(set([a for a in articles if a]))} уникальных артикулов")
                print(f"  Найдено в Product: {len(articles_check)}")
                
                if articles_check:
                    print(f"\n  Примеры найденных товаров:")
                    for p in articles_check[:10]:
                        print(f"    {p['article']} -> {p['name']} (external_id: {p['external_id']})")
        
        # Статистика по raw_data - возможно там есть данные о товаре
        raw_data_check = await conn.fetch("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN raw_data IS NOT NULL THEN 1 END) as with_raw_data
            FROM sales_records
            WHERE (product_name IS NULL OR product_article IS NULL)
               AND (product_id IS NOT NULL OR product_article IS NOT NULL)
        """)
        
        stats = raw_data_check[0]
        print(f"\n\nСтатистика по raw_data:")
        print(f"  Всего записей без товара: {stats['total']}")
        print(f"  С raw_data: {stats['with_raw_data']}")
        
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(check_missing_products())
