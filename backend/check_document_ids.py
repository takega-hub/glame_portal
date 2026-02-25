"""
Скрипт для проверки document_id в продажах за сегодня
Помогает найти проблему с подсчетом чеков
"""
import asyncio
import asyncpg
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

async def check_document_ids():
    """Проверяет document_id в продажах за сегодня"""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL не установлен в переменных окружения")
    
    conn = await asyncpg.connect(db_url)
    
    try:
        # Получаем сегодняшнюю дату
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = datetime.now()
        
        print("=" * 80)
        print("ПРОВЕРКА DOCUMENT_ID В ПРОДАЖАХ ЗА СЕГОДНЯ")
        print("=" * 80)
        print(f"Период: {today_start} - {today_end}")
        print()
        
        # Получаем UUID магазина CENTRUM
        store_row = await conn.fetchrow(
            "SELECT id, external_id, name FROM stores WHERE name = $1",
            "CENTRUM"
        )
        
        if not store_row:
            print("Магазин CENTRUM не найден в базе")
            return
        
        centrum_external_id = store_row['external_id']
        
        print(f"Магазин CENTRUM найден:")
        print(f"  ID: {store_row['id']}")
        print(f"  External ID (1C UUID): {centrum_external_id}")
        print(f"  Название: {store_row['name']}")
        print()
        
        # Получаем все продажи за сегодня для CENTRUM
        rows = await conn.fetch("""
            SELECT 
                document_id,
                external_id,
                sale_date,
                revenue,
                quantity,
                product_name
            FROM sales_records
            WHERE sale_date >= $1 
              AND sale_date <= $2
              AND store_id = $3
            ORDER BY document_id, sale_date
        """, today_start, today_end, centrum_external_id)
        
        print(f"Всего записей продаж за сегодня для CENTRUM: {len(rows)}")
        print()
        
        # Группируем по document_id
        document_ids = {}
        null_documents = []
        
        for row in rows:
            doc_id = row['document_id']
            if doc_id:
                if doc_id not in document_ids:
                    document_ids[doc_id] = []
                document_ids[doc_id].append({
                    'external_id': row['external_id'],
                    'sale_date': row['sale_date'],
                    'revenue': row['revenue'],
                    'quantity': row['quantity'],
                    'product_name': row['product_name']
                })
            else:
                null_documents.append({
                    'external_id': row['external_id'],
                    'sale_date': row['sale_date'],
                    'revenue': row['revenue'],
                    'quantity': row['quantity'],
                    'product_name': row['product_name']
                })
        
        print(f"Уникальных document_id: {len(document_ids)}")
        print(f"Записей с NULL document_id: {len(null_documents)}")
        print()
        
        # Выводим детали по каждому document_id
        print("=" * 80)
        print("ДЕТАЛИ ПО КАЖДОМУ DOCUMENT_ID:")
        print("=" * 80)
        for doc_id, records in document_ids.items():
            print(f"\nDocument ID: {doc_id}")
            print(f"  Количество записей: {len(records)}")
            total_revenue = sum(r['revenue'] for r in records)
            total_quantity = sum(r['quantity'] for r in records)
            print(f"  Общая выручка: {total_revenue:.2f} ₽")
            print(f"  Общее количество: {total_quantity:.2f}")
            print(f"  Товары:")
            for record in records:
                print(f"    - {record['product_name'] or 'N/A'} (артикул: {record['external_id']})")
                print(f"      Количество: {record['quantity']}, Выручка: {record['revenue']:.2f} ₽")
                print(f"      Дата: {record['sale_date']}")
        
        if null_documents:
            print("\n" + "=" * 80)
            print("ЗАПИСИ С NULL DOCUMENT_ID:")
            print("=" * 80)
            for record in null_documents:
                print(f"  External ID: {record['external_id']}")
                print(f"  Товар: {record['product_name'] or 'N/A'}")
                print(f"  Количество: {record['quantity']}, Выручка: {record['revenue']:.2f} ₽")
                print(f"  Дата: {record['sale_date']}")
                print()
        
        # Проверяем подсчет через SQL
        print("\n" + "=" * 80)
        print("ПОДСЧЕТ ЧЕРЕЗ SQL (как в API):")
        print("=" * 80)
        
        count_row = await conn.fetchrow("""
            SELECT COUNT(DISTINCT document_id) as total_orders
            FROM sales_records
            WHERE sale_date >= $1 
              AND sale_date <= $2
              AND store_id = $3
              AND document_id IS NOT NULL
        """, today_start, today_end, centrum_external_id)
        
        sql_count = count_row['total_orders'] if count_row else 0
        
        print(f"Количество уникальных document_id (без NULL): {sql_count}")
        print()
        
        # Проверяем с NULL
        count_with_null_row = await conn.fetchrow("""
            SELECT COUNT(DISTINCT document_id) as total_orders
            FROM sales_records
            WHERE sale_date >= $1 
              AND sale_date <= $2
              AND store_id = $3
        """, today_start, today_end, centrum_external_id)
        
        sql_count_with_null = count_with_null_row['total_orders'] if count_with_null_row else 0
        
        print(f"Количество уникальных document_id (с NULL): {sql_count_with_null}")
        print()
        
        # Проверяем, есть ли записи с одинаковым external_id но разными document_id
        print("=" * 80)
        print("ПРОВЕРКА НА ДУБЛИКАТЫ:")
        print("=" * 80)
        
        duplicates = await conn.fetch("""
            SELECT 
                external_id,
                COUNT(DISTINCT document_id) as doc_count,
                string_agg(DISTINCT document_id, ', ') as doc_ids
            FROM sales_records
            WHERE sale_date >= $1 
              AND sale_date <= $2
              AND store_id = $3
              AND external_id IS NOT NULL
            GROUP BY external_id
            HAVING COUNT(DISTINCT document_id) > 1
        """, today_start, today_end, centrum_external_id)
        
        if duplicates:
            print(f"Найдено {len(duplicates)} external_id с разными document_id:")
            for dup in duplicates:
                print(f"  External ID: {dup['external_id']}")
                print(f"    Количество разных document_id: {dup['doc_count']}")
                print(f"    Document IDs: {dup['doc_ids']}")
        else:
            print("Дубликатов не найдено")
        
        print()
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_document_ids())
