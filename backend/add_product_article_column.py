"""
Скрипт для добавления поля product_article в таблицу purchase_history
"""
import asyncio
import sys
from pathlib import Path

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from app.database.connection import engine


async def add_product_article_column():
    """Добавление поля product_article в purchase_history"""
    async with engine.begin() as conn:
        # Проверяем, существует ли колонка
        check_query = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='purchase_history' AND column_name='product_article'
        """)
        result = await conn.execute(check_query)
        exists = result.scalar() is not None
        
        if exists:
            print("Колонка product_article уже существует в purchase_history")
            return
        
        # Добавляем колонку
        print("Добавление колонки product_article в purchase_history...")
        await conn.execute(text("""
            ALTER TABLE purchase_history 
            ADD COLUMN product_article VARCHAR(100)
        """))
        
        # Создаем индекс
        print("Создание индекса для product_article...")
        try:
            await conn.execute(text("""
                CREATE INDEX ix_purchase_history_product_article 
                ON purchase_history(product_article)
            """))
        except Exception as e:
            print(f"Индекс уже существует или ошибка: {e}")
        
        # Создаем индекс для product_id, если его еще нет
        print("Проверка индекса для product_id...")
        try:
            await conn.execute(text("""
                CREATE INDEX ix_purchase_history_product_id 
                ON purchase_history(product_id)
            """))
        except Exception as e:
            print(f"Индекс product_id уже существует или ошибка: {e}")
        
        print("[OK] Колонка product_article успешно добавлена в purchase_history")


if __name__ == "__main__":
    asyncio.run(add_product_article_column())
