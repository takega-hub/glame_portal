"""
Скрипт для удаления исторических данных о продажах из Excel
Перед повторным импортом после изменений в таблице
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


async def delete_historical_sales(confirm: bool = False):
    """Удаляет исторические данные о продажах"""
    
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
        
        print("[OK] Подключение установлено\n")
        
        # Проверяем количество записей для удаления
        count = await conn.fetchval("""
            SELECT COUNT(*) FROM sales_records 
            WHERE sync_batch_id LIKE 'historical_import%'
        """)
        
        if count == 0:
            print("[INFO] Исторические данные не найдены. Нечего удалять.")
            await conn.close()
            return True
        
        print(f"[INFO] Найдено исторических записей для удаления: {count:,}\n")
        
        if not confirm:
            print("[WARNING] Это удалит все исторические данные!")
            print("Для подтверждения запустите скрипт с флагом --confirm")
            await conn.close()
            return False
        
        print("[INFO] Удаление исторических данных...")
        
        # Удаляем записи
        deleted = await conn.execute("""
            DELETE FROM sales_records 
            WHERE sync_batch_id LIKE 'historical_import%'
        """)
        
        # Проверяем результат
        remaining = await conn.fetchval("""
            SELECT COUNT(*) FROM sales_records 
            WHERE sync_batch_id LIKE 'historical_import%'
        """)
        
        print(f"[OK] Удалено записей: {count:,}")
        print(f"[OK] Осталось исторических записей: {remaining:,}")
        
        # Показываем общую статистику
        total = await conn.fetchval("SELECT COUNT(*) FROM sales_records")
        print(f"[INFO] Всего записей в таблице sales_records: {total:,}")
        
        await conn.close()
        print("\n[OK] Удаление завершено успешно!")
        print("[INFO] Теперь можно запустить импорт заново:")
        print("  python import_historical_sales_from_excel.py")
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
    
    parser = argparse.ArgumentParser(description='Удаление исторических данных о продажах')
    parser.add_argument('--confirm', action='store_true', help='Подтвердить удаление')
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("УДАЛЕНИЕ ИСТОРИЧЕСКИХ ДАННЫХ О ПРОДАЖАХ")
    print("=" * 80)
    print()
    
    success = asyncio.run(delete_historical_sales(confirm=args.confirm))
    
    if success:
        print("\n" + "=" * 80)
        print("[OK] Скрипт выполнен успешно!")
        print("=" * 80)
        exit(0)
    else:
        print("\n" + "=" * 80)
        if not args.confirm:
            print("[INFO] Запустите с --confirm для подтверждения удаления")
        else:
            print("[ERROR] Скрипт завершился с ошибками")
        print("=" * 80)
        exit(1)
