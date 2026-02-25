"""
Создание таблицы knowledge_documents через asyncpg
Обход проблемы с psycopg2
"""
import asyncio
import sys
import os
from pathlib import Path

# Исправление для Windows event loop
if sys.platform == 'win32':
    if isinstance(asyncio.get_event_loop_policy(), asyncio.WindowsProactorEventLoopPolicy):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Добавляем путь к app
sys.path.insert(0, str(Path(__file__).parent))

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

async def create_table():
    """Создание таблицы knowledge_documents через asyncpg"""
    # Получаем параметры подключения
    DB_HOST = safe_getenv("DB_HOST") or safe_getenv("DATABASE_HOST") or "localhost"
    DB_PORT = safe_getenv("DB_PORT") or safe_getenv("DATABASE_PORT") or "5432"
    DB_USER = safe_getenv("DB_USER") or safe_getenv("DATABASE_USER") or "glame_user"
    DB_PASSWORD = safe_getenv("DB_PASSWORD") or safe_getenv("DATABASE_PASSWORD") or "glame_password"
    DB_NAME = safe_getenv("DB_NAME") or safe_getenv("DATABASE_NAME") or "glame_db"
    
    # Пробуем получить из DATABASE_URL
    try:
        from urllib.parse import urlparse
        raw_url = safe_getenv("DATABASE_URL")
        if raw_url and raw_url.startswith('postgresql://'):
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
    
    print("=" * 60)
    print("Creating knowledge_documents table via asyncpg")
    print("=" * 60)
    print(f"Host: {DB_HOST}")
    print(f"Port: {DB_PORT}")
    print(f"Database: {DB_NAME}")
    print(f"User: {DB_USER}")
    print()
    
    try:
        import asyncpg
        
        print("Connecting to PostgreSQL...")
        conn = await asyncpg.connect(
            host=DB_HOST,
            port=int(DB_PORT),
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            timeout=10
        )
        
        print("[OK] Connected successfully!")
        print()
        
        print("Creating table knowledge_documents...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_documents (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                filename VARCHAR(255) NOT NULL,
                file_type VARCHAR(50) NOT NULL,
                file_size INTEGER,
                source VARCHAR(255),
                total_items INTEGER NOT NULL DEFAULT 0,
                uploaded_items INTEGER NOT NULL DEFAULT 0,
                failed_items INTEGER NOT NULL DEFAULT 0,
                vector_document_ids JSONB,
                document_metadata JSONB,
                status VARCHAR(50) NOT NULL DEFAULT 'completed',
                error_message TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE
            );
        """)
        print("[OK] Table created!")
        
        print("Creating indexes...")
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS ix_knowledge_documents_filename 
            ON knowledge_documents(filename);
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS ix_knowledge_documents_status 
            ON knowledge_documents(status);
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS ix_knowledge_documents_created_at 
            ON knowledge_documents(created_at);
        """)
        print("[OK] Indexes created!")
        
        # Проверяем, что таблица создана
        result = await conn.fetchval("""
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = 'knowledge_documents'
        """)
        
        if result > 0:
            print()
            print("=" * 60)
            print("[SUCCESS] Table 'knowledge_documents' created successfully!")
            print("=" * 60)
            
            # Показываем структуру таблицы
            columns = await conn.fetch("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'knowledge_documents'
                ORDER BY ordinal_position
            """)
            
            print("\nTable structure:")
            for col in columns:
                nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                print(f"  - {col['column_name']}: {col['data_type']} {nullable}")
        else:
            print()
            print("[ERROR] Table was not created")
            return False
        
        await conn.close()
        return True
        
    except ImportError:
        print("[ERROR] asyncpg is not installed.")
        print("Install it with: pip install asyncpg")
        return False
    except asyncpg.exceptions.InvalidPasswordError:
        print("[ERROR] Invalid password. Check DB_PASSWORD in .env file")
        return False
    except asyncpg.exceptions.InvalidCatalogNameError:
        print(f"[ERROR] Database '{DB_NAME}' does not exist.")
        print(f"Create it with: CREATE DATABASE {DB_NAME};")
        return False
    except (asyncpg.exceptions.ConnectionFailureError, asyncpg.exceptions.ConnectionDoesNotExistError) as e:
        print(f"[ERROR] Connection failed: {e}")
        print(f"Check if PostgreSQL is running on {DB_HOST}:{DB_PORT}")
        print(f"Also check firewall settings and PostgreSQL configuration (pg_hba.conf)")
        return False
    except Exception as e:
        print(f"[ERROR] Failed to create table: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    try:
        success = asyncio.run(create_table())
        if success:
            print("\nNext step: Mark migration as completed:")
            print("  alembic stamp head")
            print("\nOr manually:")
            print("  INSERT INTO alembic_version (version_num) VALUES ('003_knowledge_documents') ON CONFLICT DO NOTHING;")
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
