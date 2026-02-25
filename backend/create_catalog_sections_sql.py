"""
SQL скрипт для создания таблицы catalog_sections.
Можно выполнить напрямую через psql или другой SQL клиент.

Использование:
1. Через psql:
   psql -U glame_user -d glame_db -f backend/create_catalog_sections_sql.py

2. Через Docker:
   docker exec -i glame_postgres psql -U glame_user -d glame_db < backend/create_catalog_sections_sql.py

3. Или скопировать SQL команды и выполнить вручную
"""

SQL_SCRIPT = """
-- Проверяем, существует ли таблица
DO $$ 
BEGIN
    IF EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'catalog_sections'
    ) THEN
        RAISE NOTICE 'Таблица catalog_sections уже существует';
    ELSE
        -- Создаем таблицу catalog_sections
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
        );

        -- Создаем индексы
        CREATE INDEX ix_catalog_sections_external_id ON catalog_sections (external_id);
        CREATE INDEX ix_catalog_sections_external_code ON catalog_sections (external_code);
        CREATE INDEX ix_catalog_sections_parent_external_id ON catalog_sections (parent_external_id);
        CREATE INDEX ix_catalog_sections_is_active ON catalog_sections (is_active);

        RAISE NOTICE 'Таблица catalog_sections успешно создана';
    END IF;
END $$;
"""

if __name__ == "__main__":
    print("=" * 60)
    print("SQL скрипт для создания таблицы catalog_sections")
    print("=" * 60)
    print("\nВыполните следующие команды в PostgreSQL:\n")
    print(SQL_SCRIPT)
    print("\n" + "=" * 60)
    print("Или сохраните SQL в файл и выполните:")
    print("  psql -U glame_user -d glame_db -f catalog_sections.sql")
    print("=" * 60)
