"""
Проверка наличия колонки city в таблице users
"""
import asyncio
import sys
from sqlalchemy import text
from app.database.connection import AsyncSessionLocal

# Для Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def check_city_column():
    """Проверяем наличие колонки city"""
    async with AsyncSessionLocal() as db:
        try:
            # Проверяем структуру таблицы
            result = await db.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'users'
                ORDER BY ordinal_position
            """))
            
            columns = result.fetchall()
            
            print("\n" + "="*60)
            print("КОЛОНКИ В ТАБЛИЦЕ users:")
            print("="*60)
            
            has_city = False
            for col in columns:
                print(f"  {col[0]:<30} {col[1]}")
                if col[0] == 'city':
                    has_city = True
            
            print("="*60)
            
            if has_city:
                print("\n[OK] Колонка 'city' НАЙДЕНА в таблице users")
                
                # Проверяем, есть ли данные
                result = await db.execute(text("""
                    SELECT COUNT(*) as total,
                           COUNT(city) as with_city
                    FROM users 
                    WHERE is_customer = true
                """))
                row = result.fetchone()
                print(f"\nВсего покупателей: {row[0]}")
                print(f"С заполненным городом: {row[1]}")
                
                if row[1] > 0:
                    # Показываем примеры
                    result = await db.execute(text("""
                        SELECT full_name, phone, city
                        FROM users 
                        WHERE is_customer = true AND city IS NOT NULL
                        LIMIT 5
                    """))
                    rows = result.fetchall()
                    print("\nПримеры покупателей с городом:")
                    for r in rows:
                        print(f"  {r[0] or 'Без имени'} ({r[1]}): {r[2]}")
                else:
                    print("\n[WARNING] Ни у одного покупателя не заполнен город!")
            else:
                print("\n[ERROR] Колонка 'city' НЕ НАЙДЕНА в таблице users!")
                print("\n[INFO] Нужно выполнить миграцию или создать колонку вручную:")
                print("\n   ALTER TABLE users ADD COLUMN city VARCHAR(100);")
            
            print("="*60)
            
        except Exception as e:
            print(f"\n[ERROR] Ошибка: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(check_city_column())
