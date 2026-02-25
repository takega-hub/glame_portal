"""
Скрипт для удаления записей об упаковке, салфетках и подарочных сертификатах из таблицы sales_records
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

# Список ключевых слов для исключения товаров
EXCLUDED_KEYWORDS = [
    'упаковка', 'упаковки', 'packaging', 'pack',
    'салфетк', 'napkin', 'салфетка', 'салфетки',
    'сертификат', 'certificate', 'подарочный сертификат', 'gift certificate',
    'подарочный', 'gift card'
]

EXCLUDED_CATEGORIES = [
    'упаковка', 'упаковки',
    'салфетки',
    'сертификаты', 'подарочные сертификаты'
]


async def remove_excluded_products():
    """Удаляет записи об исключенных товарах из sales_records"""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL не установлен в переменных окружения")
    
    conn = await asyncpg.connect(db_url)
    
    try:
        # Сначала проверяем, сколько записей будет удалено
        check_query = await conn.fetch("""
            SELECT COUNT(*) as count
            FROM sales_records
            WHERE (
                -- Проверка по названию товара
                (product_name IS NOT NULL AND (
                    """ + " OR ".join([f"LOWER(product_name) LIKE '%{kw.lower()}%'" for kw in EXCLUDED_KEYWORDS]) + """
                ))
                OR
                -- Проверка по категории
                (product_category IS NOT NULL AND (
                    """ + " OR ".join([f"LOWER(product_category) LIKE '%{cat.lower()}%'" for cat in EXCLUDED_CATEGORIES]) + """
                ))
            )
        """)
        
        count_to_delete = check_query[0]['count']
        print(f"Найдено {count_to_delete} записей для удаления")
        
        if count_to_delete == 0:
            print("Нет записей для удаления")
            return
        
        # Показываем примеры записей, которые будут удалены
        examples_query = await conn.fetch("""
            SELECT product_name, product_category, product_article, revenue, quantity, sale_date
            FROM sales_records
            WHERE (
                (product_name IS NOT NULL AND (
                    """ + " OR ".join([f"LOWER(product_name) LIKE '%{kw.lower()}%'" for kw in EXCLUDED_KEYWORDS]) + """
                ))
                OR
                (product_category IS NOT NULL AND (
                    """ + " OR ".join([f"LOWER(product_category) LIKE '%{cat.lower()}%'" for cat in EXCLUDED_CATEGORIES]) + """
                ))
            )
            LIMIT 10
        """)
        
        print("\nПримеры записей, которые будут удалены:")
        print(f"{'Название':<40} {'Категория':<30} {'Артикул':<20} {'Выручка':<15} {'Дата':<12}")
        print("-" * 120)
        for ex in examples_query:
            name = (ex['product_name'] or 'N/A')[:38]
            category = (ex['product_category'] or 'N/A')[:28]
            article = (ex['product_article'] or 'N/A')[:18]
            revenue = f"{ex['revenue']:,.2f}" if ex['revenue'] else '0.00'
            date_str = ex['sale_date'].strftime('%Y-%m-%d') if ex['sale_date'] else 'N/A'
            print(f"{name:<40} {category:<30} {article:<20} {revenue:<15} {date_str:<12}")
        
        # Подтверждение
        print(f"\nБудет удалено {count_to_delete} записей.")
        print("Продолжить? (y/n): ", end='')
        # В автоматическом режиме подтверждаем
        confirm = 'y'
        
        if confirm.lower() != 'y':
            print("Отменено")
            return
        
        # Удаляем записи
        delete_query = """
            DELETE FROM sales_records
            WHERE (
                (product_name IS NOT NULL AND (
                    """ + " OR ".join([f"LOWER(product_name) LIKE '%{kw.lower()}%'" for kw in EXCLUDED_KEYWORDS]) + """
                ))
                OR
                (product_category IS NOT NULL AND (
                    """ + " OR ".join([f"LOWER(product_category) LIKE '%{cat.lower()}%'" for cat in EXCLUDED_CATEGORIES]) + """
                ))
            )
        """
        
        result = await conn.execute(delete_query)
        deleted_count = int(result.split()[-1]) if result.split()[-1].isdigit() else 0
        
        print(f"\nУдалено записей: {deleted_count}")
        
        # Финальная статистика
        final_stats = await conn.fetch("""
            SELECT 
                COUNT(*) as total,
                SUM(revenue) as total_revenue,
                SUM(quantity) as total_quantity
            FROM sales_records
        """)
        
        stats = final_stats[0]
        print(f"\nФинальная статистика по таблице sales_records:")
        print(f"  Всего записей: {stats['total']}")
        print(f"  Общая выручка: {stats['total_revenue']:,.2f} RUR")
        print(f"  Общее количество: {stats['total_quantity']:,.2f}")
        
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(remove_excluded_products())
