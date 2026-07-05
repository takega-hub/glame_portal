# AI Стилист (Stylist Agent)

## Обзор

AI Стилист - это интеллектуальный агент платформы GLAME, специализирующийся на создании персонализированных образов и стилистических рекомендаций. Агент анализирует предпочтения пользователя, доступные товары из каталога и создает уникальные сочетания украшений и аксессуаров.

## Архитектура

### Базовый класс

AI Стилист наследуется от [`BaseAgent`](backend/app/agents/base_agent.py) и расширяет его функциональность для работы с образами и стилистическими рекомендациями.

### Основные компоненты

```
backend/app/agents/
├── stylist_agent.py          # Основной класс агента
└── ...

backend/app/api/
├── stylist.py                # API endpoints
└── looks.py                  # Управление образами

backend/app/services/
├── look_generation_service.py   # Генерация образов
├── recommendation_service.py    # Рекомендации товаров
└── image_generation_service.py  # Генерация изображений
```

## Функциональность

### 1. Генерация образов (Look Generation)

Агент создает полные образы на основе:
- **Профиля пользователя** - предпочтения, история покупок, стиль
- **Контекста** - повод, сезон, погода, dress code
- **Доступных товаров** - актуальный каталог из 1С

#### Параметры генерации

```python
{
    "occasion": "вечеринка",           # Повод
    "season": "осень",                  # Сезон
    "style_preference": "эклектика",    # Предпочтительный стиль
    "budget": "medium",                  # Бюджет: low/medium/high
    "color_scheme": "тёплые тона",      # Цветовая схема
    "exclude_categories": ["кольца"],   # Исключить категории
    "include_products": ["uuid1"],      # Включить конкретные товары
}
```

### 2. Интеграция с каталогом товаров

Агент работает с актуальным каталогом:
- Синхронизация с 1С через [`OneCProductsService`](backend/app/services/onec_products_service.py)
- Учет остатков на складах через [`ProductStock`](backend/app/models/product_stock.py)
- Фильтрация по доступности и активности

### 3. Генерация изображений образов

Для визуализации образов используется:
- [`ImageGenerationService`](backend/app/services/image_generation_service.py)
- Поддержка различных стилей фотографии
- Генерация с участием моделей или flat lay

### 4. Продажи и сопровождение в чате

Стилист работает как полноценный консультант-продавец в диалоге с покупателем:
- Отвечает на вопросы о бренде GLAME, коллекциях и украшениях
- Разбирает номенклатуру: артикулы, коды, конкретные позиции
- Проверяет наличие товара по магазинам (с учетом остатков и города)
- Консультирует по магазинам: адреса, города, варианты посещения
- Объясняет варианты покупки: онлайн, самовывоз, доставка
- Показывает в чате карточки товаров и образы
- Предлагает примерку (виртуальную и офлайн)
- Формирует комплекты и апсейл/кросс-сейл предложения
- Поддерживает действия с корзиной (добавление/обновление/удаление)

### 5. Структурированный payload для UI чата

Ответ ассистента в чате сохраняет не только `text`, но и структурированные данные в `payload`, чтобы клиентское приложение рендерило карточки и действия:

```json
{
  "persona": "fashion_girl",
  "cjm_stage": "consideration",
  "looks": [],
  "products": [],
  "stores_context": "список магазинов по городу",
  "store_stock_context": "наличие по магазинам",
  "purchase_options": "варианты покупки и доставки",
  "cta": "действие для пользователя"
}
```

### 6. Сохраненные образы в кабинете и контексте AI

- В кабинете покупателя отображается блок "Сохраненные образы" из endpoint `GET /api/customer/saved-looks`.
- AI-стилист учитывает последние сохраненные образы пользователя (название, стиль, настроение) как сигнал вкуса и опирается на них в подборе.
- Это повышает консистентность рекомендаций между разделом "Образы", кабинетом и чатом со стилистом.

## API Endpoints

### Стилистические рекомендации

```http
POST /api/stylist/recommendations
```

Создание персонализированных рекомендаций.

**Request Body:**
```json
{
  "context": "мне нужен образ на свадьбу друга",
  "preferences": ["минимализм", "золото"],
  "budget_range": {"min": 5000, "max": 15000},
  "product_count": 5
}
```

**Response:**
```json
{
  "recommendations": [
    {
      "product_id": "uuid",
      "name": "Колье Antura",
      "reason": "Подходит к вашему стилю минимализма",
      "match_score": 0.92,
      "suggested_combinations": ["uuid2", "uuid3"]
    }
  ],
  "style_analysis": "Ваш стиль - современный минимализм с элементами boho",
  "total_looks": 3
}
```

### Генерация образа

```http
POST /api/looks/generate
```

Создание нового образа с AI.

**Request Body:**
```json
{
  "name": "Образ на корпоратив",
  "description": "Элегантный образ для новогоднего корпоратива",
  "occasion": "корпоратив",
  "style_tags": ["элегантность", "вечер"],
  "budget": "high",
  "product_ids": [],
  "generate_image": true
}
```

**Response:**
```json
{
  "id": "look-uuid",
  "name": "Образ на корпоратив",
  "products": [
    {
      "id": "product-uuid",
      "name": "Серьги",
      "brand": "Antura",
      "price": 12500,
      "position": {"x": 100, "y": 200, "layer": 1}
    }
  ],
  "generated_image_url": "/static/look_images/look_xxx.png",
  "total_price": 45600,
  "style_summary": "Вечерняя элегантность в золотых тонах"
}
```

### Подбор по фото

```http
POST /api/stylist/analyze-photo
```

Анализ фотографии пользователя для стилистических рекомендаций.

**Request:**
- `image`: Файл изображения (multipart/form-data)
- `context`: Дополнительный контекст (optional)

**Response:**
```json
{
  "detected_features": {
    "color_temperature": "теплый",
    "style_direction": "классика",
    "preferred_metal": "золото"
  },
  "recommendations": [
    {
      "category": "колье",
      "products": [],
      "reasoning": "Подчеркнет линию шеи"
    }
  ],
  "style_profile": "romantic_classic"
}
```

### Чат покупателя со стилистом

```http
GET /api/customer/stylist-chat/messages
POST /api/customer/stylist-chat/messages
```

`POST` принимает:
- `text` (form field)
- `product_id` (optional)
- `photo` (optional image, multipart/form-data)

В ответ сохраняются сообщения `user` + `assistant`, а в `assistant.payload` возвращаются карточки товаров/образов и коммерческий контекст для UI.

#### Cart-команды в тексте чата

Поддерживаются текстовые команды покупателя (без отдельного endpoint):
- `покажи корзину` / `что в корзине`
- `добавь в корзину <артикул|код|название> [N шт]`
- `удали из корзины <артикул|код|название>`
- `очисти корзину`

Для этих команд backend выполняет действие с корзиной и возвращает быстрый ответ ассистента с `payload.cart` и `payload.products` (без вызова LLM), чтобы UI сразу показал актуальные карточки и сумму.

## Модели данных

### Look (Образ)

```python
class Look(Base):
    id: UUID                    # Уникальный идентификатор
    name: str                   # Название образа
    description: str            # Описание
    products: List[Product]     # Товары в образе
    positions: JSON             # Позиционирование на изображении
    generated_image_url: str    # URL сгенерированного изображения
    style_tags: List[str]      # Теги стиля
    occasion: str              # Повод
    is_public: bool            # Публичный ли образ
    created_by: UUID           # Автор
```

### SavedLook (Сохраненный образ)

```python
class SavedLook(Base):
    id: UUID
    user_id: UUID              # Пользователь
    look_id: UUID             # Ссылка на образ
    saved_at: datetime         # Дата сохранения
    notes: str                 # Заметки пользователя
    rating: int              # Оценка
```

## Интеграции

### 1. AI Content Agent

Стилист передает образы в Content Agent для:
- Создания контента на основе образов
- Генерации описаний для соцсетей
- Планирования публикаций с образами

### 2. AI Маркетолог

Маркетолог использует данные стилиста для:
- Анализа популярных сочетаний
- Планирования акций на комплекты
- Сегментации по стилевым предпочтениям

### 3. Каталог товаров

Прямая интеграция с:
- [`Product`](backend/app/models/product.py)
- [`ProductStock`](backend/app/models/product_stock.py)
- [`CatalogSection`](backend/app/models/catalog_section.py)

## Примеры использования

### Создание образа для клиента

```python
from app.agents.stylist_agent import StylistAgent

agent = StylistAgent(db)

# Генерация образа
look = await agent.generate_look(
    user_id=user.id,
    occasion="свидание",
    preferences=["романтика", "нежность"],
    budget="medium"
)

# Получение рекомендаций
recommendations = await agent.get_recommendations(
    user_id=user.id,
    context="нужно украшение на каждый день",
    count=5
)
```

### Виртуальный примерочный

```http
POST /api/look-tryon/virtual
Content-Type: application/json

{
  "look_id": "look-uuid",
  "user_photo_url": "/uploads/user_photo.jpg",
  "options": {
    "background": "studio_white",
    "lighting": "soft"
  }
}
```

## Конфигурация

### Переменные окружения

```bash
# Генерация изображений
IMAGE_GENERATION_ENABLED=true
IMAGE_GENERATION_MODEL=default

# Ограничения
MAX_LOOK_PRODUCTS=8
MAX_GENERATION_TIME=120

# Стили фотографии
DEFAULT_PHOTO_STYLE=editorial_fashion
```

## Ограничения и рекомендации

### Технические ограничения

- Максимум 8 товаров в одном образе
- Генерация изображения занимает до 2 минут
- Кэширование рекомендаций на 1 час

### Бизнес-правила

- Образы должны содержать только доступные товары
- Минимальная цена образа - 3000₽
- Рекомендуется минимум 2 категории украшений

## Мониторинг

### Метрики

- `stylist_looks_generated` - Количество созданных образов
- `stylist_recommendations_accuracy` - Точность рекомендаций
- `stylist_generation_time` - Время генерации
- `stylist_user_satisfaction` - Удовлетворенность пользователей

### Логирование

```python
logger.info(f"Generated look {look.id} for user {user.id}")
logger.info(f"Products in look: {len(look.products)}")
logger.info(f"Generation time: {generation_time}s")
```

## Разработка и расширение

### Добавление новых стилей

1. Обновить `STYLE_DEFINITIONS` в [`stylist_agent.py`](backend/app/agents/stylist_agent.py)
2. Добавить примеры в векторную базу знаний
3. Обновить тесты

### Расширение API

Пример добавления нового endpoint:

```python
@router.post("/stylist/style-quiz")
async def style_quiz(
    answers: StyleQuizAnswers,
    db: AsyncSession = Depends(get_db)
):
    agent = StylistAgent(db)
    style_profile = await agent.analyze_style_quiz(answers)
    return style_profile
```

## Troubleshooting

### Проблемы с генерацией образов

**Образ не генерируется**
- Проверить наличие товаров в каталоге
- Проверить подключение к сервису генерации изображений
- Проверить лимиты API

**Нерелевантные рекомендации**
- Обновить векторную базу знаний
- Проверить данные профиля пользователя
- Увеличить вес предпочтений

### Поддержка

При возникновении проблем:
1. Проверить логи в `backend/logs/stylist.log`
2. Проверить состояние таблиц `looks`, `saved_looks`
3. Убедиться в актуальности каталога товаров

## Дорожная карта

### Q1 2026
- [x] Базовая генерация образов
- [x] Интеграция с каталогом
- [x] Генерация изображений

### Q2 2026
- [ ] Улучшенный анализ стиля по фото
- [ ] Интеграция с AI Content Agent
- [ ] Персонализированные подборки

### Q3 2026
- [ ] 3D визуализация
- [ ] AR-примерка
- [ ] Социальные функции (делиться образами)

---

**Последнее обновление:** 2026-02-27  
**Версия документа:** 1.0  
**Ответственный:** AI Platform Team
