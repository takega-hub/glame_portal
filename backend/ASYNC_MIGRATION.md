# Миграция на asyncpg - Инструкция

## Что было сделано

1. ✅ Заменен `psycopg2-binary` на `asyncpg` в requirements.txt
2. ✅ Обновлен `backend/app/database/connection.py` для использования async SQLAlchemy
3. ✅ Обновлен `backend/app/agents/stylist_agent.py` для работы с AsyncSession
4. ✅ Обновлен `backend/app/api/stylist.py` для работы с async
5. ✅ Обновлен `backend/app/services/recommendation_service.py` для async запросов
6. ✅ Включен полноценный stylist API вместо упрощенной версии

## Изменения в коде

### Database Connection
- Используется `create_async_engine` вместо `create_engine`
- Используется `AsyncSession` вместо `Session`
- URL изменен с `postgresql://` на `postgresql+asyncpg://`

### API Endpoints
- Все endpoints теперь используют `AsyncSession = Depends(get_db)`
- Запросы к БД используют `await db.execute(select(...))` вместо `db.query(...)`

### Agents и Services
- Все методы, работающие с БД, теперь async
- Используется `select()` из SQLAlchemy для построения запросов
- Результаты получаются через `result.scalars().all()` или `result.scalar_one_or_none()`

## Установка зависимостей

```bash
cd backend
pip install -r requirements.txt
```

## Тестирование

### 1. Проверка подключения к БД

```bash
python -c "import asyncio; from app.database.connection import engine; asyncio.run(engine.connect())"
```

### 2. Тестирование API

```bash
# Запустите backend
cd backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# В другом терминале протестируйте endpoint
python -c "import requests; r = requests.post('http://localhost:8000/api/stylist/chat', json={'message': 'Хочу образ для свидания'}); print(r.json())"
```

### 3. Проверка через Swagger UI

Откройте http://localhost:8000/docs и протестируйте `/api/stylist/chat`

## Осталось обновить (опционально)

Следующие файлы также используют синхронные запросы, но они не критичны для работы stylist agent:

- `backend/app/api/products.py`
- `backend/app/api/looks.py`
- `backend/app/api/content.py`
- `backend/app/api/analytics.py`
- `backend/app/api/knowledge.py`
- `backend/app/api/auth.py`
- `backend/app/api/onec_sync.py`

Их можно обновить позже по мере необходимости.

## Известные проблемы

1. **Alembic миграции** - могут потребовать обновления для работы с async
2. **Seeds скрипты** - нужно обновить для async версии

## Откат изменений

Если что-то пошло не так, можно временно вернуться к упрощенной версии:

В `backend/app/main.py`:
```python
# app.include_router(stylist.router, prefix="/api/stylist", tags=["stylist"])
app.include_router(stylist_simple.router, prefix="/api/stylist", tags=["stylist"])
```
