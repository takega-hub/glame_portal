"""
Диагностический скрипт для анализа проблемы с DATABASE_URL
"""
import os
from urllib.parse import quote_plus, urlparse
from dotenv import load_dotenv

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

# Получаем DATABASE_URL
raw_url = safe_getenv("DATABASE_URL")
print("=" * 60)
print("ANALYSIS OF DATABASE_URL")
print("=" * 60)

if raw_url:
    print(f"\n1. Raw DATABASE_URL:")
    print(f"   {raw_url}")
    print(f"   Length: {len(raw_url)}")
    
    # Анализ байтов
    try:
        url_bytes = raw_url.encode('utf-8')
        print(f"\n2. URL as UTF-8 bytes:")
        print(f"   Total bytes: {len(url_bytes)}")
        
        if len(url_bytes) > 61:
            print(f"\n3. Byte at position 61:")
            print(f"   Byte value: 0x{url_bytes[61]:02x} ({url_bytes[61]})")
            print(f"   Bytes around position 61:")
            start = max(0, 55)
            end = min(len(url_bytes), 68)
            for i in range(start, end):
                marker = " <-- POSITION 61" if i == 61 else ""
                print(f"   [{i:2d}] 0x{url_bytes[i]:02x} ({url_bytes[i]:3d}) '{chr(url_bytes[i]) if 32 <= url_bytes[i] < 127 else '?'}'{marker}")
            
            # Пробуем декодировать проблемную область
            print(f"\n4. Trying to decode bytes around position 61:")
            try:
                decoded = url_bytes[55:68].decode('utf-8')
                print(f"   Decoded: '{decoded}'")
            except UnicodeDecodeError as e:
                print(f"   ERROR: Cannot decode - {e}")
                print(f"   Problematic bytes: {list(url_bytes[55:68])}")
        else:
            print(f"\n3. URL is shorter than 61 bytes")
    except Exception as e:
        print(f"   ERROR analyzing bytes: {e}")
    
    # Парсим URL
    print(f"\n5. Parsed URL components:")
    try:
        parsed = urlparse(raw_url)
        print(f"   Scheme: {parsed.scheme}")
        print(f"   Username: {parsed.username}")
        print(f"   Password length: {len(parsed.password) if parsed.password else 0}")
        if parsed.password:
            pwd_bytes = parsed.password.encode('utf-8')
            print(f"   Password bytes: {list(pwd_bytes)}")
            print(f"   Password (first 20 chars): {parsed.password[:20]}")
        print(f"   Hostname: {parsed.hostname}")
        print(f"   Port: {parsed.port}")
        print(f"   Database: {parsed.path}")
    except Exception as e:
        print(f"   ERROR parsing URL: {e}")
    
    # Пробуем пересобрать URL
    print(f"\n6. Rebuilding URL with proper encoding:")
    try:
        parsed = urlparse(raw_url)
        username = parsed.username or 'glame_user'
        password = parsed.password or 'glame_password'
        hostname = parsed.hostname or 'localhost'
        port = parsed.port or 5432
        database = parsed.path.lstrip('/') or 'glame_db'
        
        # Анализ пароля
        print(f"   Original password bytes: {list(password.encode('utf-8'))}")
        password_encoded = quote_plus(password, safe='')
        print(f"   Encoded password: {password_encoded}")
        print(f"   Encoded password bytes: {list(password_encoded.encode('utf-8'))}")
        
        username_encoded = quote_plus(username, safe='')
        clean_url = f"postgresql://{username_encoded}:{password_encoded}@{hostname}:{port}/{database}"
        
        print(f"   Clean URL length: {len(clean_url)}")
        clean_bytes = clean_url.encode('utf-8')
        if len(clean_bytes) > 61:
            print(f"   Clean URL bytes at position 61: 0x{clean_bytes[61]:02x} ({clean_bytes[61]})")
        else:
            print(f"   Clean URL is shorter than 61 bytes")
        
        # Проверка на ASCII
        try:
            clean_url.encode('ascii')
            print(f"   [OK] Clean URL is pure ASCII")
        except UnicodeEncodeError:
            print(f"   [ERROR] Clean URL contains non-ASCII characters")
            # Найдем проблемные символы
            for i, char in enumerate(clean_url):
                try:
                    char.encode('ascii')
                except UnicodeEncodeError:
                    print(f"   Non-ASCII char at position {i}: '{char}' (0x{ord(char):04x})")
    except Exception as e:
        print(f"   ERROR rebuilding URL: {e}")
        import traceback
        traceback.print_exc()
else:
    print("\nDATABASE_URL is not set, using individual variables:")
    DB_HOST = safe_getenv("DB_HOST", "localhost")
    DB_PORT = safe_getenv("DB_PORT", "5432")
    DB_USER = safe_getenv("DB_USER", "glame_user")
    DB_PASSWORD = safe_getenv("DB_PASSWORD", "glame_password")
    DB_NAME = safe_getenv("DB_NAME", "glame_db")
    
    print(f"   Host: {DB_HOST}")
    print(f"   Port: {DB_PORT}")
    print(f"   User: {DB_USER}")
    print(f"   Password length: {len(DB_PASSWORD)}")
    print(f"   Password bytes: {list(DB_PASSWORD.encode('utf-8'))}")
    print(f"   Database: {DB_NAME}")

print("\n" + "=" * 60)
