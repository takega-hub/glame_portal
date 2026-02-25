# GLAME AI Platform

AI-платформа для бренда GLAME с фокусом на AI Stylist Agent, генерацию контента, интеграцию с каталогом, веб-интерфейс с чатом и аналитику.

## Структура платформы

Платформа включает следующие модули:

- **AI Stylist** (`/`) - Диалоговый интерфейс с AI стилистом для подбора образов
- **Генератор контента** (`/content-generator`) - Генерация контента для маркетинга
- **Каталог товаров** (`/products`) - Просмотр и управление каталогом
- **Образы** (`/looks`) - Готовые образы и стилистические решения
- **Аналитика** (`/analytics`) - Панель аналитики взаимодействий

Подробнее: [PLATFORM_STRUCTURE.md](PLATFORM_STRUCTURE.md) | [PLATFORM_NAVIGATION.md](PLATFORM_NAVIGATION.md)

## Архитектура

- **Frontend**: Next.js (React, TypeScript)
- **Backend**: FastAPI (Python)
- **AI Layer**: OpenRouter API для доступа к LLM
- **Vector DB**: Qdrant для хранения знаний бренда
- **Database**: PostgreSQL для основных данных
- **Cache**: Redis

## Быстрый старт

### Требования

- Docker и Docker Compose
- Python 3.11+
- Node.js 18+

### Установка

1. Клонируйте репозиторий
2. Скопируйте `.env.example` в `.env` и заполните переменные окружения:
   ```bash
   cp .env.example .env
   ```
   Обязательно укажите:
   - `OPENROUTER_API_KEY` - ваш API ключ от OpenRouter
   - `JWT_SECRET_KEY` - секретный ключ для JWT токенов
   
   Опционально (для работы с образами):
   - `OPENAI_API_KEY` - для embeddings и vision models
   - `FASHION_TRENDS_API_KEY` - API ключ для модных трендов (используется LLM fallback если не указан)
   - `TRY_ON_API_KEY` - API ключ для визуальной примерки (используется fallback если не указан)
   - `STORAGE_TYPE` - тип хранилища (`local` или `s3`)

3. Запустите инфраструктуру (PostgreSQL, Qdrant, Redis):
   ```bash
   docker-compose -f infra/docker-compose.yml up -d
   ```

4. Установите зависимости backend:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

5. Инициализируйте базу данных:
   ```bash
   cd backend
   python init_database.py
   ```
   Или вручную:
   ```bash
   alembic upgrade head
   ```
   Подробнее: [INIT_DATABASE.md](INIT_DATABASE.md)

6. Заполните базу тестовыми данными (опционально):
   ```bash
   cd backend
   python run_seeds.py
   ```

7. Установите зависимости frontend:
   ```bash
   cd frontend
   npm install
   ```

8. Запустите backend (в отдельном терминале):
   ```bash
   cd backend
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

9. Запустите frontend (в отдельном терминале):
   ```bash
   cd frontend
   npm run dev
   ```

10. Откройте браузер: http://localhost:3000

## Навигация по платформе

После запуска frontend доступны следующие страницы:

- **AI Stylist** (`/`) - Чат с AI стилистом для подбора образов
- **Генератор контента** (`/content-generator`) - Генерация контента для маркетинга
- **Каталог товаров** (`/products`) - Просмотр каталога товаров
- **Образы** (`/looks`) - Готовые образы и стилистические решения
- **Аналитика** (`/analytics`) - Панель аналитики взаимодействий

Подробнее: [PLATFORM_NAVIGATION.md](PLATFORM_NAVIGATION.md)

## Структура проекта

```
glame-platform/
├── frontend/              # Next.js приложение
│   ├── src/
│   │   ├── app/          # Next.js App Router
│   │   ├── components/   # React компоненты
│   │   ├── lib/          # Утилиты и API клиенты
│   │   └── types/        # TypeScript типы
│   └── package.json
├── backend/               # FastAPI приложение
│   ├── app/
│   │   ├── api/          # API роуты
│   │   ├── agents/       # AI агенты
│   │   ├── services/     # Бизнес-логика
│   │   ├── models/       # SQLAlchemy модели
│   │   └── main.py       # Точка входа
│   └── requirements.txt
├── data/
│   └── migrations/       # Alembic миграции
├── infra/
│   └── docker-compose.yml # Docker конфигурация
└── README.md
```

## API Документация

После запуска backend доступна по адресу: http://localhost:8000/docs

### Основные endpoints:

- `POST /api/stylist/chat` - диалог с AI стилистом
- `GET /api/products` - список товаров
- `GET /api/looks` - список образов
- `POST /api/content/generate` - генерация контента
- `POST /api/analytics/track` - трекинг событий

## Основные функции

### AI Stylist Agent
- Определение персоны пользователя
- Определение этапа Customer Journey Map
- Подбор товаров и образов
- Генерация персонализированных рекомендаций

### AI Content Agent
- Генерация контента на основе персоны и CJM
- Адаптация под различные каналы

### Analytics
- Трекинг событий пользователей
- Метрики сессий
- Аналитика взаимодействий

## Переменные окружения

См. `.env.example` для полного списка переменных окружения.

## Документация

- [QUICK_START.md](QUICK_START.md) - Быстрый старт
- [PLATFORM_STRUCTURE.md](PLATFORM_STRUCTURE.md) - Структура платформы
- [PLATFORM_NAVIGATION.md](PLATFORM_NAVIGATION.md) - Навигация по платформе
- [CONTENT_AGENT_GUIDE.md](CONTENT_AGENT_GUIDE.md) - Руководство по Content Agent
- [CONTENT_AGENT_INTEGRATION.md](CONTENT_AGENT_INTEGRATION.md) - Интеграция Content Agent
- [CONTENT_AGENT_USAGE.md](CONTENT_AGENT_USAGE.md) - Использование Content Agent
- [1C_INTEGRATION.md](1C_INTEGRATION.md) - Интеграция с 1С
- [BRAND_KNOWLEDGE.md](BRAND_KNOWLEDGE.md) - База знаний о бренде
- [NEXT_STEPS.md](NEXT_STEPS.md) - План дальнейшей работы

## Разработка

См. план реализации в `.cursor/plans/` для детальной информации о спринтах и задачах.

## Лицензия

Proprietary - GLAME AI Platform
