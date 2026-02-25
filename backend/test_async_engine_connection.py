"""
Проверка подключения через SQLAlchemy AsyncEngine (psycopg3).

Запуск:
  backend\\venv\\Scripts\\python.exe backend\\test_async_engine_connection.py
"""

import asyncio
from sqlalchemy import text
from app.database.connection import engine


async def main() -> None:
    async with engine.connect() as conn:
        val = await conn.scalar(text("select 1"))
        print("[OK] sqlalchemy async engine:", val)


if __name__ == "__main__":
    asyncio.run(main())

