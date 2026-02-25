"""
Скрипт для создания таблицы catalog_sections напрямую через SQLAlchemy.
Работает на Windows, использует синхронный движок SQLAlchemy.

Использование: python backend/create_catalog_sections_table.py
"""
import os
import sys
from pathlib import Path
from getpass import getpass
from dotenv import load_dotenv

# Настройка кодировки для Windows
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# Загружаем переменные окружения с fallback по кодировкам (Windows-safe)
def load_env_with_fallback(env_path: Path) -> None:
    """Загружает .env с fallback по кодировкам, чтобы избежать UnicodeDecodeError."""
    try:
        if not env_path.exists():
            load_dotenv()
            return
        raw = env_path.read_bytes()
        for encoding in ("utf-8", "cp1251", "cp866", "latin-1"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = raw.decode("utf-8", errors="replace")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ[key] = value
    except Exception:
        load_dotenv()

env_path = Path(__file__).parent.parent / ".env"
load_env_with_fallback(env_path)

# Импортируем SQLAlchemy синхронный движок
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import OperationalError

# Функция для безопасного получения переменных окружения
def safe_getenv(key, default=None):
    """Безопасное получение переменной окружения с обработкой кодировки"""
    try:
        value = os.getenv(key, default)
        if value is None:
            return default
        # Если это bytes, декодируем
        if isinstance(value, bytes):
            # Пробуем разные кодировки
            for encoding in ['utf-8', 'latin-1', 'cp1251', 'cp866']:
                try:
                    value = value.decode(encoding, errors='strict')
                    break
                except UnicodeDecodeError:
                    continue
            else:
                # Если ничего не помогло, используем replace
                value = value.decode('utf-8', errors='replace')
        # Преобразуем в строку и очищаем
        value = str(value).strip()
        # Убираем BOM и невидимые символы
        value = value.strip('\ufeff').strip('\x00')
        return value
    except Exception as e:
        print(f"Warning: Error getting env {key}: {e}")
        return default

# Параметры подключения к БД из переменных окружения
DB_HOST = safe_getenv('DB_HOST', 'localhost')
DB_PORT = int(safe_getenv('DB_PORT', '5433') or '5433')
DB_NAME = safe_getenv('DB_NAME', 'glame_db')
DB_USER = safe_getenv('DB_USER', 'glame_user')
DB_PASSWORD = safe_getenv('DB_PASSWORD', 'glame_password')

# Формируем URL подключения с правильным кодированием (fallback на параметры)
from urllib.parse import quote_plus

try:
    username_encoded = quote_plus(DB_USER, safe="")
    password_encoded = quote_plus(DB_PASSWORD, safe="")
    DATABASE_URL = f"postgresql://{username_encoded}:{password_encoded}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    DATABASE_URL.encode("ascii")
except (UnicodeEncodeError, UnicodeDecodeError) as e:
    print(f"Warning: Encoding error in DATABASE_URL, using direct params: {e}")
    DATABASE_URL = None


def create_catalog_sections_table():
    """Создание таблицы catalog_sections"""
    engine = None
    try:
        print("=" * 60)
        print("Создание таблицы catalog_sections")
        print("=" * 60)
        
        # Создаем синхронный движок SQLAlchemy
        print(f"\nПодключение к базе данных {DB_NAME} на {DB_HOST}:{DB_PORT}...")
        engine = _create_engine()
        
        # Проверяем подключение
        try:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT version()"))
                version = result.scalar()
                print(f"✓ Подключение установлено")
                print(f"  PostgreSQL версия: {version.split(',')[0]}")
        except UnicodeDecodeError:
            # Пробуем запросить пароль вручную и подключиться повторно
            print("\n⚠ Ошибка кодировки при подключении. Введите пароль вручную.")
            manual_password = getpass("DB_PASSWORD: ")
            engine.dispose()
            engine = _create_engine(password_override=manual_password)
            with engine.connect() as conn:
                result = conn.execute(text("SELECT version()"))
                version = result.scalar()
                print(f"✓ Подключение установлено (manual password)")
                print(f"  PostgreSQL версия: {version.split(',')[0]}")
        
        # Проверяем, существует ли таблица
        inspector = inspect(engine)
        table_exists = 'catalog_sections' in inspector.get_table_names()
        
        if table_exists:
            print("\n⚠ Таблица catalog_sections уже существует")
            response = input("Пересоздать таблицу? (y/n): ")
            if response.lower() != 'y':
                print("Отменено")
                return
            print("Удаление существующей таблицы...")
            with engine.begin() as conn:
                conn.execute(text("DROP TABLE IF EXISTS catalog_sections CASCADE;"))
            print("✓ Таблица удалена")
        
        # Создание таблицы
        print("\nСоздание таблицы catalog_sections...")
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE catalog_sections (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    external_id VARCHAR(255) NOT NULL UNIQUE,
                    external_code VARCHAR(100),
                    name VARCHAR(255) NOT NULL,
                    parent_external_id VARCHAR(255),
                    description TEXT,
                    onec_metadata JSONB,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    sync_status VARCHAR(50),
                    sync_metadata JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE
                )
            """))
        print("✓ Таблица создана")
        
        # Создание индексов
        print("\nСоздание индексов...")
        indexes = [
            ("ix_catalog_sections_external_id", "external_id"),
            ("ix_catalog_sections_external_code", "external_code"),
            ("ix_catalog_sections_parent_external_id", "parent_external_id"),
            ("ix_catalog_sections_is_active", "is_active"),
        ]
        
        with engine.begin() as conn:
            for idx_name, column in indexes:
                # Проверяем, существует ли индекс
                result = conn.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM pg_indexes 
                        WHERE indexname = :idx_name
                    )
                """), {"idx_name": idx_name})
                idx_exists = result.scalar()
                
                if not idx_exists:
                    conn.execute(text(f"""
                        CREATE INDEX {idx_name} ON catalog_sections ({column})
                    """))
                    print(f"✓ Индекс {idx_name} создан")
                else:
                    print(f"⚠ Индекс {idx_name} уже существует")
        
        print("\n✅ Таблица catalog_sections успешно создана!")
        print("\nСтруктура таблицы:")
        print("  - id: UUID (primary key)")
        print("  - external_id: VARCHAR(255) UNIQUE (Ref_Key из 1С)")
        print("  - external_code: VARCHAR(100) (Code из 1С)")
        print("  - name: VARCHAR(255) (название раздела)")
        print("  - parent_external_id: VARCHAR(255) (родительский раздел)")
        print("  - description: TEXT")
        print("  - onec_metadata: JSONB (полные данные из 1С)")
        print("  - is_active: BOOLEAN")
        print("  - sync_status: VARCHAR(50)")
        print("  - sync_metadata: JSONB")
        print("  - created_at: TIMESTAMP")
        print("  - updated_at: TIMESTAMP")
        
    except OperationalError as e:
        print(f"\n❌ Ошибка подключения к базе данных: {e}")
        print("\nПроверьте:")
        print("  1. Запущен ли PostgreSQL")
        print("  2. Правильность параметров подключения в .env файле")
        print("  3. Доступность базы данных по адресу {DB_HOST}:{DB_PORT}")
        raise
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        if engine:
            engine.dispose()
            print("\n✓ Соединение закрыто")


def _create_engine(password_override: str | None = None):
    """Создает SQLAlchemy engine с fallback на ввод пароля."""
    # Используем URL или параметры напрямую
    if DATABASE_URL and password_override is None:
        return create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            echo=False
        )

    # Используем параметры напрямую (обход проблем с кодировкой в URL)
    from sqlalchemy.engine.url import URL
    db_url = URL.create(
        drivername="postgresql",
        username=DB_USER,
        password=password_override or DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME
    )
    return create_engine(
        db_url,
        pool_pre_ping=True,
        echo=False
    )


if __name__ == "__main__":
    try:
        create_catalog_sections_table()
    except KeyboardInterrupt:
        print("\n\nПрервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nКритическая ошибка: {e}")
        sys.exit(1)
