"""
Проверка подключения к PostgreSQL через psycopg3 AsyncConnection.
Запуск:
  backend\\venv\\Scripts\\python.exe backend\\test_psycopg_async_direct.py
"""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

# Важно: установить policy ДО asyncio.run()
if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import psycopg


def _safe(s: str) -> str:
    return s.encode("utf-8", "backslashreplace").decode("utf-8")


async def main() -> None:
    dsn = os.getenv("DATABASE_URL") or "postgresql://glame_user:glame_password@localhost:5432/glame_db"
    # psycopg3 использует "postgresql://" DSN
    if dsn.startswith("postgresql+psycopg://"):
        dsn = dsn.replace("postgresql+psycopg://", "postgresql://", 1)
    if dsn.startswith("postgresql+asyncpg://"):
        dsn = dsn.replace("postgresql+asyncpg://", "postgresql://", 1)

    print("DSN:", dsn)
    try:
        async with await psycopg.AsyncConnection.connect(dsn, connect_timeout=5) as conn:
            async with conn.cursor() as cur:
                await cur.execute("select 1")
                row = await cur.fetchone()
                print("[OK] psycopg3 async:", row)
    except Exception as e:
        msg = _safe(f"{type(e).__name__}: {e}")
        print("[FAIL] psycopg3 async:", msg)


if __name__ == "__main__":
    asyncio.run(main())

