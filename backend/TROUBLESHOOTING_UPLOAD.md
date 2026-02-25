# Решение проблемы с загрузкой файлов

## Проблема
Файл не загружается - процесс зависает на "Загрузка..." или "Загрузка истории...".

## Возможные причины и решения

### 1. Бэкенд не запущен или не отвечает

**Проверка:**
```bash
# Проверьте, запущен ли бэкенд
netstat -ano | findstr :8000

# Или откройте в браузере
http://localhost:8000/health
```

**Решение:**
```bash
cd backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 2. Обработка PDF занимает много времени

PDF файлы обрабатываются через AI, что может занять несколько минут для больших файлов.

**Что было сделано:**
- Увеличен таймаут до 5 минут на фронтенде
- Увеличен таймаут до 10 минут на бэкенде
- Добавлено логирование для отслеживания прогресса

**Проверка логов:**
Смотрите логи в консоли бэкенда. Должны быть сообщения:
- "Starting file upload: ..."
- "Reading file content..."
- "Starting PDF processing..."
- "PDF processing completed..."
- "Uploading X knowledge items to vector database..."

### 3. Ошибка при обработке PDF

**Проверка:**
1. Откройте консоль браузера (F12) и проверьте ошибки
2. Проверьте логи бэкенда
3. Проверьте, что файл не поврежден

**Возможные проблемы:**
- Файл слишком большой (>50MB)
- Файл защищен паролем
- Файл содержит только изображения без текста
- Проблемы с API ключом OpenRouter

### 4. Проблемы с подключением к базе данных

**Проверка:**
```bash
# Проверьте, что PostgreSQL запущен
docker ps | grep postgres

# Или если не в Docker
netstat -ano | findstr :5432
```

**Решение:**
```bash
# Запустите PostgreSQL через Docker
cd infra
docker-compose up -d postgres
```

### 5. Проблемы с Qdrant (векторная база)

**Проверка:**
```bash
# Проверьте, что Qdrant запущен
docker ps | grep qdrant

# Проверьте доступность
curl http://localhost:6333/health
```

**Решение:**
```bash
# Запустите Qdrant через Docker
cd infra
docker-compose up -d qdrant
```

### 6. Проверка переменных окружения

Убедитесь, что в `.env` файле заданы:
- `OPENROUTER_API_KEY` - для обработки PDF через AI
- `QDRANT_URL` - адрес Qdrant
- `DATABASE_URL` или `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`

## Диагностика

### Шаг 1: Проверьте доступность сервисов
```bash
python backend/test_upload_endpoint.py
```

### Шаг 2: Проверьте логи бэкенда
При загрузке файла в логах должны быть:
```
INFO: Starting file upload: O GLAME_2025.pdf
INFO: Created document record with ID: ...
INFO: Reading file content...
INFO: File read: O GLAME_2025.pdf, size: 221824 bytes
INFO: File type detected: PDF
INFO: Starting PDF processing...
```

### Шаг 3: Проверьте консоль браузера
Откройте DevTools (F12) → Console и Network tabs:
- Проверьте ошибки в Console
- Проверьте статус запроса в Network (должен быть 200 или 500 с деталями ошибки)

### Шаг 4: Проверьте статус документа в БД
```bash
python backend/verify_table.py
```

Или через SQL:
```sql
SELECT id, filename, status, error_message, created_at 
FROM knowledge_documents 
ORDER BY created_at DESC 
LIMIT 5;
```

## Быстрое решение

1. **Убедитесь, что все сервисы запущены:**
   ```bash
   cd infra
   docker-compose up -d
   ```

2. **Запустите бэкенд:**
   ```bash
   cd backend
   python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

3. **Попробуйте загрузить файл снова**

4. **Если проблема сохраняется:**
   - Проверьте логи бэкенда
   - Проверьте консоль браузера
   - Попробуйте загрузить небольшой JSON файл для проверки

## Дополнительная информация

- Логи бэкенда выводятся в консоль, где запущен uvicorn
- Ошибки также сохраняются в записи `knowledge_documents` в поле `error_message`
- Для больших PDF файлов (>10MB) обработка может занять 5-10 минут
