"""
Скрипт для расширения таблицы sales_records новыми полями согласно плану аналитики
Добавляет поля: product_name, product_article, product_category, product_brand, product_type
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

async def extend_sales_record_table():
    """Расширяет таблицу sales_records новыми полями"""
    
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
        
        # SQL для добавления новых полей
        extend_table_sql = """
        -- Добавление новых полей в таблицу sales_records
        DO $$ 
        BEGIN
            -- product_name - название товара на момент продажи
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'sales_records' AND column_name = 'product_name'
            ) THEN
                ALTER TABLE sales_records ADD COLUMN product_name VARCHAR(500);
                RAISE NOTICE 'Поле product_name добавлено';
            END IF;
            
            -- product_article - артикул товара
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'sales_records' AND column_name = 'product_article'
            ) THEN
                ALTER TABLE sales_records ADD COLUMN product_article VARCHAR(100);
                CREATE INDEX IF NOT EXISTS ix_sales_records_product_article ON sales_records(product_article);
                RAISE NOTICE 'Поле product_article добавлено';
            END IF;
            
            -- product_category - категория товара
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'sales_records' AND column_name = 'product_category'
            ) THEN
                ALTER TABLE sales_records ADD COLUMN product_category VARCHAR(100);
                CREATE INDEX IF NOT EXISTS ix_sales_records_product_category ON sales_records(product_category);
                RAISE NOTICE 'Поле product_category добавлено';
            END IF;
            
            -- product_brand - бренд товара
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'sales_records' AND column_name = 'product_brand'
            ) THEN
                ALTER TABLE sales_records ADD COLUMN product_brand VARCHAR(100);
                CREATE INDEX IF NOT EXISTS ix_sales_records_product_brand ON sales_records(product_brand);
                RAISE NOTICE 'Поле product_brand добавлено';
            END IF;
            
            -- product_type - тип изделия (кольца, серьги, браслеты и т.д.)
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'sales_records' AND column_name = 'product_type'
            ) THEN
                ALTER TABLE sales_records ADD COLUMN product_type VARCHAR(100);
                CREATE INDEX IF NOT EXISTS ix_sales_records_product_type ON sales_records(product_type);
                RAISE NOTICE 'Поле product_type добавлено';
            END IF;
            
            -- cost_price - себестоимость (если доступна)
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'sales_records' AND column_name = 'cost_price'
            ) THEN
                ALTER TABLE sales_records ADD COLUMN cost_price DOUBLE PRECISION;
                RAISE NOTICE 'Поле cost_price добавлено';
            END IF;
            
            -- margin - маржа
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'sales_records' AND column_name = 'margin'
            ) THEN
                ALTER TABLE sales_records ADD COLUMN margin DOUBLE PRECISION;
                RAISE NOTICE 'Поле margin добавлено';
            END IF;
            
        END $$;
        """
        
        await conn.execute(extend_table_sql)
        print("[OK] Таблица sales_records расширена новыми полями!")
        
        # Проверяем добавленные поля
        columns = await conn.fetch("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'sales_records' 
            AND column_name IN ('product_name', 'product_article', 'product_category', 
                               'product_brand', 'product_type', 'cost_price', 'margin')
            ORDER BY column_name
        """)
        
        print("\n[INFO] Добавленные поля:")
        for col in columns:
            print(f"   [OK] {col['column_name']} ({col['data_type']})")
        
        # Проверяем индексы
        indexes = await conn.fetch("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE tablename = 'sales_records'
            AND indexname LIKE 'ix_sales_records_product%'
            ORDER BY indexname
        """)
        
        if indexes:
            print(f"\n[INFO] Созданные индексы для новых полей:")
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
    print("Расширение таблицы sales_records новыми полями")
    print("=" * 60)
    print()
    
    success = asyncio.run(extend_sales_record_table())
    
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
