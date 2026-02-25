"""
Скрипт для создания таблицы purchase_recommendation
Запуск: python create_purchase_recommendation_table.py
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()


async def create_purchase_recommendation_table():
    """Создает таблицу purchase_recommendation"""
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
                AND table_name = 'purchase_recommendation'
            )
        """)
        
        if table_exists:
            print("[INFO] Таблица purchase_recommendation уже существует")
            return
        
        print("[INFO] Создание таблицы purchase_recommendation...")
        
        create_table_sql = """
        -- Создание таблицы purchase_recommendation
        CREATE TABLE IF NOT EXISTS purchase_recommendation (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            
            -- Связь с товаром
            product_id_1c VARCHAR(255),
            product_id UUID,
            
            -- Данные о товаре
            product_name VARCHAR(500),
            product_article VARCHAR(100),
            category VARCHAR(100),
            brand VARCHAR(100),
            
            -- Текущие остатки
            current_stock INTEGER NOT NULL DEFAULT 0,
            
            -- Рекомендации
            recommended_stock INTEGER,
            reorder_quantity INTEGER,
            reorder_point INTEGER,
            
            -- Метрики для расчёта
            days_of_stock DOUBLE PRECISION,
            avg_daily_sales DOUBLE PRECISION,
            turnover_rate DOUBLE PRECISION,
            turnover_days DOUBLE PRECISION,
            
            -- Уровень срочности
            urgency_level VARCHAR(20),
            
            -- Распределение по магазинам
            store_distribution VARCHAR(500),
            
            -- Даты
            recommended_date TIMESTAMP WITH TIME ZONE,
            calculated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE
        );
        """
        
        await conn.execute(create_table_sql)
        print("[OK] Таблица purchase_recommendation создана!")
        
        # Создание индексов
        print("[INFO] Создание индексов...")
        
        indexes_sql = """
        -- Индексы для быстрых запросов
        CREATE INDEX IF NOT EXISTS ix_purchase_recommendation_product_id_1c ON purchase_recommendation(product_id_1c);
        CREATE INDEX IF NOT EXISTS ix_purchase_recommendation_product_id ON purchase_recommendation(product_id);
        CREATE INDEX IF NOT EXISTS ix_purchase_recommendation_product_name ON purchase_recommendation(product_name);
        CREATE INDEX IF NOT EXISTS ix_purchase_recommendation_product_article ON purchase_recommendation(product_article);
        CREATE INDEX IF NOT EXISTS ix_purchase_recommendation_category ON purchase_recommendation(category);
        CREATE INDEX IF NOT EXISTS ix_purchase_recommendation_brand ON purchase_recommendation(brand);
        CREATE INDEX IF NOT EXISTS ix_purchase_recommendation_urgency ON purchase_recommendation(urgency_level);
        CREATE INDEX IF NOT EXISTS ix_purchase_recommendation_date ON purchase_recommendation(recommended_date);
        CREATE UNIQUE INDEX IF NOT EXISTS ix_purchase_recommendation_product_unique ON purchase_recommendation(product_id_1c) WHERE product_id_1c IS NOT NULL;
        """
        
        await conn.execute(indexes_sql)
        print("[OK] Индексы созданы!")
        
        print("\n[SUCCESS] Таблица purchase_recommendation успешно создана со всеми индексами!")
        
    except Exception as e:
        print(f"[ERROR] Ошибка создания таблицы: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(create_purchase_recommendation_table())
