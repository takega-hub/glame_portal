#!/usr/bin/env python3
import asyncio
import asyncpg

async def test_connection():
    try:
        conn = await asyncpg.connect(
            host='172.18.0.3',
            port=5432,
            user='glame_user',
            password='glame_password',
            database='glame_db'
        )
        print("✅ Подключение к PostgreSQL успешно!")
        await conn.close()
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())