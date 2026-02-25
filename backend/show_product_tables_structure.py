"""
Скрипт для отображения структуры таблиц товаров в базе данных
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

def get_table_structure(table_name: str):
    """Получить структуру таблицы"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Получаем информацию о колонках
        cursor.execute("""
            SELECT 
                column_name,
                data_type,
                character_maximum_length,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_schema = 'public' 
            AND table_name = %s
            ORDER BY ordinal_position;
        """, (table_name,))
        
        columns = cursor.fetchall()
        
        # Получаем информацию об индексах
        cursor.execute("""
            SELECT 
                indexname,
                indexdef
            FROM pg_indexes
            WHERE schemaname = 'public' 
            AND tablename = %s;
        """, (table_name,))
        
        indexes = cursor.fetchall()
        
        # Получаем информацию о внешних ключах
        cursor.execute("""
            SELECT
                tc.constraint_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_schema = 'public'
            AND tc.table_name = %s;
        """, (table_name,))
        
        foreign_keys = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return {
            'columns': columns,
            'indexes': indexes,
            'foreign_keys': foreign_keys
        }
    except Exception as e:
        print(f"[ERROR] Ошибка при получении структуры таблицы {table_name}: {e}")
        return None

def format_column_info(col):
    """Форматировать информацию о колонке"""
    data_type = col['data_type']
    if col['character_maximum_length']:
        data_type += f"({col['character_maximum_length']})"
    
    nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
    default = f" DEFAULT {col['column_default']}" if col['column_default'] else ""
    
    return f"  {col['column_name']:<30} {data_type:<25} {nullable}{default}"

def main():
    """Основная функция"""
    tables = [
        'products',
        'product_stocks',
        'catalog_sections',
    ]
    
    print("=" * 80)
    print("СТРУКТУРА ТАБЛИЦ ТОВАРОВ В БАЗЕ ДАННЫХ")
    print("=" * 80)
    print()
    
    for table_name in tables:
        print(f"\n{'=' * 80}")
        print(f"ТАБЛИЦА: {table_name}")
        print('=' * 80)
        
        structure = get_table_structure(table_name)
        if not structure:
            print(f"[ERROR] Не удалось получить структуру таблицы {table_name}")
            continue
        
        # Колонки
        print("\nКОЛОНКИ:")
        print("-" * 80)
        for col in structure['columns']:
            print(format_column_info(col))
        
        # Индексы
        if structure['indexes']:
            print("\nИНДЕКСЫ:")
            print("-" * 80)
            for idx in structure['indexes']:
                print(f"  {idx['indexname']}")
                print(f"    {idx['indexdef']}")
        
        # Внешние ключи
        if structure['foreign_keys']:
            print("\nВНЕШНИЕ КЛЮЧИ:")
            print("-" * 80)
            for fk in structure['foreign_keys']:
                print(f"  {fk['column_name']} -> {fk['foreign_table_name']}.{fk['foreign_column_name']}")
    
    print("\n" + "=" * 80)
    print("СТАТИСТИКА")
    print("=" * 80)
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Количество записей в каждой таблице
        for table_name in tables:
            cursor.execute(f"SELECT COUNT(*) as count FROM {table_name};")
            result = cursor.fetchone()
            print(f"  {table_name:<25} {result['count']:>10} записей")
        
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"[ERROR] Ошибка при получении статистики: {e}")

if __name__ == "__main__":
    main()
