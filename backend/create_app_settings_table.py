import asyncio
import sys


async def main():
    # Используем тот же engine/URL, что и backend (psycopg3 + порт 5433 по умолчанию)
    from sqlalchemy import text
    from app.database.connection import engine

    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS app_settings (
                  key VARCHAR(100) PRIMARY KEY,
                  value VARCHAR(500) NOT NULL,
                  updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
            )
        )

    print("OK: app_settings table exists")


if __name__ == "__main__":
    # Windows: psycopg async не поддерживает ProactorEventLoop, нужен Selector loop policy
    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass
    asyncio.run(main())

