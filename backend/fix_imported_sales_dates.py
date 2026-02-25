"""
Скрипт для исправления дат в уже импортированных исторических данных
Использует month_label из raw_data для правильного парсинга даты
"""
import asyncio
import asyncpg
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import json
import re
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


def parse_month_label(label: str) -> datetime:
    """Парсит метку месяца в дату"""
    if not label:
        return None
    
    label_str = str(label).strip()
    if not label_str or label_str.lower() in ['nan', 'none', '']:
        return None
    
    month_map = {
        'янв': 1, 'фев': 2, 'мар': 3, 'апр': 4, 'май': 5, 'июн': 6,
        'июл': 7, 'авг': 8, 'сен': 9, 'окт': 10, 'ноя': 11, 'дек': 12
    }
    
    label_lower = label_str.lower()
    if 'итого' in label_lower:
        return None
    
    # Примеры: "янв. 24", "янв 24", "январь 2024", "янв.24"
    patterns = [
        r'([а-я]+)\.?\s*(\d{2,4})',  # "янв. 24" или "янв 24"
        r'([а-я]+)\s+(\d{4})',       # "январь 2024"
        r'([а-я]+)\.(\d{2,4})',      # "янв.24" (без пробела)
    ]
    
    for pattern in patterns:
        match = re.search(pattern, label_lower)
        if match:
            month_str = match.group(1)[:3]
            year_str = match.group(2)
            
            month_num = month_map.get(month_str)
            if month_num:
                try:
                    year = int(year_str)
                    if year < 100:
                        year += 2000
                    if 2020 <= year <= 2030:
                        return datetime(year, month_num, 1)
                except ValueError:
                    continue
    
    return None


async def fix_imported_dates(dry_run: bool = True):
    """Исправляет даты в импортированных данных"""
    
    # Параметры подключения
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "5433"))
    DB_USER = os.getenv("DB_USER", "glame_user")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "glame_password")
    DB_NAME = os.getenv("DB_NAME", "glame_db")
    
    print(f"Подключение к БД: {DB_HOST}:{DB_PORT}/{DB_NAME} как {DB_USER}")
    
    if dry_run:
        print("[INFO] РЕЖИМ ПРОВЕРКИ (dry-run) - изменения не будут сохранены\n")
    else:
        print("[INFO] РЕЖИМ ИСПРАВЛЕНИЯ - изменения будут сохранены\n")
    
    try:
        conn = await asyncpg.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        
        print("[OK] Подключение установлено\n")
        
        # Находим записи с неправильными датами (1970 или раньше 2020)
        records = await conn.fetch("""
            SELECT 
                id,
                sale_date,
                product_name,
                product_article,
                raw_data,
                external_id
            FROM sales_records
            WHERE sync_batch_id LIKE 'historical_import%'
                AND (sale_date < '2020-01-01'::timestamp OR sale_date IS NULL)
            ORDER BY external_id
        """)
        
        print(f"Найдено записей с неправильными датами: {len(records)}\n")
        
        if not records:
            print("[OK] Все даты корректны!")
            await conn.close()
            return True
        
        fixed_count = 0
        skipped_count = 0
        errors = []
        
        for record in records:
            try:
                raw_data = record['raw_data']
                if isinstance(raw_data, str):
                    raw_data = json.loads(raw_data)
                
                month_label = raw_data.get('month_label') if raw_data else None
                
                if not month_label:
                    skipped_count += 1
                    print(f"[SKIP] {record['external_id']}: нет month_label в raw_data")
                    continue
                
                new_date = parse_month_label(month_label)
                
                if not new_date:
                    skipped_count += 1
                    print(f"[SKIP] {record['external_id']}: не удалось распарсить '{month_label}'")
                    continue
                
                old_date = record['sale_date']
                
                print(f"[FIX] {record['external_id']}: {old_date} -> {new_date.strftime('%Y-%m-%d')} (из '{month_label}')")
                
                if not dry_run:
                    await conn.execute("""
                        UPDATE sales_records
                        SET sale_date = $1
                        WHERE id = $2
                    """, new_date, record['id'])
                
                fixed_count += 1
                
            except Exception as e:
                errors.append((record['external_id'], str(e)))
                print(f"[ERROR] {record['external_id']}: {e}")
        
        print("\n" + "=" * 80)
        print("РЕЗУЛЬТАТЫ")
        print("=" * 80)
        print(f"Исправлено: {fixed_count}")
        print(f"Пропущено: {skipped_count}")
        print(f"Ошибок: {len(errors)}")
        
        if errors:
            print("\nОшибки:")
            for ext_id, error in errors[:10]:
                print(f"  {ext_id}: {error}")
        
        if dry_run:
            print("\n[INFO] Это был режим проверки. Для применения изменений запустите:")
            print("  python fix_imported_sales_dates.py --apply")
        else:
            await conn.execute("COMMIT")
            print("\n[OK] Изменения применены!")
        
        await conn.close()
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
    
    parser = argparse.ArgumentParser(description='Исправление дат в импортированных данных')
    parser.add_argument('--apply', action='store_true', help='Применить изменения (по умолчанию только проверка)')
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("ИСПРАВЛЕНИЕ ДАТ В ИМПОРТИРОВАННЫХ ДАННЫХ")
    print("=" * 80)
    print()
    
    success = asyncio.run(fix_imported_dates(dry_run=not args.apply))
    
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
