"""
Создание таблицы knowledge_documents напрямую через SQLAlchemy
Обход проблемы с psycopg2 и Alembic
"""
import sys
import os
from pathlib import Path

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

def create_table_via_sql():
    """Создание таблицы через SQL напрямую"""
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
    
    print("Creating table via SQLAlchemy with asyncpg...")
    
    try:
        from sqlalchemy import create_engine, text
        from urllib.parse import quote_plus
        
        # Используем asyncpg через SQLAlchemy
        username_encoded = quote_plus(DB_USER, safe='')
        password_encoded = quote_plus(DB_PASSWORD, safe='')
        asyncpg_url = f"postgresql+asyncpg://{username_encoded}:{password_encoded}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        
        # Но для синхронного выполнения нужен синхронный драйвер
        # Используем psycopg2, но с параметрами подключения
        sync_url = f"postgresql+psycopg2://{username_encoded}:{password_encoded}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        
        print(f"Connecting to: postgresql://***:***@{DB_HOST}:{DB_PORT}/{DB_NAME}")
        
        # Пробуем создать engine
        engine = create_engine(
            sync_url,
            connect_args={
                'client_encoding': 'utf8',
                'options': '-c client_encoding=utf8'
            },
            echo=False
        )
        
        # Создаем таблицу через SQL
        with engine.connect() as conn:
            conn.execute(text("""
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
            """))
            
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_knowledge_documents_filename 
                ON knowledge_documents(filename);
            """))
            
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_knowledge_documents_status 
                ON knowledge_documents(status);
            """))
            
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_knowledge_documents_created_at 
                ON knowledge_documents(created_at);
            """))
            
            conn.commit()
        
        print("[OK] Table 'knowledge_documents' created successfully!")
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to create table: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = create_table_via_sql()
    sys.exit(0 if success else 1)
