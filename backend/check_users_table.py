"""
Скрипт для просмотра данных в таблице users
"""
import asyncio
import sys
from sqlalchemy import select, func, text
from app.database.connection import AsyncSessionLocal
from app.models.user import User

# Устанавливаем кодировку для Windows
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')


async def check_users_table():
    """Проверяет данные в таблице users"""
    async with AsyncSessionLocal() as db:
        try:
            print("=" * 80)
            print("АНАЛИЗ ТАБЛИЦЫ USERS")
            print("=" * 80)
            
            # 1. Общая статистика
            total_stmt = select(func.count(User.id))
            total_result = await db.execute(total_stmt)
            total = total_result.scalar()
            print(f"\n1. Всего пользователей в базе: {total}")
            
            # 2. Покупатели
            customers_stmt = select(func.count(User.id)).where(User.is_customer == True)
            customers_result = await db.execute(customers_stmt)
            customers = customers_result.scalar()
            print(f"2. Покупателей (is_customer=True): {customers}")
            
            # 3. Проверка наличия колонки gender в БД
            gender_check_stmt = text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'gender'
            """)
            gender_check_result = await db.execute(gender_check_stmt)
            gender_column = gender_check_result.fetchone()
            
            if gender_column:
                print(f"\n3. Колонка 'gender' существует в БД:")
                print(f"   - Тип данных: {gender_column[1]}")
                print(f"   - Nullable: {gender_column[2]}")
            else:
                print("\n3. Колонка 'gender' НЕ найдена в БД!")
            
            # 4. Статистика по полю gender (если колонка есть)
            if gender_column:
                # Всего с заполненным полем
                with_gender_stmt = text("""
                    SELECT COUNT(*) 
                    FROM users 
                    WHERE is_customer = TRUE AND gender IS NOT NULL
                """)
                with_gender_result = await db.execute(with_gender_stmt)
                with_gender = with_gender_result.scalar()
                
                # Мужчины
                male_stmt = text("""
                    SELECT COUNT(*) 
                    FROM users 
                    WHERE is_customer = TRUE AND gender = 'male'
                """)
                male_result = await db.execute(male_stmt)
                male_count = male_result.scalar()
                
                # Женщины
                female_stmt = text("""
                    SELECT COUNT(*) 
                    FROM users 
                    WHERE is_customer = TRUE AND gender = 'female'
                """)
                female_result = await db.execute(female_stmt)
                female_count = female_result.scalar()
                
                # NULL
                null_gender = customers - with_gender
                
                print(f"\n4. Статистика по полю 'gender' (для покупателей):")
                print(f"   - Мужчин (male): {male_count}")
                print(f"   - Женщин (female): {female_count}")
                print(f"   - Не указано (NULL): {null_gender}")
                print(f"   - Всего с заполненным полем: {with_gender}")
            
            # 5. Примеры покупателей с их именами и полом
            print(f"\n5. Примеры покупателей (первые 20):")
            print("-" * 80)
            print(f"{'ID':<38} {'Имя':<30} {'Пол':<10} {'Телефон':<15} {'Город':<15}")
            print("-" * 80)
            
            examples_stmt = text("""
                SELECT id, full_name, gender, phone, city
                FROM users
                WHERE is_customer = TRUE
                LIMIT 20
            """)
            
            examples_result = await db.execute(examples_stmt)
            examples = examples_result.all()
            
            for user in examples:
                user_id = str(user[0])[:36]
                full_name = user[1] or "—"
                gender = user[2] or "NULL"
                phone = user[3] or "—"
                city = user[4] or "—"
                
                # Обрезаем длинные строки
                if len(full_name) > 28:
                    full_name = full_name[:25] + "..."
                if len(city) > 13:
                    city = city[:10] + "..."
                
                print(f"{user_id:<38} {full_name:<30} {gender:<10} {phone:<15} {city:<15}")
            
            # 6. Примеры имен с телефоном в full_name
            print(f"\n6. Примеры покупателей с телефоном в имени (первые 10):")
            print("-" * 80)
            
            phone_in_name_stmt = text("""
                SELECT id, full_name, gender, phone
                FROM users
                WHERE is_customer = TRUE 
                  AND full_name ~ '[0-9]{10,}'
                LIMIT 10
            """)
            phone_in_name_result = await db.execute(phone_in_name_stmt)
            phone_in_name = phone_in_name_result.all()
            
            if phone_in_name:
                for user in phone_in_name:
                    print(f"  ID: {user[0]}")
                    print(f"  Имя: {user[1]}")
                    print(f"  Пол: {user[2] or 'NULL'}")
                    print(f"  Телефон: {user[3] or '—'}")
                    print()
            else:
                print("  Не найдено")
            
            # 7. Статистика по городам
            print(f"\n7. Топ-10 городов покупателей:")
            print("-" * 80)
            
            cities_stmt = text("""
                SELECT city, COUNT(*) as count
                FROM users
                WHERE is_customer = TRUE AND city IS NOT NULL
                GROUP BY city
                ORDER BY count DESC
                LIMIT 10
            """)
            cities_result = await db.execute(cities_stmt)
            cities = cities_result.all()
            
            for city, count in cities:
                print(f"  {city}: {count} покупателей")
            
            print("\n" + "=" * 80)
            
        except Exception as e:
            print(f"\n❌ Ошибка: {e}")
            import traceback
            traceback.print_exc()
            raise


if __name__ == "__main__":
    asyncio.run(check_users_table())
