"""
Скрипт для создания таблицы inventory_analytics
Запуск: python create_inventory_analytics_table.py
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()


async def create_inventory_analytics_table():
    """Создает таблицу inventory_analytics"""
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
                AND table_name = 'inventory_analytics'
            )
        """)
        
        if table_exists:
            print("[INFO] Таблица inventory_analytics уже существует")
            return
        
        print("[INFO] Создание таблицы inventory_analytics...")
        
        create_table_sql = """
        -- Создание таблицы inventory_analytics
        CREATE TABLE IF NOT EXISTS inventory_analytics (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            
            -- Связь с товаром
            product_id_1c VARCHAR(255),
            product_id UUID,
            
            -- Данные о товаре
            product_name VARCHAR(500),
            product_article VARCHAR(100),
            category VARCHAR(100),
            brand VARCHAR(100),
            
            -- Магазин/склад
            store_id VARCHAR(255),
            
            -- Дата анализа
            analysis_date DATE NOT NULL,
            
            -- Текущие остатки
            current_stock DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            avg_stock_30d DOUBLE PRECISION,
            avg_stock_90d DOUBLE PRECISION,
            
            -- Скорость продаж
            sales_velocity DOUBLE PRECISION,
            avg_daily_sales DOUBLE PRECISION,
            
            -- Оборачиваемость
            turnover_days DOUBLE PRECISION,
            turnover_rate DOUBLE PRECISION,
            
            -- Риски
            stockout_risk DOUBLE PRECISION,
            overstock_risk DOUBLE PRECISION,
            
            -- Классификация
            abc_class VARCHAR(1),
            xyz_class VARCHAR(1),
            
            -- Уровень сервиса
            service_level DOUBLE PRECISION,
            
            -- Снимки остатков по дням
            daily_snapshots JSONB,
            
            -- Служебные поля
            calculated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE
        );
        """
        
        await conn.execute(create_table_sql)
        print("[OK] Таблица inventory_analytics создана!")
        
        # Создание индексов
        print("[INFO] Создание индексов...")
        
        indexes_sql = """
        -- Индексы для быстрых запросов
        CREATE INDEX IF NOT EXISTS ix_inventory_analytics_product_id_1c ON inventory_analytics(product_id_1c);
        CREATE INDEX IF NOT EXISTS ix_inventory_analytics_product_id ON inventory_analytics(product_id);
        CREATE INDEX IF NOT EXISTS ix_inventory_analytics_product_name ON inventory_analytics(product_name);
        CREATE INDEX IF NOT EXISTS ix_inventory_analytics_product_article ON inventory_analytics(product_article);
        CREATE INDEX IF NOT EXISTS ix_inventory_analytics_category ON inventory_analytics(category);
        CREATE INDEX IF NOT EXISTS ix_inventory_analytics_brand ON inventory_analytics(brand);
        CREATE INDEX IF NOT EXISTS ix_inventory_analytics_store_id ON inventory_analytics(store_id);
        CREATE INDEX IF NOT EXISTS ix_inventory_analytics_analysis_date ON inventory_analytics(analysis_date);
        CREATE INDEX IF NOT EXISTS ix_inventory_analytics_abc_class ON inventory_analytics(abc_class);
        CREATE INDEX IF NOT EXISTS ix_inventory_analytics_xyz_class ON inventory_analytics(xyz_class);
        CREATE INDEX IF NOT EXISTS ix_inventory_analytics_product_date ON inventory_analytics(product_id_1c, analysis_date);
        CREATE INDEX IF NOT EXISTS ix_inventory_analytics_store_date ON inventory_analytics(store_id, analysis_date);
        CREATE INDEX IF NOT EXISTS ix_inventory_analytics_abc_xyz ON inventory_analytics(abc_class, xyz_class);
        CREATE INDEX IF NOT EXISTS ix_inventory_analytics_category_date ON inventory_analytics(category, analysis_date);
        CREATE INDEX IF NOT EXISTS ix_inventory_analytics_risk ON inventory_analytics(stockout_risk, overstock_risk);
        """
        
        await conn.execute(indexes_sql)
        print("[OK] Индексы созданы!")
        
        print("\n[SUCCESS] Таблица inventory_analytics успешно создана со всеми индексами!")
        
    except Exception as e:
        print(f"[ERROR] Ошибка создания таблицы: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(create_inventory_analytics_table())
