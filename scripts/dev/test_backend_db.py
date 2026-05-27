#!/usr/bin/env python3
import asyncio
import asyncpg

async def test_backend_db():
    try:
        conn = await asyncpg.connect(
            host='e7905e3c0050_glame_postgres',
            port=5432,
            user='glame_user',
            password='glame_password',
            database='glame_db'
        )
        print("✅ Подключение к базе данных успешно!")
        
        # Проверим, есть ли данные в таблицах
        result = await conn.fetch("SELECT COUNT(*) FROM catalog_sections")
        print(f"Количество каталогов: {result[0]['count']}")
        
        result = await conn.fetch("SELECT COUNT(*) FROM products")
        print(f"Количество продуктов: {result[0]['count']}")
        
        await conn.close()
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(test_backend_db())