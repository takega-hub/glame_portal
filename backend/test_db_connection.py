"""
Скрипт для проверки подключения к базе данных
"""
import os
import sys
from urllib.parse import quote_plus, urlparse
from dotenv import load_dotenv

# Загружаем .env
load_dotenv()

def safe_getenv(key, default=None):
    """Безопасное получение переменной окружения"""
    try:
        value = os.getenv(key, default)
        if value is None:
            return default
        if isinstance(value, bytes):
            value = value.decode('utf-8', errors='replace')
        return str(value).strip().strip('\ufeff').strip('\x00')
    except Exception:
        return default

def build_database_url():
    """Построение DATABASE_URL с правильным кодированием"""
    DB_HOST = safe_getenv("DB_HOST") or safe_getenv("DATABASE_HOST") or "localhost"
    DB_PORT = safe_getenv("DB_PORT") or safe_getenv("DATABASE_PORT") or "5432"
    DB_USER = safe_getenv("DB_USER") or safe_getenv("DATABASE_USER") or "glame_user"
    DB_PASSWORD = safe_getenv("DB_PASSWORD") or safe_getenv("DATABASE_PASSWORD") or "glame_password"
    DB_NAME = safe_getenv("DB_NAME") or safe_getenv("DATABASE_NAME") or "glame_db"
    
    raw_url = safe_getenv("DATABASE_URL")
    
    if raw_url and raw_url.startswith('postgresql://'):
        try:
            parsed = urlparse(raw_url)
            username = parsed.username or DB_USER
            password = parsed.password or DB_PASSWORD
            hostname = parsed.hostname or DB_HOST
            port = parsed.port or int(DB_PORT)
            database = parsed.path.lstrip('/') or DB_NAME
            
            username_encoded = quote_plus(username, safe='')
            password_encoded = quote_plus(password, safe='')
            
            database_url = f"postgresql://{username_encoded}:{password_encoded}@{hostname}:{port}/{database}"
            database_url.encode('ascii')
            return database_url
        except Exception as e:
            print(f"Error parsing DATABASE_URL: {e}")
    
    username_encoded = quote_plus(DB_USER, safe='')
    password_encoded = quote_plus(DB_PASSWORD, safe='')
    return f"postgresql://{username_encoded}:{password_encoded}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

if __name__ == "__main__":
    # Получаем компоненты подключения напрямую
    DB_HOST = safe_getenv("DB_HOST") or safe_getenv("DATABASE_HOST") or "localhost"
    DB_PORT = safe_getenv("DB_PORT") or safe_getenv("DATABASE_PORT") or "5432"
    DB_USER = safe_getenv("DB_USER") or safe_getenv("DATABASE_USER") or "glame_user"
    DB_PASSWORD = safe_getenv("DB_PASSWORD") or safe_getenv("DATABASE_PASSWORD") or "glame_password"
    DB_NAME = safe_getenv("DB_NAME") or safe_getenv("DATABASE_NAME") or "glame_db"
    
    # Пробуем получить из DATABASE_URL
    try:
        raw_url = safe_getenv("DATABASE_URL")
        if raw_url and raw_url.startswith('postgresql://'):
            from urllib.parse import urlparse
            parsed = urlparse(raw_url)
            if parsed.username:
                DB_USER = parsed.username
            if parsed.password:
                DB_PASSWORD = parsed.password
            if parsed.hostname:
                DB_HOST = parsed.hostname
            if parsed.port:
                DB_PORT = str(parsed.port)
            if parsed.path:
                DB_NAME = parsed.path.lstrip('/')
    except Exception:
        pass
    
    # Очищаем от не-ASCII символов
    DB_USER = DB_USER.encode('ascii', errors='ignore').decode('ascii')
    DB_PASSWORD = DB_PASSWORD.encode('ascii', errors='ignore').decode('ascii')
    DB_HOST = DB_HOST.encode('ascii', errors='ignore').decode('ascii')
    DB_NAME = DB_NAME.encode('ascii', errors='ignore').decode('ascii')
    
    print(f"Connection params: host={DB_HOST}, port={DB_PORT}, database={DB_NAME}, user={DB_USER}")
    print(f"Password length: {len(DB_PASSWORD)}, Password bytes: {list(DB_PASSWORD.encode('utf-8'))}")
    
    try:
        # Пробуем подключиться через параметры напрямую (избегаем проблем с DSN строкой)
        import psycopg2
        
        # Очищаем все параметры от не-ASCII символов
        DB_HOST_CLEAN = DB_HOST.encode('ascii', errors='ignore').decode('ascii')
        DB_USER_CLEAN = DB_USER.encode('ascii', errors='ignore').decode('ascii')
        DB_PASSWORD_CLEAN = DB_PASSWORD.encode('ascii', errors='ignore').decode('ascii')
        DB_NAME_CLEAN = DB_NAME.encode('ascii', errors='ignore').decode('ascii')
        
        print(f"Cleaned params: host={DB_HOST_CLEAN}, user={DB_USER_CLEAN}, database={DB_NAME_CLEAN}")
        print(f"Cleaned password bytes: {list(DB_PASSWORD_CLEAN.encode('utf-8'))}")
        
        # Пробуем подключиться через параметры
        conn = psycopg2.connect(
            host=DB_HOST_CLEAN,
            port=int(DB_PORT),
            database=DB_NAME_CLEAN,
            user=DB_USER_CLEAN,
            password=DB_PASSWORD_CLEAN
        )
        print("[OK] Connection successful!")
        conn.close()
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        import traceback
        traceback.print_exc()
        
        # Пробуем с дефолтными значениями
        print("\nTrying with default values directly...")
        try:
            import psycopg2
            conn = psycopg2.connect(
                host='localhost',
                port=5432,
                database='glame_db',
                user='glame_user',
                password='glame_password'
            )
            print("✓ Connection with defaults successful!")
            conn.close()
        except Exception as e2:
            print(f"✗ Default connection also failed: {e2}")
