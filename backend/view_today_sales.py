"""
Скрипт для просмотра продаж за сегодня, отсортированных по магазинам
"""
import asyncio
import asyncpg
import os
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()


async def view_today_sales():
    """Показывает продажи за сегодня, отсортированные по магазинам"""
    # Получаем параметры подключения из переменных окружения
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL не установлен в переменных окружения")
    
    conn = await asyncpg.connect(db_url)
    
    try:
        # Получаем названия магазинов
        stores_query = await conn.fetch("SELECT external_id, name FROM stores WHERE external_id IS NOT NULL")
        store_names = {row['external_id']: row['name'] for row in stores_query}
        
        # Получаем продажи за сегодня
        today = date.today()
        sales_query = """
            SELECT 
                id,
                sale_date,
                external_id,
                document_id,
                store_id,
                customer_id,
                product_id,
                product_name,
                product_article,
                product_category,
                product_brand,
                product_type,
                revenue,
                quantity,
                channel,
                created_at
            FROM sales_records
            WHERE DATE(sale_date) = $1
            ORDER BY store_id, sale_date DESC
            LIMIT 100
        """
        
        sales = await conn.fetch(sales_query, today)
        
        print(f"\n{'='*120}")
        print(f"ПРОДАЖИ ЗА СЕГОДНЯ ({today})")
        print(f"{'='*120}\n")
        print(f"Всего записей: {len(sales)}\n")
        
        if not sales:
            print("Нет продаж за сегодня")
            return
        
        # Группируем по магазинам
        by_store = {}
        for sale in sales:
            store_id = sale['store_id'] or 'unknown'
            store_name = store_names.get(store_id, store_id)
            
            if store_id not in by_store:
                by_store[store_id] = {
                    'name': store_name,
                    'sales': [],
                    'total_revenue': 0.0,
                    'total_quantity': 0.0,
                    'count': 0
                }
            
            by_store[store_id]['sales'].append(sale)
            by_store[store_id]['total_revenue'] += float(sale['revenue'] or 0.0)
            by_store[store_id]['total_quantity'] += float(sale['quantity'] or 0.0)
            by_store[store_id]['count'] += 1
        
        # Выводим по магазинам
        for store_id, store_data in sorted(by_store.items(), key=lambda x: x[1]['total_revenue'], reverse=True):
            print(f"\n{'-'*120}")
            print(f"МАГАЗИН: {store_data['name']} ({store_id})")
            print(f"{'-'*120}")
            print(f"Всего продаж: {store_data['count']}")
            print(f"Общая выручка: {store_data['total_revenue']:,.2f} RUR")
            print(f"Общее количество: {store_data['total_quantity']:,.2f}")
            print(f"\nДетали продаж:")
            print(f"{'Дата/Время':<20} {'Товар':<30} {'Артикул':<15} {'Кол-во':<10} {'Выручка':<15} {'Канал':<10}")
            print(f"{'-'*120}")
            
            for sale in store_data['sales'][:20]:  # Показываем первые 20 записей
                sale_time = sale['sale_date'].strftime('%Y-%m-%d %H:%M:%S') if sale['sale_date'] else 'N/A'
                product_name = (sale['product_name'] or 'N/A')[:28]
                article = (sale['product_article'] or 'N/A')[:13]
                quantity = f"{sale['quantity']:.2f}" if sale['quantity'] else '0.00'
                revenue = f"{sale['revenue']:,.2f}" if sale['revenue'] else '0.00'
                channel = sale['channel'] or 'N/A'
                
                print(f"{sale_time:<20} {product_name:<30} {article:<15} {quantity:<10} {revenue:<15} {channel:<10}")
            
            if len(store_data['sales']) > 20:
                print(f"... и еще {len(store_data['sales']) - 20} записей")
        
        print(f"\n{'='*120}\n")
        
        # Общая статистика
        total_revenue = sum(s['total_revenue'] for s in by_store.values())
        total_quantity = sum(s['total_quantity'] for s in by_store.values())
        total_count = sum(s['count'] for s in by_store.values())
        
        print(f"ОБЩАЯ СТАТИСТИКА:")
        print(f"  Всего магазинов: {len(by_store)}")
        print(f"  Всего продаж: {total_count}")
        print(f"  Общая выручка: {total_revenue:,.2f} RUR")
        print(f"  Общее количество: {total_quantity:,.2f}")
        print(f"\n{'='*120}\n")
        
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(view_today_sales())
