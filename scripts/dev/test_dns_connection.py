#!/usr/bin/env python3
import asyncio
import asyncpg

async def test_connection():
    try:
        # Проверяем подключение по имени контейнера
        conn = await asyncpg.connect(
            host='e7905e3c0050_glame_postgres',
            port=5432,
            user='glame_user',
            password='glame_password',
            database='glame_db'
        )
        print("✅ Подключение по DNS имени контейнера успешно!")
        await conn.close()
    except Exception as e:
        print(f"❌ Ошибка подключения по DNS: {e}")
        
    try:
        # Проверяем подключение по IP-адресу
        conn = await asyncpg.connect(
            host='172.18.0.3',
            port=5432,
            user='glame_user',
            password='glame_password',
            database='glame_db'
        )
        print("✅ Подключение по IP-адресу успешно!")
        await conn.close()
    except Exception as e:
        print(f"❌ Ошибка подключения по IP: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())