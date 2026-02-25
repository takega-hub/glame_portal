"""
Скрипт для создания таблиц продаж и обновления таблицы магазинов
Создает:
- Таблицу sales_records (детальные записи о продажах)
- Добавляет поле external_id в таблицу stores (для связи с 1С)
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

async def create_sales_tables():
    """Создает таблицы для продаж и обновляет stores"""
    
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
        
        # SQL для создания таблицы sales_records
        sales_records_sql = """
        -- Создание таблицы sales_records
        CREATE TABLE IF NOT EXISTS sales_records (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            sale_date TIMESTAMP WITH TIME ZONE NOT NULL,
            external_id VARCHAR(255),
            document_id VARCHAR(255),
            store_id VARCHAR(255),
            customer_id VARCHAR(255),
            product_id VARCHAR(255),
            organization_id VARCHAR(255),
            revenue DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            quantity DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            revenue_without_discount DOUBLE PRECISION,
            channel VARCHAR(64) DEFAULT 'offline',
            raw_data JSONB,
            synced_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            sync_batch_id VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE
        );

        -- Создание индексов для sales_records
        CREATE INDEX IF NOT EXISTS ix_sales_records_sale_date ON sales_records(sale_date);
        CREATE UNIQUE INDEX IF NOT EXISTS ix_sales_records_external_id ON sales_records(external_id) WHERE external_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS ix_sales_records_document_id ON sales_records(document_id);
        CREATE INDEX IF NOT EXISTS ix_sales_records_store_id ON sales_records(store_id);
        CREATE INDEX IF NOT EXISTS ix_sales_records_customer_id ON sales_records(customer_id);
        CREATE INDEX IF NOT EXISTS ix_sales_records_product_id ON sales_records(product_id);
        CREATE INDEX IF NOT EXISTS ix_sales_records_synced_at ON sales_records(synced_at);
        CREATE INDEX IF NOT EXISTS ix_sales_records_sync_batch_id ON sales_records(sync_batch_id);
        CREATE INDEX IF NOT EXISTS ix_sales_records_date_store ON sales_records(sale_date, store_id);
        CREATE INDEX IF NOT EXISTS ix_sales_records_date_customer ON sales_records(sale_date, customer_id);
        CREATE INDEX IF NOT EXISTS ix_sales_records_date_product ON sales_records(sale_date, product_id);
        CREATE INDEX IF NOT EXISTS ix_sales_records_channel ON sales_records(channel);
        """
        
        await conn.execute(sales_records_sql)
        print("[OK] Таблица sales_records создана!")
        
        # Обновление таблицы stores - добавление поля external_id
        stores_update_sql = """
        -- Добавление поля external_id в таблицу stores (если его еще нет)
        DO $$ 
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'stores' AND column_name = 'external_id'
            ) THEN
                ALTER TABLE stores ADD COLUMN external_id VARCHAR(255);
                CREATE INDEX IF NOT EXISTS ix_stores_external_id ON stores(external_id);
                RAISE NOTICE 'Поле external_id добавлено в таблицу stores';
            ELSE
                RAISE NOTICE 'Поле external_id уже существует в таблице stores';
            END IF;
        END $$;
        """
        
        await conn.execute(stores_update_sql)
        print("[OK] Таблица stores обновлена (добавлено поле external_id)!")
        
        # Проверяем, что таблицы существуют
        sales_tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'sales_records'
        """)
        
        stores_columns = await conn.fetch("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'stores' 
            AND column_name = 'external_id'
        """)
        
        print("\n[INFO] Проверка созданных объектов:")
        if sales_tables:
            print(f"   [OK] Таблица sales_records существует")
            
            # Проверяем количество записей
            count = await conn.fetchval("SELECT COUNT(*) FROM sales_records")
            print(f"      Записей в таблице: {count}")
        else:
            print(f"   [ERROR] Таблица sales_records не найдена")
        
        if stores_columns:
            print(f"   [OK] Поле external_id в таблице stores существует")
        else:
            print(f"   [ERROR] Поле external_id в таблице stores не найдено")
        
        # Проверяем индексы
        indexes = await conn.fetch("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE tablename IN ('sales_records', 'stores')
            AND indexname LIKE 'ix_%'
            ORDER BY tablename, indexname
        """)
        
        if indexes:
            print(f"\n[INFO] Созданные индексы:")
            for idx in indexes:
                print(f"   - {idx['indexname']}")
        
        await conn.close()
        print("\n[OK] Все операции выполнены успешно!")
        return True
        
    except asyncpg.exceptions.InvalidPasswordError:
        print("[ERROR] Ошибка: Неверный пароль для подключения к БД")
        return False
    except asyncpg.exceptions.InvalidCatalogNameError:
        print(f"[ERROR] Ошибка: База данных '{DB_NAME}' не существует")
        return False
    except asyncpg.exceptions.ConnectionDoesNotExistError:
        print(f"[ERROR] Ошибка: Не удалось подключиться к БД {DB_HOST}:{DB_PORT}")
        print("   Проверьте, что PostgreSQL запущен и доступен")
        return False
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
    print("Создание таблиц для продаж и обновление stores")
    print("=" * 60)
    print()
    
    success = asyncio.run(create_sales_tables())
    
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
