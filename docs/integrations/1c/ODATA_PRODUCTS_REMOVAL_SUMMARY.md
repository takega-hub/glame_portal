# Удаление OData API для товаров - Сводка изменений

Дата: 2026-02-04

## Обзор

Согласно требованиям пользователя, вся функциональность синхронизации товаров через **OData API** была полностью удалена из проекта. Теперь товары синхронизируются **только через CommerceML XML**.

**OData API сохранен только для:**
- Покупателей (дисконтные карты)
- Продаж (розничные продажи)
- Остатков по складам (для аналитики)

## Удаленные компоненты

### Backend

#### 1. API Endpoints (`backend/app/api/products.py`)

**Удалено:**
- `POST /api/products/sync-1c` - endpoint для синхронизации через OData API
- `async def _run_sync_task()` - фоновая задача для OData синхронизации

**Обновлено:**
- `GET /api/products/sync-1c/status` - теперь работает только с XML задачами (`products_xml`)

#### 2. Service Methods (`backend/app/services/onec_products_service.py`)

**Удалено:**
- `fetch_nomenclature_page()` - загрузка страницы товаров из OData
- `fetch_nomenclature()` - загрузка всех товаров из OData
- `fetch_collection_page()` - загрузка страницы коллекции OData
- `fetch_collection()` - загрузка всей коллекции OData
- `fetch_barcodes_map()` - загрузка штрихкодов из регистров OData
- `fetch_prices_map()` - загрузка розничных цен из регистров OData
- `fetch_characteristics_catalog_map()` - загрузка артикулов характеристик из OData
- `fetch_product_characteristics()` - загрузка характеристик товара из OData
- `_resolve_characteristic_article()` - резолвинг артикулов характеристик
- `_resolve_price_from_map()` - резолвинг цен из карты
- `map_1c_to_product()` - маппинг OData данных в модель Product
- `sync_catalog()` - синхронизация каталога через OData
- `sync_catalog_sections()` - синхронизация разделов каталога через OData

**Обновлено:**
- `__init__()` - теперь принимает только `db: AsyncSession`
- Комментарии и docstrings обновлены для отражения использования только XML

**Сохранено:**
- `import_groups_from_xml()` - импорт групп каталога из XML
- `import_products_from_xml()` - основной метод для импорта товаров из XML
- Вспомогательные методы: `_get_first()`, `_as_string()`, `_normalize_price()`, `_is_empty_guid()`, `_extract_images()`
- Методы загрузки изображений: `_load_product_images()`, `_load_product_images_direct()`

#### 3. Test Scripts

**Удалено:**
- `backend/test_1c_products_sync.py` - устаревший тест скрипт для OData синхронизации

**Сохранено (для отладки):**
- `backend/test_1c_nomenclature_fields.py` - анализ полей (может быть обновлен для работы напрямую с OData)
- Другие тест скрипты для поиска штрихкодов, цен, изображений

### Frontend

#### 1. UI Components (`frontend/src/components/products/OneCSyncUpload.tsx`)

**Удалено:**
- Вкладка "OData API (основной)" и вся связанная UI логика
- Метод синхронизации `'odata'`
- Кнопка "Синхронизировать загруженные"
- Все обработчики и состояния для OData синхронизации

**Обновлено:**
- XML синхронизация установлена как основной метод по умолчанию
- Упрощен UI - осталась только одна форма для ввода XML URL

#### 2. Product List Page (`frontend/src/app/products/page.tsx`)

**Удалено:**
- Кнопка "Синхронизировать с 1С" (которая открывала модальное окно с OData синхронизацией)
- Модальное окно синхронизации с OData API
- Функция `startOneCSync()` для запуска OData синхронизации
- State переменные: `syncModalOpen`, `syncing`, `syncStocks`, `syncError`, `syncResult`

**Сохранено:**
- Компонент `OneCSyncUpload` для XML синхронизации
- Кнопки экспорта в CSV/XLSX
- Кнопка "Удалить тестовые товары"

#### 3. API Client (`frontend/src/lib/api.ts`)

**Удалено:**
- `syncProductsFrom1C()` - функция для вызова OData синхронизации

**Сохранено:**
- `syncProductsFromXML()` - функция для вызова XML синхронизации
- `getSyncProgress()` - используется для отслеживания прогресса XML синхронизации

### API Endpoints

#### `backend/app/api/onec_sync.py`

**Удалено:**
- `POST /api/1c/sync/api/background` - endpoint для фоновой синхронизации через REST API
- `class SyncFromAPIRequest` - Pydantic модель для OData API синхронизации

**Сохранено:**
- `POST /api/1c/sync/file` - для загрузки из файла (JSON/XML)
- `POST /api/1c/sync/tilda` - для загрузки из Tilda CommerceML
- `POST /api/1c/sync/yml` - для загрузки из YML файла

**Примечание:**
Префикс роутера остается `/api/1c`, хотя теперь он используется только для покупателей и продаж через OData. Товары загружаются через `/api/products/sync-xml`.

### Main Application

#### `backend/app/main.py`

**Сохранено:**
- Импорт и вызовы `stock_sync_scheduler` - это для синхронизации **остатков товаров** (inventory levels), не каталога
- Все schedulers для покупателей и продаж

**Примечание:**
`stock_sync_scheduler.py` - это синхронизация **остатков по складам** (`AccumulationRegister_ТоварыНаСкладах`), необходима для аналитики. Не путать с синхронизацией каталога товаров.

## Сохраненные OData функции

### 1. Покупатели (Customers)

**Service**: `backend/app/services/onec_customers_service.py`  
**Endpoints**: `/api/admin/1c/*`

- Синхронизация дисконтных карт
- Синхронизация истории покупок
- Синхронизация баллов лояльности

### 2. Продажи (Sales)

**Service**: `backend/app/services/onec_sales_service.py`  
**Endpoints**: `/api/analytics/1c-sales/*`

- Загрузка продаж по периодам
- Метрики продаж
- Продажи по дням, магазинам, каналам

### 3. Остатки (Stock Levels)

**Service**: `backend/app/services/onec_stock_service.py`  
**Scheduler**: `backend/app/services/stock_sync_scheduler.py`

- Ночная синхронизация остатков по складам
- Используется для аналитики, не для каталога товаров

## Новый рабочий процесс

### Синхронизация товаров

1. Настройте выгрузку XML из 1С УНФ FRESH в формате CommerceML
2. Разместите файл `import.xml` по доступному URL (например, FTP, HTTP сервер)
3. В UI платформы:
   - Перейдите в раздел "Каталог товаров"
   - Нажмите кнопку синхронизации
   - Введите URL XML файла (например: `https://your-server.com/1c_exchange/uploaded/import.xml`)
   - Нажмите "Синхронизировать"
4. Отслеживайте прогресс в реальном времени:
   - **5%** - Импорт групп каталога
   - **10-100%** - Импорт товаров
5. После завершения проверьте результаты:
   - Группы каталога загружены в таблицу `catalog_sections`
   - Товары загружены с привязкой к группам

### Синхронизация продаж и покупателей

Работает автоматически по расписанию через OData API:

- Покупатели: каждые 4 часа + ночная синхронизация в 03:00
- Остатки: ежедневно в 02:00
- Продажи: по требованию (автоматически при запросе данных)

## Преимущества нового подхода

1. **Стандартизация**: CommerceML - стандартный формат 1С для e-commerce
2. **Надежность**: XML файлы можно проверить и валидировать перед загрузкой
3. **Гибкость**: Файлы можно редактировать вручную при необходимости
4. **Разделение ответственности**: Четкое разделение между каталогом (XML) и аналитикой (OData)
5. **Упрощение кода**: Удалена сложная логика OData для каталога

## Миграция

Если у вас уже были товары, синхронизированные через OData:

1. Товары в БД остаются без изменений
2. При первой XML синхронизации товары обновятся по `external_id`
3. Рекомендуется сделать резервную копию БД перед первой XML синхронизацией

## Дополнительные ресурсы

- [1C_INTEGRATION.md](1C_INTEGRATION.md) - Обновленная документация по интеграции
- [CHARACTERISTICS_LOADING_GUIDE.md](CHARACTERISTICS_LOADING_GUIDE.md) - Загрузка характеристик
- [PRODUCT_GROUPS_FILTERING.md](PRODUCT_GROUPS_FILTERING.md) - Фильтрация по группам
