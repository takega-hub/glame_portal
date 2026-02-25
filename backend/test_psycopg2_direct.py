"""
Прямой тест подключения к PostgreSQL без использования переменных окружения
"""
import psycopg2
import sys

print("Testing direct psycopg2 connection...")
print(f"Python version: {sys.version}")
print(f"psycopg2 version: {psycopg2.__version__}")

# Пробуем подключиться с жестко заданными параметрами
try:
    print("\n1. Trying with hardcoded ASCII parameters:")
    conn = psycopg2.connect(
        host='localhost',
        port=5432,
        database='glame_db',
        user='glame_user',
        password='glame_password'
    )
    print("[OK] Connection successful!")
    conn.close()
except Exception as e:
    print(f"[ERROR] Connection failed: {e}")
    import traceback
    traceback.print_exc()

# Пробуем через DSN строку
try:
    print("\n2. Trying with DSN string:")
    dsn = "postgresql://glame_user:glame_password@localhost:5432/glame_db"
    print(f"DSN length: {len(dsn)}")
    print(f"DSN bytes: {list(dsn.encode('utf-8'))}")
    
    # Проверяем байт на позиции 61
    dsn_bytes = dsn.encode('utf-8')
    if len(dsn_bytes) > 61:
        print(f"Byte at position 61: 0x{dsn_bytes[61]:02x} ({dsn_bytes[61]})")
    
    conn = psycopg2.connect(dsn)
    print("[OK] Connection with DSN successful!")
    conn.close()
except Exception as e:
    print(f"[ERROR] Connection with DSN failed: {e}")
    import traceback
    traceback.print_exc()

# Пробуем через параметры с явным указанием кодировки
try:
    print("\n3. Trying with connection string parameters:")
    conn = psycopg2.connect(
        "host=localhost port=5432 dbname=glame_db user=glame_user password=glame_password"
    )
    print("[OK] Connection with connection string successful!")
    conn.close()
except Exception as e:
    print(f"[ERROR] Connection with connection string failed: {e}")
    import traceback
    traceback.print_exc()
