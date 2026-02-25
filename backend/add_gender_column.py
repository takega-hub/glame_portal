"""
Скрипт для добавления колонки gender в таблицу users
"""
import asyncio
import sys
from sqlalchemy import text
from app.database.connection import AsyncSessionLocal, engine


async def add_gender_column():
    """Добавляет колонку gender в таблицу users"""
    async with AsyncSessionLocal() as session:
        try:
            # Проверяем, существует ли уже колонка
            check_query = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' AND column_name = 'gender'
            """)
            result = await session.execute(check_query)
            existing = result.scalar_one_or_none()
            
            if existing:
                print("Колонка 'gender' уже существует в таблице 'users'")
                return
            
            # Добавляем колонку
            add_column_query = text("""
                ALTER TABLE users 
                ADD COLUMN gender VARCHAR(10) NULL
            """)
            await session.execute(add_column_query)
            await session.commit()
            
            print("✅ Колонка 'gender' успешно добавлена в таблицу 'users'")
            
        except Exception as e:
            await session.rollback()
            print(f"❌ Ошибка при добавлении колонки: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(add_gender_column())
