"""
Тест подключения к PostgreSQL через asyncpg из backend/venv.
Запуск:
  backend\\venv\\Scripts\\python.exe backend\\test_asyncpg_connection.py
"""

import asyncio
import sys

if sys.platform == "win32":
    # Для asyncpg на Windows стабильнее SelectorEventLoop
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import asyncpg


async def check(host: str) -> None:
    conn = await asyncpg.connect(
        host=host,
        port=5432,
        user="glame_user",
        password="glame_password",
        database="glame_db",
        timeout=5,
    )
    try:
        val = await conn.fetchval("select 1")
        print(f"[OK] asyncpg connect host={host}: {val}")
    finally:
        await conn.close()


async def main() -> None:
    for host in ("127.0.0.1", "localhost"):
        try:
            await check(host)
        except Exception as e:
            print(f"[FAIL] asyncpg connect host={host}: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())

