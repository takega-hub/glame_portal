"""
Скрипт для создания таблицы website_priority
Запуск: python create_website_priority_table.py
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()


async def create_website_priority_table():
    """Создает таблицу website_priority"""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL не установлен в переменных окружения")
    
    conn = await asyncpg.connect(db_url)
    
    try:
        print("[INFO] Подключение к базе данных...")
        
        # Проверяем существование таблицы
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'website_priority'
            )
        """)
        
        if table_exists:
            print("[INFO] Таблица website_priority уже существует")
            return
        
        print("[INFO] Создание таблицы website_priority...")
        
        create_table_sql = """
        -- Создание таблицы website_priority
        CREATE TABLE IF NOT EXISTS website_priority (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            
            -- Связь с товаром
            product_id_1c VARCHAR(255),
            product_id UUID,
            
            -- Данные о товаре
            product_name VARCHAR(500),
            product_article VARCHAR(100),
            category VARCHAR(100),
            brand VARCHAR(100),
            
            -- Общий приоритет
            priority_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            priority_class VARCHAR(20),
            
            -- Компоненты приоритета
            turnover_score DOUBLE PRECISION,
            revenue_score DOUBLE PRECISION,
            margin_score DOUBLE PRECISION,
            stock_score DOUBLE PRECISION,
            trend_score DOUBLE PRECISION,
            seasonality_score DOUBLE PRECISION,
            
            -- Рекомендации
            is_recommended BOOLEAN DEFAULT FALSE,
            recommendation_reason VARCHAR(500),
            
            -- Служебные поля
            calculated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE
        );
        """
        
        await conn.execute(create_table_sql)
        print("[OK] Таблица website_priority создана!")
        
        # Создание индексов
        print("[INFO] Создание индексов...")
        
        indexes_sql = """
        -- Индексы для быстрых запросов
        CREATE INDEX IF NOT EXISTS ix_website_priority_product_id_1c ON website_priority(product_id_1c);
        CREATE INDEX IF NOT EXISTS ix_website_priority_product_id ON website_priority(product_id);
        CREATE INDEX IF NOT EXISTS ix_website_priority_product_name ON website_priority(product_name);
        CREATE INDEX IF NOT EXISTS ix_website_priority_product_article ON website_priority(product_article);
        CREATE INDEX IF NOT EXISTS ix_website_priority_category ON website_priority(category);
        CREATE INDEX IF NOT EXISTS ix_website_priority_brand ON website_priority(brand);
        CREATE INDEX IF NOT EXISTS ix_website_priority_score ON website_priority(priority_score);
        CREATE INDEX IF NOT EXISTS ix_website_priority_class ON website_priority(priority_class);
        CREATE INDEX IF NOT EXISTS ix_website_priority_recommended ON website_priority(is_recommended);
        CREATE UNIQUE INDEX IF NOT EXISTS ix_website_priority_product_unique ON website_priority(product_id_1c) WHERE product_id_1c IS NOT NULL;
        """
        
        await conn.execute(indexes_sql)
        print("[OK] Индексы созданы!")
        
        print("\n[SUCCESS] Таблица website_priority успешно создана со всеми индексами!")
        
    except Exception as e:
        print(f"[ERROR] Ошибка создания таблицы: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(create_website_priority_table())
