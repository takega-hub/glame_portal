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

# Проверяем данные store_visits
cursor.execute("SELECT COUNT(*) FROM store_visits")
count = cursor.fetchone()[0]
print(f"Total store_visits records: {count}")

if count > 0:
    cursor.execute("SELECT MIN(date), MAX(date) FROM store_visits")
    date_range = cursor.fetchone()
    print(f"Date range: {date_range[0]} to {date_range[1]}")
    
    cursor.execute("SELECT SUM(visitor_count), SUM(sales_count) FROM store_visits")
    totals = cursor.fetchone()
    print(f"Total visitors: {totals[0]}, Total sales: {totals[1]}")
    
    # Проверяем типы данных
    cursor.execute("SELECT date, visitor_count, sales_count FROM store_visits LIMIT 5")
    samples = cursor.fetchall()
    print("\nSample records:")
    for row in samples:
        print(f"  Date: {row[0]} (type: {type(row[0])}), Visitors: {row[1]}, Sales: {row[2]}")

cursor.close()
conn.close()
