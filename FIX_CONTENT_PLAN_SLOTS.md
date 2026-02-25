# Исправление ошибки "Ошибка загрузки слотов плана"

## Проблема

При попытке загрузить слоты (items) контент-плана возникает ошибка:
```
Ошибка загрузки слотов плана
```

## Возможные причины

1. **Таблица `content_items` не существует** - самая частая причина
2. **Таблица `content_plans` не существует** - план не может быть найден
3. **Проблема с подключением к БД**
4. **План с указанным ID не существует**

## Решение

### Шаг 1: Убедитесь, что все таблицы созданы

Выполните скрипт создания таблиц:

```bash
cd backend
python create_content_tables.py
```

Этот скрипт создаст все необходимые таблицы:
- `content_plans`
- `content_items`
- `content_publications`

### Шаг 2: Проверьте, что таблицы существуют

Подключитесь к БД и проверьте:

```sql
-- Проверка таблиц
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name LIKE 'content_%'
ORDER BY table_name;

-- Должны быть видны:
-- content_items
-- content_plans
-- content_publications
```

### Шаг 3: Проверьте логи backend

Если ошибка сохраняется, проверьте логи backend для детальной информации об ошибке.

### Шаг 4: Проверьте, что план существует

Убедитесь, что план с указанным ID существует в таблице `content_plans`:

```sql
SELECT id, name, status, start_date, end_date 
FROM content_plans 
ORDER BY created_at DESC 
LIMIT 10;
```

## Что было исправлено в коде

1. ✅ Добавлена обработка ошибок в endpoint `/api/content/plans/{plan_id}/items`
2. ✅ Добавлена проверка существования плана перед загрузкой слотов
3. ✅ Улучшено логирование ошибок

## После исправления

1. Перезапустите backend
2. Попробуйте снова загрузить слоты плана
3. Если ошибка сохраняется, проверьте логи backend для детальной информации

## Дополнительная диагностика

Если проблема сохраняется, выполните:

```bash
# Проверка подключения к БД
cd backend
python -c "from app.database.connection import engine; print('Connected!' if engine else 'Failed')"

# Проверка миграций
python -m alembic current

# Применение миграций (если нужно)
python -m alembic upgrade head
```

## Связанные файлы

- `backend/app/api/content.py` - API endpoint для загрузки слотов
- `backend/create_content_tables.py` - Скрипт создания таблиц
- `FIX_CONTENT_PLANS_TABLE.md` - Инструкция по созданию таблиц
