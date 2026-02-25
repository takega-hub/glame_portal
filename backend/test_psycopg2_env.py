"""
Проверка переменных окружения PostgreSQL и альтернативных способов подключения
"""
import os
import sys

print("Checking PostgreSQL environment variables...")
pg_vars = ['PGHOST', 'PGPORT', 'PGDATABASE', 'PGUSER', 'PGPASSWORD', 'PGPASSFILE']
for var in pg_vars:
    value = os.getenv(var)
    if value:
        print(f"{var} = {value}")
        if isinstance(value, bytes):
            print(f"  (bytes): {list(value)}")
        else:
            print(f"  (string): {value}")
            print(f"  (bytes): {list(value.encode('utf-8'))}")
    else:
        print(f"{var} = (not set)")

print("\n" + "="*60)
print("Trying connection with cleared environment...")

# Временно очищаем переменные окружения PostgreSQL
import psycopg2

# Сохраняем оригинальные значения
original_env = {}
for var in pg_vars:
    original_env[var] = os.environ.get(var)
    if var in os.environ:
        del os.environ[var]

try:
    print("\n1. Connection with cleared PG* environment variables:")
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
finally:
    # Восстанавливаем переменные окружения
    for var, value in original_env.items():
        if value:
            os.environ[var] = value

# Пробуем использовать psycopg (новая версия) если доступна
print("\n" + "="*60)
print("Trying with psycopg (if available)...")
try:
    import psycopg
    print(f"psycopg version: {psycopg.__version__}")
    conn = psycopg.connect(
        host='localhost',
        port=5432,
        dbname='glame_db',
        user='glame_user',
        password='glame_password'
    )
    print("[OK] Connection with psycopg successful!")
    conn.close()
except ImportError:
    print("psycopg not available")
except Exception as e:
    print(f"[ERROR] Connection with psycopg failed: {e}")
