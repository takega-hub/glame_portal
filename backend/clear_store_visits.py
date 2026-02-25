import os
import psycopg2
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()
database_url = os.getenv("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")
parsed = urlparse(database_url)

conn = psycopg2.connect(
    host=parsed.hostname,
    port=parsed.port or 5432,
    database=parsed.path[1:],
    user=parsed.username,
    password=parsed.password
)

cursor = conn.cursor()
cursor.execute("DELETE FROM store_visits")
conn.commit()

print(f"[OK] Deleted all store_visits records")

cursor.close()
conn.close()
