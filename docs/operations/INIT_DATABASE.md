# Инициализация базы данных

Инструкция по созданию и инициализации базы данных с нуля.

## Предварительные требования

1. **PostgreSQL должен быть запущен**
   - Локально через Docker: `docker-compose -f infra/docker-compose.yml up -d postgres`
   - Или установленный PostgreSQL на хосте

2. **Переменные окружения настроены**
   - Скопируйте `ENV.example` в `.env` в корне проекта
   - Заполните необходимые переменные (минимум `OPENROUTER_API_KEY`)

## Быстрая инициализация

### Windows (PowerShell)
```powershell
cd backend
.\init_database.ps1
```

### Windows (CMD)
```cmd
cd backend
init_database.bat
```

### Linux/Mac
```bash
cd backend
python init_database.py
```

## Ручная инициализация

Если автоматический скрипт не работает, выполните шаги вручную:

### 1. Запустите PostgreSQL

```bash
docker-compose -f infra/docker-compose.yml up -d postgres
```

Дождитесь, пока контейнер запустится (проверьте статус: `docker ps`)

### 2. Создайте базу данных (если нужно)

Если база данных не создается автоматически:

```bash
# Подключитесь к PostgreSQL
docker exec -it glame_postgres psql -U glame_user -d postgres

# Создайте базу данных
CREATE DATABASE glame_db;

# Выйдите
\q
```

### 3. Выполните миграции

```bash
cd backend
alembic upgrade head
```

### 4. Проверьте созданные таблицы

```bash
docker exec -it glame_postgres psql -U glame_user -d glame_db -c "\dt"
```

Должны быть созданы следующие таблицы:
- `users`
- `products`
- `looks`
- `sessions`
- `analytics_events`
- `knowledge_documents`
- `content_plans`
- `content_items`
- `content_publications`
- `app_settings`

## Переменные окружения для работы с образами

Для полной функциональности работы с образами добавьте в `.env`:

```env
# OpenAI API (опционально, для embeddings и vision models)
OPENAI_API_KEY=your_openai_key

# Embedding model
EMBEDDING_MODEL=text-embedding-3-small

# Fashion Trends API (опционально, используется LLM fallback если не указан)
FASHION_TRENDS_API_KEY=
FASHION_TRENDS_API_URL=https://api.fashiontrends.com/v1

# Try-On API для визуальной примерки (опционально)
TRY_ON_API_KEY=
TRY_ON_API_URL=https://api.replicate.com/v1

# Хранилище изображений
STORAGE_TYPE=local
# Для S3:
# S3_BUCKET_NAME=your-bucket
# S3_ACCESS_KEY=your-access-key
# S3_SECRET_KEY=your-secret-key
```

**Важно:**
- Минимально необходим только `OPENROUTER_API_KEY` для базовой работы
- `FASHION_TRENDS_API_KEY` и `TRY_ON_API_KEY` опциональны - система будет использовать LLM fallback
- Для локальной разработки используйте `STORAGE_TYPE=local`

## Устранение проблем

### Ошибка подключения к PostgreSQL

```
✗ Ошибка подключения к PostgreSQL
```

**Решение:**
1. Проверьте, что PostgreSQL запущен: `docker ps`
2. Проверьте порт в `.env` (по умолчанию `5433`)
3. Проверьте учетные данные в `.env`

### Ошибка выполнения миграций

```
✗ Ошибка при выполнении миграций
```

**Решение:**
1. Убедитесь, что все зависимости установлены: `pip install -r requirements.txt`
2. Проверьте, что база данных создана
3. Проверьте логи: `alembic upgrade head --sql` для просмотра SQL

### Таблицы не созданы

**Решение:**
1. Проверьте логи миграций
2. Выполните миграции вручную: `alembic upgrade head`
3. Проверьте, что все модели импортированы в `app/models/__init__.py`

## Проверка работоспособности

После инициализации проверьте:

1. **Подключение к БД:**
   ```bash
   python backend/check_postgres.py
   ```

2. **API работает:**
   ```bash
   curl http://localhost:8000/health
   ```

3. **Таблицы созданы:**
   ```bash
   docker exec -it glame_postgres psql -U glame_user -d glame_db -c "\dt"
   ```

## Сброс базы данных

Если нужно начать заново:

```bash
# Остановите контейнеры
docker-compose -f infra/docker-compose.yml down

# Удалите volumes (ВНИМАНИЕ: удалит все данные!)
docker-compose -f infra/docker-compose.yml down -v

# Запустите заново
docker-compose -f infra/docker-compose.yml up -d postgres

# Выполните инициализацию
cd backend
python init_database.py
```
