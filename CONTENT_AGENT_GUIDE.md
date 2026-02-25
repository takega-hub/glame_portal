# Как запустить Content Agent

## Content Agent - это AI агент для генерации контента для бренда GLAME

## Шаг 1: Запуск Backend

Убедитесь, что backend сервер запущен:

```bash
cd backend
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Или используйте скрипт:
```bash
cd backend
.\start_backend.bat
```

Backend будет доступен на: **http://localhost:8000**

## Шаг 2: Использование Content Agent

Content Agent доступен через API endpoint: **POST `/api/content/generate`**

### Способ 1: Через Swagger UI (рекомендуется)

1. Откройте в браузере: http://localhost:8000/docs
2. Найдите endpoint `/api/content/generate`
3. Нажмите "Try it out"
4. Заполните параметры:
   ```json
   {
     "persona": "Молодая женщина 25-35 лет, любит стильные украшения",
     "cjm_stage": "awareness",
     "channel": "website_main",
     "goal": "Вдохновить на покупку"
   }
   ```
5. Нажмите "Execute"

### Способ 2: Через curl (PowerShell)

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/content/generate" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{
    "persona": "Молодая женщина 25-35 лет",
    "cjm_stage": "awareness",
    "channel": "website_main",
    "goal": "Вдохновить на покупку"
  }'
```

### Способ 3: Через Python скрипт

Создайте файл `test_content_agent.py`:

```python
import requests
import json

url = "http://localhost:8000/api/content/generate"

data = {
    "persona": "Молодая женщина 25-35 лет, любит стильные украшения",
    "cjm_stage": "awareness",  # awareness, consideration, purchase, retention
    "channel": "website_main",  # website_main, instagram, email, etc.
    "goal": "Вдохновить на покупку"
}

response = requests.post(url, json=data)
print(json.dumps(response.json(), ensure_ascii=False, indent=2))
```

Запуск:
```bash
python test_content_agent.py
```

## Параметры запроса

| Параметр | Тип | Обязательный | Описание |
|----------|-----|--------------|----------|
| `persona` | string | Нет | Описание целевой персоны пользователя |
| `cjm_stage` | string | Нет | Этап Customer Journey Map (awareness, consideration, purchase, retention) |
| `channel` | string | Нет | Канал коммуникации (по умолчанию: "website_main") |
| `goal` | string | Нет | Цель контента (например, "вдохновить", "мотивировать к покупке") |

## Примеры использования

### Пример 1: Контент для главной страницы

```json
{
  "persona": "Женщина 30-40 лет, ценит качество и уникальность",
  "cjm_stage": "awareness",
  "channel": "website_main",
  "goal": "Познакомить с брендом GLAME"
}
```

### Пример 2: Контент для Instagram

```json
{
  "persona": "Молодая женщина 20-30 лет, активна в соцсетях",
  "cjm_stage": "consideration",
  "channel": "instagram",
  "goal": "Мотивировать к покупке"
}
```

### Пример 3: Email рассылка

```json
{
  "persona": "Постоянный клиент, покупает регулярно",
  "cjm_stage": "retention",
  "channel": "email",
  "goal": "Предложить новые коллекции"
}
```

## Ответ API

Успешный ответ:

```json
{
  "content": "Сгенерированный контент...",
  "persona": "Молодая женщина 25-35 лет",
  "cjm_stage": "awareness"
}
```

## Как работает Content Agent

1. **Получает контекст бренда** из векторной базы данных Qdrant
2. **Формирует промпт** на основе:
   - Персоны пользователя
   - Этапа Customer Journey Map
   - Канала коммуникации
   - Цели контента
3. **Генерирует контент** через LLM (OpenRouter)
4. **Возвращает результат** с учетом философии бренда GLAME

## Требования

- ✅ Backend должен быть запущен
- ✅ Docker контейнеры должны быть запущены (PostgreSQL, Qdrant, Redis)
- ✅ Переменные окружения настроены (OPENROUTER_API_KEY и др.)

## Проверка статуса

Проверьте, что все сервисы работают:

```bash
# Проверка backend
Invoke-RestMethod -Uri "http://localhost:8000/health"

# Проверка Docker контейнеров
cd infra
docker-compose ps
```

## Troubleshooting

### Ошибка: "Connection refused"
- Убедитесь, что backend запущен на порту 8000
- Проверьте: `netstat -an | findstr 8000`

### Ошибка: "Error generating content"
- Проверьте логи backend в терминале
- Убедитесь, что OPENROUTER_API_KEY настроен в `.env`
- Проверьте, что Qdrant доступен

### Контент не соответствует бренду
- Убедитесь, что база знаний о бренде загружена в Qdrant
- См. инструкцию: [BRAND_KNOWLEDGE.md](BRAND_KNOWLEDGE.md)
