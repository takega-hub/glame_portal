"""
Скрипт для проверки всех магазинов и их продаж за сегодня
"""
import asyncio
import asyncpg
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

async def check_all_stores():
    """Проверяет все магазины и их продажи за сегодня"""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL не установлен")
    
    conn = await asyncpg.connect(db_url)
    
    try:
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = datetime.now()
        
        print("=" * 80)
        print("ПРОВЕРКА ВСЕХ МАГАЗИНОВ И ПРОДАЖ ЗА СЕГОДНЯ")
        print("=" * 80)
        print(f"Период: {today_start} - {today_end}")
        print()
        
        # Получаем все магазины
        stores = await conn.fetch("""
            SELECT id, external_id, name, city, is_active
            FROM stores
            ORDER BY name
        """)
        
        print(f"Всего магазинов в базе: {len(stores)}")
        print()
        
        # UUID магазинов из 1С (по информации пользователя)
        store_uuids = {
            "6c3a8322-a2ab-11f0-96fc-fa163e4cc04e": "CENTRUM",
            "3daee4e4-a2ab-11f0-96fc-fa163e4cc04e": "YALTA",
            "8cebda58-a2ab-11f0-96fc-fa163e4cc04e": "MEGANOM"
        }
        
        # Проверяем каждый магазин
        for store in stores:
            store_name = store['name']
            store_external_id = store['external_id']
            
            print(f"\n{'='*80}")
            print(f"МАГАЗИН: {store_name}")
            print(f"{'='*80}")
            print(f"  ID: {store['id']}")
            print(f"  External ID (1C UUID): {store_external_id or 'НЕТ'}")
            print(f"  Город: {store['city'] or 'N/A'}")
            print(f"  Активен: {store['is_active']}")
            
            # Проверяем продажи за сегодня
            if store_external_id:
                sales_count = await conn.fetchval("""
                    SELECT COUNT(*)
                    FROM sales_records
                    WHERE sale_date >= $1 
                      AND sale_date <= $2
                      AND store_id = $3
                """, today_start, today_end, store_external_id)
                
                orders_count = await conn.fetchval("""
                    SELECT COUNT(DISTINCT document_id)
                    FROM sales_records
                    WHERE sale_date >= $1 
                      AND sale_date <= $2
                      AND store_id = $3
                      AND document_id IS NOT NULL
                """, today_start, today_end, store_external_id)
                
                print(f"  Продаж за сегодня: {sales_count}")
                print(f"  Чеков за сегодня: {orders_count}")
                
                # Показываем уникальные document_id
                if sales_count > 0:
                    doc_ids = await conn.fetch("""
                        SELECT DISTINCT document_id
                        FROM sales_records
                        WHERE sale_date >= $1 
                          AND sale_date <= $2
                          AND store_id = $3
                          AND document_id IS NOT NULL
                        ORDER BY document_id
                    """, today_start, today_end, store_external_id)
                    
                    if doc_ids:
                        print(f"  Document IDs:")
                        for doc in doc_ids:
                            print(f"    - {doc['document_id']}")
            else:
                print(f"  [WARNING] НЕТ external_id - продажи не будут найдены по этому магазину")
        
        # Проверяем продажи по UUID из 1С напрямую
        print(f"\n{'='*80}")
        print("ПРОВЕРКА ПРОДАЖ ПО UUID ИЗ 1С НАПРЯМУЮ:")
        print(f"{'='*80}")
        
        for uuid, name in store_uuids.items():
            sales_count = await conn.fetchval("""
                SELECT COUNT(*)
                FROM sales_records
                WHERE sale_date >= $1 
                  AND sale_date <= $2
                  AND store_id = $3
            """, today_start, today_end, uuid)
            
            orders_count = await conn.fetchval("""
                SELECT COUNT(DISTINCT document_id)
                FROM sales_records
                WHERE sale_date >= $1 
                  AND sale_date <= $2
                  AND store_id = $3
                  AND document_id IS NOT NULL
            """, today_start, today_end, uuid)
            
            print(f"\n{name} (UUID: {uuid}):")
            print(f"  Продаж: {sales_count}")
            print(f"  Чеков: {orders_count}")
            
            if sales_count > 0:
                # Показываем детали по каждому document_id
                doc_details = await conn.fetch("""
                    SELECT 
                        document_id,
                        COUNT(*) as items_count,
                        SUM(revenue) as total_revenue,
                        SUM(quantity) as total_quantity
                    FROM sales_records
                    WHERE sale_date >= $1 
                      AND sale_date <= $2
                      AND store_id = $3
                      AND document_id IS NOT NULL
                    GROUP BY document_id
                    ORDER BY document_id
                """, today_start, today_end, uuid)
                
                for doc in doc_details:
                    print(f"    Document ID: {doc['document_id']}")
                    print(f"      Товаров: {doc['items_count']}")
                    print(f"      Выручка: {doc['total_revenue']:.2f} RUR")
                    print(f"      Количество: {doc['total_quantity']:.2f}")
        
        # Проверяем все уникальные store_id в продажах за сегодня
        print(f"\n{'='*80}")
        print("ВСЕ УНИКАЛЬНЫЕ STORE_ID В ПРОДАЖАХ ЗА СЕГОДНЯ:")
        print(f"{'='*80}")
        
        all_store_ids = await conn.fetch("""
            SELECT DISTINCT store_id, COUNT(*) as sales_count
            FROM sales_records
            WHERE sale_date >= $1 
              AND sale_date <= $2
              AND store_id IS NOT NULL
            GROUP BY store_id
            ORDER BY sales_count DESC
        """, today_start, today_end)
        
        for row in all_store_ids:
            store_id = row['store_id']
            # Проверяем, есть ли этот store_id в таблице stores
            store_info = await conn.fetchrow("""
                SELECT name, external_id FROM stores WHERE external_id = $1
            """, store_id)
            
            store_name = store_info['name'] if store_info else 'НЕ НАЙДЕН В STORES'
            print(f"  {store_id}: {store_name} ({row['sales_count']} продаж)")
        
        print()
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_all_stores())
