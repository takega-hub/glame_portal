"""
Простой скрипт для создания таблиц content_plans, content_items, content_publications
"""
import asyncio
import asyncpg
import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные окружения
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

async def create_tables():
    """Создает таблицы для content plans"""
    
    # Параметры подключения
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "5433"))
    DB_USER = os.getenv("DB_USER", "glame_user")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "glame_password")
    DB_NAME = os.getenv("DB_NAME", "glame_db")
    
    print(f"Подключение к БД: {DB_HOST}:{DB_PORT}/{DB_NAME} как {DB_USER}")
    
    try:
        conn = await asyncpg.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        
        print("✅ Подключение установлено")
        
        # SQL для создания таблиц
        sql = """
        -- Создание таблицы content_plans
        CREATE TABLE IF NOT EXISTS content_plans (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255),
            status VARCHAR(50) NOT NULL DEFAULT 'draft',
            start_date TIMESTAMP WITH TIME ZONE NOT NULL,
            end_date TIMESTAMP WITH TIME ZONE NOT NULL,
            timezone VARCHAR(64) NOT NULL DEFAULT 'Europe/Moscow',
            inputs JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE
        );

        CREATE INDEX IF NOT EXISTS ix_content_plans_status ON content_plans(status);
        CREATE INDEX IF NOT EXISTS ix_content_plans_start_date ON content_plans(start_date);
        CREATE INDEX IF NOT EXISTS ix_content_plans_end_date ON content_plans(end_date);

        -- Создание таблицы content_items
        CREATE TABLE IF NOT EXISTS content_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            plan_id UUID NOT NULL REFERENCES content_plans(id),
            scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL,
            timezone VARCHAR(64) NOT NULL DEFAULT 'Europe/Moscow',
            channel VARCHAR(64) NOT NULL,
            content_type VARCHAR(64) NOT NULL DEFAULT 'post',
            topic VARCHAR(500),
            hook VARCHAR(500),
            cta VARCHAR(500),
            persona VARCHAR(500),
            cjm_stage VARCHAR(64),
            goal VARCHAR(500),
            spec JSONB,
            generated JSONB,
            generated_text TEXT,
            status VARCHAR(50) NOT NULL DEFAULT 'planned',
            published_at TIMESTAMP WITH TIME ZONE,
            publication_metadata JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE
        );

        CREATE INDEX IF NOT EXISTS ix_content_items_plan_id ON content_items(plan_id);
        CREATE INDEX IF NOT EXISTS ix_content_items_scheduled_at ON content_items(scheduled_at);
        CREATE INDEX IF NOT EXISTS ix_content_items_status ON content_items(status);
        CREATE INDEX IF NOT EXISTS ix_content_items_channel ON content_items(channel);

        -- Создание таблицы content_publications
        CREATE TABLE IF NOT EXISTS content_publications (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            item_id UUID NOT NULL REFERENCES content_items(id),
            provider VARCHAR(64) NOT NULL DEFAULT 'glame',
            status VARCHAR(50) NOT NULL DEFAULT 'created',
            external_id VARCHAR(255),
            request_payload JSONB,
            response_payload JSONB,
            error_message TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS ix_content_publications_item_id ON content_publications(item_id);
        CREATE INDEX IF NOT EXISTS ix_content_publications_status ON content_publications(status);
        """
        
        await conn.execute(sql)
        print("✅ Таблицы успешно созданы!")
        
        # Проверяем, что таблицы существуют
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name LIKE 'content_%'
            ORDER BY table_name
        """)
        
        print("\n📋 Созданные таблицы:")
        for table in tables:
            print(f"   - {table['table_name']}")
        
        await conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Настройка для Windows
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    success = asyncio.run(create_tables())
    exit(0 if success else 1)
