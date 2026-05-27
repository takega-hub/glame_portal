# Быстрый старт: Инициализация БД

## Шаг 1: Запустите PostgreSQL

```bash
docker-compose -f infra/docker-compose.yml up -d postgres
```

Подождите 10-15 секунд пока PostgreSQL запустится.

## Шаг 2: Настройте переменные окружения

Скопируйте `ENV.example` в `.env`:

```bash
cp ENV.example .env
```

Откройте `.env` и укажите минимум:
```env
OPENROUTER_API_KEY=your_key_here
```

## Шаг 3: Инициализируйте базу данных

### Windows:
```powershell
cd backend
.\init_database.ps1
```

### Linux/Mac:
```bash
cd backend
python init_database.py
```

## Готово! ✓

База данных создана и готова к работе.

## Что дальше?

1. **Запустите backend:**
   ```bash
   cd backend
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

2. **Запустите frontend:**
   ```bash
   cd frontend
   npm run dev
   ```

3. **Откройте в браузере:**
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

## Проблемы?

См. [INIT_DATABASE.md](INIT_DATABASE.md) для подробной инструкции и решения проблем.
