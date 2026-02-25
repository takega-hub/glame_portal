"""
Скрипт для создания таблицы product_sales_analytics
Таблица для агрегированных данных о продажах товаров
"""
import asyncio
import asyncpg
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

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

async def create_product_sales_analytics_table():
    """Создает таблицу product_sales_analytics"""
    
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
        
        print("[OK] Подключение установлено")
        
        # SQL для создания таблицы product_sales_analytics
        create_table_sql = """
        -- Создание таблицы product_sales_analytics
        CREATE TABLE IF NOT EXISTS product_sales_analytics (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            
            -- Связь с товаром
            product_id_1c VARCHAR(255),
            product_id UUID,
            
            -- Данные о товаре
            product_name VARCHAR(500),
            product_article VARCHAR(100),
            category VARCHAR(100),
            subcategory VARCHAR(100),
            brand VARCHAR(100),
            product_type VARCHAR(100),
            
            -- Период агрегации
            period_date DATE NOT NULL,
            period_type VARCHAR(20) NOT NULL,
            
            -- Агрегированные метрики
            total_revenue DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            total_quantity DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            orders_count INTEGER NOT NULL DEFAULT 0,
            avg_price DOUBLE PRECISION,
            avg_quantity_per_order DOUBLE PRECISION,
            
            -- Финансовые метрики
            total_cost DOUBLE PRECISION,
            total_margin DOUBLE PRECISION,
            margin_percent DOUBLE PRECISION,
            
            -- Канал продаж и магазин
            channel VARCHAR(64),
            store_id VARCHAR(255),
            
            -- Дополнительные метрики
            revenue_without_discount DOUBLE PRECISION,
            discount_amount DOUBLE PRECISION,
            
            -- Дополнительные данные
            raw_metrics JSONB,
            
            -- Служебные поля
            calculated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE
        );
        """
        
        await conn.execute(create_table_sql)
        print("[OK] Таблица product_sales_analytics создана!")
        
        # Создание индексов
        indexes_sql = """
        -- Индексы для быстрых запросов
        CREATE INDEX IF NOT EXISTS ix_product_sales_analytics_product_id_1c ON product_sales_analytics(product_id_1c);
        CREATE INDEX IF NOT EXISTS ix_product_sales_analytics_product_id ON product_sales_analytics(product_id);
        CREATE INDEX IF NOT EXISTS ix_product_sales_analytics_product_name ON product_sales_analytics(product_name);
        CREATE INDEX IF NOT EXISTS ix_product_sales_analytics_product_article ON product_sales_analytics(product_article);
        CREATE INDEX IF NOT EXISTS ix_product_sales_analytics_category ON product_sales_analytics(category);
        CREATE INDEX IF NOT EXISTS ix_product_sales_analytics_brand ON product_sales_analytics(brand);
        CREATE INDEX IF NOT EXISTS ix_product_sales_analytics_product_type ON product_sales_analytics(product_type);
        CREATE INDEX IF NOT EXISTS ix_product_sales_analytics_period_date ON product_sales_analytics(period_date);
        CREATE INDEX IF NOT EXISTS ix_product_sales_analytics_period_type ON product_sales_analytics(period_type);
        CREATE INDEX IF NOT EXISTS ix_product_sales_analytics_channel ON product_sales_analytics(channel);
        CREATE INDEX IF NOT EXISTS ix_product_sales_analytics_store_id ON product_sales_analytics(store_id);
        CREATE INDEX IF NOT EXISTS ix_product_sales_analytics_calculated_at ON product_sales_analytics(calculated_at);
        
        -- Составные индексы для частых запросов
        CREATE INDEX IF NOT EXISTS ix_product_sales_analytics_product_period ON product_sales_analytics(product_id_1c, period_date, period_type);
        CREATE INDEX IF NOT EXISTS ix_product_sales_analytics_category_period ON product_sales_analytics(category, period_date, period_type);
        CREATE INDEX IF NOT EXISTS ix_product_sales_analytics_brand_period ON product_sales_analytics(brand, period_date, period_type);
        CREATE INDEX IF NOT EXISTS ix_product_sales_analytics_type_period ON product_sales_analytics(product_type, period_date, period_type);
        CREATE INDEX IF NOT EXISTS ix_product_sales_analytics_store_period ON product_sales_analytics(store_id, period_date, period_type);
        CREATE INDEX IF NOT EXISTS ix_product_sales_analytics_channel_period ON product_sales_analytics(channel, period_date, period_type);
        CREATE INDEX IF NOT EXISTS ix_product_sales_analytics_period ON product_sales_analytics(period_date, period_type);
        """
        
        await conn.execute(indexes_sql)
        print("[OK] Индексы созданы!")
        
        # Проверяем, что таблица создана
        table_check = await conn.fetchval("""
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'product_sales_analytics'
        """)
        
        if table_check > 0:
            print(f"\n[OK] Таблица product_sales_analytics успешно создана")
            
            # Проверяем количество записей
            count = await conn.fetchval("SELECT COUNT(*) FROM product_sales_analytics")
            print(f"   Записей в таблице: {count}")
        else:
            print(f"\n[ERROR] Таблица product_sales_analytics не найдена")
        
        # Проверяем индексы
        indexes = await conn.fetch("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE tablename = 'product_sales_analytics'
            AND indexname LIKE 'ix_%'
            ORDER BY indexname
        """)
        
        if indexes:
            print(f"\n[INFO] Созданные индексы ({len(indexes)}):")
            for idx in indexes:
                print(f"   - {idx['indexname']}")
        
        await conn.close()
        print("\n[OK] Все операции выполнены успешно!")
        return True
        
    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Настройка для Windows
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    print("=" * 60)
    print("Создание таблицы product_sales_analytics")
    print("=" * 60)
    print()
    
    success = asyncio.run(create_product_sales_analytics_table())
    
    if success:
        print("\n" + "=" * 60)
        print("[OK] Скрипт выполнен успешно!")
        print("=" * 60)
        exit(0)
    else:
        print("\n" + "=" * 60)
        print("[ERROR] Скрипт завершился с ошибками")
        print("=" * 60)
        exit(1)
