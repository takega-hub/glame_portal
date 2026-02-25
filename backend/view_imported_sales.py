"""
Скрипт для просмотра импортированных данных о продажах из исторического Excel файла
"""
import asyncio
import asyncpg
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import json
from datetime import datetime

# Исправление кодировки для Windows
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# Добавляем корневую директорию в путь для импорта
sys.path.insert(0, str(Path(__file__).parent))

# Загружаем переменные окружения
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)


async def view_imported_sales(limit: int = 20, batch_id_filter: str = None):
    """Просмотр импортированных данных о продажах"""
    
    # Параметры подключения
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "5433"))
    DB_USER = os.getenv("DB_USER", "glame_user")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "glame_password")
    DB_NAME = os.getenv("DB_NAME", "glame_db")
    
    print(f"Подключение к БД: {DB_HOST}:{DB_PORT}/{DB_NAME} как {DB_USER}")
    
    try:
        conn = await asyncpg.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        
        print("[OK] Подключение установлено\n")
        
        # 1. Статистика по таблице
        print("=" * 80)
        print("СТАТИСТИКА ПО ТАБЛИЦЕ sales_records")
        print("=" * 80)
        
        total_count = await conn.fetchval("SELECT COUNT(*) FROM sales_records")
        historical_count = await conn.fetchval("""
            SELECT COUNT(*) FROM sales_records 
            WHERE sync_batch_id LIKE 'historical_import%'
        """)
        
        print(f"Всего записей в таблице: {total_count:,}")
        print(f"Исторических записей (из Excel): {historical_count:,}")
        print()
        
        # 2. Структура таблицы
        print("=" * 80)
        print("СТРУКТУРА ТАБЛИЦЫ sales_records")
        print("=" * 80)
        
        columns = await conn.fetch("""
            SELECT 
                column_name,
                data_type,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_name = 'sales_records'
            ORDER BY ordinal_position
        """)
        
        print(f"{'Колонка':<30} {'Тип':<25} {'NULL':<8} {'По умолчанию'}")
        print("-" * 80)
        for col in columns:
            default = str(col['column_default'])[:30] if col['column_default'] else '-'
            print(f"{col['column_name']:<30} {col['data_type']:<25} {col['is_nullable']:<8} {default}")
        print()
        
        # 3. Статистика по историческим данным
        print("=" * 80)
        print("СТАТИСТИКА ПО ИСТОРИЧЕСКИМ ДАННЫМ")
        print("=" * 80)
        
        stats = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total,
                COUNT(DISTINCT product_article) as unique_articles,
                COUNT(DISTINCT product_id) as matched_products,
                COUNT(*) FILTER (WHERE product_id IS NOT NULL) as with_product_id,
                COUNT(*) FILTER (WHERE product_id IS NULL) as without_product_id,
                SUM(quantity) as total_quantity,
                SUM(revenue) as total_revenue,
                MIN(sale_date) as min_date,
                MAX(sale_date) as max_date
            FROM sales_records
            WHERE sync_batch_id LIKE 'historical_import%'
        """)
        
        if stats:
            print(f"Всего записей: {stats['total']:,}")
            print(f"Уникальных артикулов: {stats['unique_articles']:,}")
            print(f"Товаров найдено в каталоге: {stats['with_product_id']:,}")
            print(f"Товаров не найдено: {stats['without_product_id']:,}")
            print(f"Общее количество проданных единиц: {stats['total_quantity']:,.0f}")
            print(f"Общая выручка: {stats['total_revenue']:,.2f} ₽")
            print(f"Период: {stats['min_date'].strftime('%Y-%m-%d') if stats['min_date'] else 'N/A'} - {stats['max_date'].strftime('%Y-%m-%d') if stats['max_date'] else 'N/A'}")
        print()
        
        # 4. Топ товаров по количеству продаж
        print("=" * 80)
        print("ТОП-10 ТОВАРОВ ПО КОЛИЧЕСТВУ ПРОДАЖ")
        print("=" * 80)
        
        top_quantity = await conn.fetch("""
            SELECT 
                product_name,
                product_article,
                product_category,
                product_brand,
                COUNT(*) as sales_count,
                SUM(quantity) as total_quantity,
                SUM(revenue) as total_revenue
            FROM sales_records
            WHERE sync_batch_id LIKE 'historical_import%'
            GROUP BY product_name, product_article, product_category, product_brand
            ORDER BY total_quantity DESC
            LIMIT 10
        """)
        
        print(f"{'Товар':<40} {'Артикул':<15} {'Категория':<20} {'Кол-во':<12} {'Выручка':<15}")
        print("-" * 80)
        for row in top_quantity:
            name = (row['product_name'] or 'N/A')[:38]
            article = (row['product_article'] or 'N/A')[:13]
            category = (row['product_category'] or 'N/A')[:18]
            qty = f"{row['total_quantity']:,.0f}"
            rev = f"{row['total_revenue']:,.2f} ₽"
            print(f"{name:<40} {article:<15} {category:<20} {qty:<12} {rev:<15}")
        print()
        
        # 5. Примеры импортированных записей
        print("=" * 80)
        print(f"ПРИМЕРЫ ИМПОРТИРОВАННЫХ ЗАПИСЕЙ (первые {limit})")
        print("=" * 80)
        
        where_clause = "WHERE sync_batch_id LIKE 'historical_import%'"
        if batch_id_filter:
            where_clause = f"WHERE sync_batch_id = '{batch_id_filter}'"
        
        samples = await conn.fetch(f"""
            SELECT 
                sale_date,
                product_name,
                product_article,
                product_category,
                product_brand,
                quantity,
                revenue,
                channel,
                external_id,
                product_id,
                raw_data
            FROM sales_records
            {where_clause}
            ORDER BY sale_date DESC, product_name
            LIMIT $1
        """, limit)
        
        for i, row in enumerate(samples, 1):
            print(f"\n--- Запись #{i} ---")
            print(f"Дата продажи: {row['sale_date'].strftime('%Y-%m-%d') if row['sale_date'] else 'N/A'}")
            print(f"Товар: {row['product_name'] or 'N/A'}")
            print(f"Артикул: {row['product_article'] or 'N/A'}")
            print(f"Категория: {row['product_category'] or 'N/A'}")
            print(f"Бренд: {row['product_brand'] or 'N/A'}")
            print(f"Количество: {row['quantity']:,.2f}")
            print(f"Выручка: {row['revenue']:,.2f} ₽")
            print(f"Канал: {row['channel'] or 'N/A'}")
            print(f"Product ID (из каталога): {row['product_id'] or 'НЕ НАЙДЕН'}")
            print(f"External ID: {row['external_id'] or 'N/A'}")
            if row['raw_data']:
                raw = json.loads(row['raw_data']) if isinstance(row['raw_data'], str) else row['raw_data']
                print(f"Источник: {raw.get('source', 'N/A')}")
                if 'month_label' in raw:
                    print(f"Месяц из файла: {raw['month_label']}")
        
        print()
        
        # 6. Статистика по категориям
        print("=" * 80)
        print("СТАТИСТИКА ПО КАТЕГОРИЯМ")
        print("=" * 80)
        
        categories = await conn.fetch("""
            SELECT 
                product_category,
                COUNT(*) as sales_count,
                SUM(quantity) as total_quantity,
                SUM(revenue) as total_revenue
            FROM sales_records
            WHERE sync_batch_id LIKE 'historical_import%'
                AND product_category IS NOT NULL
            GROUP BY product_category
            ORDER BY total_revenue DESC
            LIMIT 10
        """)
        
        print(f"{'Категория':<30} {'Записей':<12} {'Кол-во':<15} {'Выручка':<15}")
        print("-" * 80)
        for row in categories:
            cat = (row['product_category'] or 'N/A')[:28]
            count = f"{row['sales_count']:,}"
            qty = f"{row['total_quantity']:,.0f}"
            rev = f"{row['total_revenue']:,.2f} ₽"
            print(f"{cat:<30} {count:<12} {qty:<15} {rev:<15}")
        print()
        
        # 7. Статистика по месяцам
        print("=" * 80)
        print("СТАТИСТИКА ПО МЕСЯЦАМ")
        print("=" * 80)
        
        months = await conn.fetch("""
            SELECT 
                DATE_TRUNC('month', sale_date) as month,
                COUNT(*) as sales_count,
                SUM(quantity) as total_quantity,
                SUM(revenue) as total_revenue
            FROM sales_records
            WHERE sync_batch_id LIKE 'historical_import%'
                AND sale_date IS NOT NULL
            GROUP BY DATE_TRUNC('month', sale_date)
            ORDER BY month
        """)
        
        print(f"{'Месяц':<20} {'Записей':<12} {'Кол-во':<15} {'Выручка':<15}")
        print("-" * 80)
        for row in months:
            month_str = row['month'].strftime('%Y-%m') if row['month'] else 'N/A'
            count = f"{row['sales_count']:,}"
            qty = f"{row['total_quantity']:,.0f}"
            rev = f"{row['total_revenue']:,.2f} ₽"
            print(f"{month_str:<20} {count:<12} {qty:<15} {rev:<15}")
        print()
        
        # 8. Товары, которые не найдены в каталоге
        print("=" * 80)
        print("ПРИМЕРЫ ТОВАРОВ, НЕ НАЙДЕННЫХ В КАТАЛОГЕ (первые 10)")
        print("=" * 80)
        
        unmatched = await conn.fetch("""
            SELECT DISTINCT
                product_name,
                product_article,
                COUNT(*) as sales_count,
                SUM(quantity) as total_quantity
            FROM sales_records
            WHERE sync_batch_id LIKE 'historical_import%'
                AND product_id IS NULL
            GROUP BY product_name, product_article
            ORDER BY total_quantity DESC
            LIMIT 10
        """)
        
        print(f"{'Товар':<40} {'Артикул':<15} {'Продаж':<12} {'Кол-во':<15}")
        print("-" * 80)
        for row in unmatched:
            name = (row['product_name'] or 'N/A')[:38]
            article = (row['product_article'] or 'N/A')[:13]
            count = f"{row['sales_count']:,}"
            qty = f"{row['total_quantity']:,.0f}"
            print(f"{name:<40} {article:<15} {count:<12} {qty:<15}")
        print()
        
        await conn.close()
        print("[OK] Просмотр завершен!")
        return True
        
    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import argparse
    
    # Настройка для Windows
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    parser = argparse.ArgumentParser(description='Просмотр импортированных данных о продажах')
    parser.add_argument('--limit', type=int, default=20, help='Количество примеров записей (по умолчанию: 20)')
    parser.add_argument('--batch-id', type=str, default=None, help='Фильтр по batch_id')
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("ПРОСМОТР ИМПОРТИРОВАННЫХ ДАННЫХ О ПРОДАЖАХ")
    print("=" * 80)
    print()
    
    success = asyncio.run(view_imported_sales(limit=args.limit, batch_id_filter=args.batch_id))
    
    if success:
        print("\n" + "=" * 80)
        print("[OK] Скрипт выполнен успешно!")
        print("=" * 80)
        exit(0)
    else:
        print("\n" + "=" * 80)
        print("[ERROR] Скрипт завершился с ошибками")
        print("=" * 80)
        exit(1)
