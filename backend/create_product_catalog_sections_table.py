"""
Скрипт для создания таблицы product_catalog_sections для связи many-to-many
между товарами и разделами каталога
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

# Добавляем путь к app
sys.path.insert(0, os.path.dirname(__file__))

# Загружаем .env
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")

if not DATABASE_URL:
    print("[ERROR] DATABASE_URL not found")
    sys.exit(1)

def create_table():
    """Создать таблицу product_catalog_sections"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        print("[INFO] Создание таблицы product_catalog_sections...")
        
        # Проверяем, существует ли таблица
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'product_catalog_sections'
            );
        """)
        exists = cursor.fetchone()[0]
        
        if exists:
            print("[INFO] Таблица product_catalog_sections уже существует")
            response = input("Удалить и пересоздать таблицу? (yes/no): ").strip().lower()
            if response == 'yes':
                print("[INFO] Удаление существующей таблицы...")
                cursor.execute("DROP TABLE IF EXISTS product_catalog_sections CASCADE;")
                conn.commit()
            else:
                print("[INFO] Отмена операции")
                cursor.close()
                conn.close()
                return
        
        # Создаем таблицу
        cursor.execute("""
            CREATE TABLE product_catalog_sections (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                catalog_section_id UUID NOT NULL REFERENCES catalog_sections(id) ON DELETE CASCADE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(product_id, catalog_section_id)
            );
        """)
        
        # Создаем индексы
        cursor.execute("""
            CREATE INDEX ix_product_catalog_sections_product_section 
            ON product_catalog_sections(product_id, catalog_section_id);
        """)
        
        cursor.execute("""
            CREATE INDEX ix_product_catalog_sections_product 
            ON product_catalog_sections(product_id);
        """)
        
        cursor.execute("""
            CREATE INDEX ix_product_catalog_sections_section 
            ON product_catalog_sections(catalog_section_id);
        """)
        
        conn.commit()
        print("[OK] Таблица product_catalog_sections успешно создана")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"[ERROR] Ошибка при создании таблицы: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    create_table()
