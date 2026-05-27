# Исправление ошибки: таблица content_plans не существует

## Проблема

Ошибка при сохранении плана контента:
```
relation "content_plans" does not exist
```

## Решение

Таблица `content_plans` не была создана в базе данных. Есть несколько способов исправить это:

### Способ 1: Применить миграцию через Alembic (рекомендуется)

```bash
cd backend
python -m alembic upgrade head
```

Если это не работает, попробуйте:

```bash
cd backend
python -m alembic upgrade 004_add_content_tables
```

### Способ 2: Использовать скрипт создания таблиц (рекомендуется для Windows)

```bash
cd backend
python create_content_tables.py
```

Этот скрипт использует asyncpg и должен работать надежно на Windows.

### Способ 3: Создать таблицы через SQL напрямую

Подключитесь к PostgreSQL и выполните SQL из файла `backend/create_tables.sql`:

```bash
# Через psql
psql -h localhost -p 5433 -U glame_user -d glame_db -f backend/create_tables.sql

# Или через Docker
docker exec -i glame-postgres psql -U glame_user -d glame_db < backend/create_tables.sql
```

### Способ 4: Выполнить SQL вручную

Подключитесь к базе данных и выполните:

```sql
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
```

## Проверка

После создания таблиц проверьте, что они существуют:

```sql
-- Проверка таблиц
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name LIKE 'content_%';

-- Должны быть видны:
-- content_plans
-- content_items
-- content_publications
```

## Примечания

1. Убедитесь, что Docker контейнеры запущены:
   ```bash
   cd infra
   docker-compose ps
   ```

2. Проверьте подключение к БД:
   ```bash
   cd backend
   python -c "from app.database.connection import engine; print('Connected!' if engine else 'Failed')"
   ```

3. Если миграции не применяются, проверьте файл `data/migrations/env.py` - там должны быть импортированы все модели, включая `ContentPlan`, `ContentItem`, `ContentPublication`.

## После исправления

После создания таблиц перезапустите backend и попробуйте снова создать план контента.
