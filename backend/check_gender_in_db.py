"""
Скрипт для проверки, сохранились ли данные о поле в БД
"""
import asyncio
from sqlalchemy import select, func
from app.database.connection import AsyncSessionLocal
from app.models.user import User


async def check_gender_data():
    """Проверяет данные о поле в БД"""
    async with AsyncSessionLocal() as db:
        try:
            # Общее количество покупателей
            total_stmt = select(func.count(User.id)).where(User.is_customer == True)
            total_result = await db.execute(total_stmt)
            total = total_result.scalar()
            
            # Количество с определенным полом (используем прямое SQL для совместимости)
            from sqlalchemy import text
            with_gender_stmt = text("""
                SELECT COUNT(*) 
                FROM users 
                WHERE is_customer = TRUE AND gender IS NOT NULL
            """)
            with_gender_result = await db.execute(with_gender_stmt)
            with_gender = with_gender_result.scalar()
            
            # Количество мужчин
            male_stmt = text("""
                SELECT COUNT(*) 
                FROM users 
                WHERE is_customer = TRUE AND gender = 'male'
            """)
            male_result = await db.execute(male_stmt)
            male_count = male_result.scalar()
            
            # Количество женщин
            female_stmt = text("""
                SELECT COUNT(*) 
                FROM users 
                WHERE is_customer = TRUE AND gender = 'female'
            """)
            female_result = await db.execute(female_stmt)
            female_count = female_result.scalar()
            
            # Показываем несколько примеров (используем прямое SQL)
            examples_stmt = text("""
                SELECT id, full_name, gender 
                FROM users 
                WHERE is_customer = TRUE AND gender IS NOT NULL
                LIMIT 5
            """)
            examples_result = await db.execute(examples_stmt)
            examples = examples_result.fetchall()
            
            print("=" * 60)
            print("СТАТИСТИКА ПО ПОЛУ В БД:")
            print("=" * 60)
            print(f"Всего покупателей: {total}")
            if total > 0:
                print(f"С определенным полом: {with_gender} ({with_gender/total*100:.1f}%)")
                print(f"  - Мужчин: {male_count}")
                print(f"  - Женщин: {female_count}")
                print(f"Без пола: {total - with_gender} ({(total - with_gender)/total*100:.1f}%)")
            else:
                print("Покупатели не найдены")
            print()
            print("Примеры записей с полом:")
            for row in examples:
                user_id, full_name, gender = row
                print(f"  - {full_name or 'Без имени'}: {gender}")
            print("=" * 60)
            
        except Exception as e:
            print(f"❌ Ошибка при проверке данных: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(check_gender_data())
