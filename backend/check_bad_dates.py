"""Проверка записей с неправильными датами"""
import asyncio
import asyncpg
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import json

if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

sys.path.insert(0, str(Path(__file__).parent))

env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

async def check_bad_dates():
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "5433"))
    DB_USER = os.getenv("DB_USER", "glame_user")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "glame_password")
    DB_NAME = os.getenv("DB_NAME", "glame_db")

    conn = await asyncpg.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    
    rows = await conn.fetch("""
        SELECT sale_date, product_article, product_name, raw_data, external_id
        FROM sales_records
        WHERE sync_batch_id LIKE 'historical_import%'
        AND sale_date < '2020-01-01'
        LIMIT 10
    """)
    
    print(f"Найдено записей с неправильными датами: {len(rows)}")
    print("=" * 80)
    
    for r in rows:
        print(f"\nДата: {r['sale_date']}")
        print(f"Артикул: {r['product_article']}")
        print(f"Товар: {r['product_name']}")
        print(f"External ID: {r['external_id']}")
        print(f"Raw data: {json.dumps(r['raw_data'], ensure_ascii=False, indent=2)}")
        print("-" * 80)
    
    await conn.close()

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(check_bad_dates())
