# Импорт исторических данных о продажах

## Описание

Скрипты для импорта исторических данных о продажах из Excel файла `1c/sales25.xls` в базу данных.

## Подготовка

### 1. Установка зависимостей

```bash
pip install pandas openpyxl xlrd
```

Или обновите requirements.txt:
```bash
pip install -r requirements.txt
```

### 2. Расширение таблицы sales_records

Перед импортом необходимо расширить таблицу `sales_records` новыми полями:

```bash
cd backend
python extend_sales_record_table.py
```

Этот скрипт добавит следующие поля:
- `product_name` - название товара на момент продажи
- `product_article` - артикул товара
- `product_category` - категория товара
- `product_brand` - бренд товара
- `product_type` - тип изделия
- `cost_price` - себестоимость
- `margin` - маржа

## Формат данных Excel

Файл `1c/sales25.xls` должен содержать:
- Колонка с датой продажи (автоматически определяется)
- Колонка с товаром в формате: `"Название, единица, артикул"`

Примеры:
- `"Каффа Geometry, шт, 82039-G"`
- `"Кольцо золотое, шт, RING-123"`

## Импорт данных

### Запуск импорта

```bash
cd backend
python import_historical_sales_from_excel.py
```

Скрипт:
1. Читает файл `1c/sales25.xls`
2. Парсит строки товаров (название, единица, артикул)
3. Ищет товары в каталоге `products` по артикулу
4. Импортирует данные в таблицу `sales_records`

### Процесс импорта

1. **Парсинг товаров**: Скрипт извлекает артикул из строки товара
2. **Сопоставление с каталогом**: Поиск товара в таблице `products` по полям:
   - `article` (точное совпадение)
   - `external_code` (точное совпадение)
   - Частичное совпадение (если артикул содержит дефисы)
3. **Заполнение данных**: 
   - Если товар найден - заполняются `product_id`, `category`, `brand`
   - Если не найден - только `product_name` и `product_article`

### Статистика импорта

После завершения скрипт выводит:
- Всего строк в файле
- Импортировано записей
- Пропущено строк (некорректные данные)
- Товаров найдено в каталоге
- Товаров не найдено

## Структура данных

### Таблица sales_records

После расширения таблица содержит:

```sql
CREATE TABLE sales_records (
    id UUID PRIMARY KEY,
    sale_date TIMESTAMP WITH TIME ZONE NOT NULL,
    external_id VARCHAR(255) UNIQUE,
    document_id VARCHAR(255),
    store_id VARCHAR(255),
    customer_id VARCHAR(255),
    product_id VARCHAR(255),  -- ID товара из 1С
    organization_id VARCHAR(255),
    
    -- Метрики продажи
    revenue DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    quantity DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    revenue_without_discount DOUBLE PRECISION,
    
    -- Данные о товаре (новые поля)
    product_name VARCHAR(500),
    product_article VARCHAR(100),
    product_category VARCHAR(100),
    product_brand VARCHAR(100),
    product_type VARCHAR(100),
    cost_price DOUBLE PRECISION,
    margin DOUBLE PRECISION,
    
    -- Канал продажи
    channel VARCHAR(64) DEFAULT 'offline',
    
    -- Метаданные
    raw_data JSONB,
    sync_batch_id VARCHAR(255),
    synced_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE
);
```

## Особенности

### Обработка артикулов

Скрипт поддерживает различные форматы артикулов:
- `82039-G` - с дефисом
- `RING-123` - буквы-цифры
- `12345` - только цифры

### Сопоставление товаров

Приоритет поиска:
1. Точное совпадение `article = артикул`
2. Точное совпадение `external_code = артикул`
3. Частичное совпадение (если артикул содержит дефисы)

### Дедупликация

Скрипт использует `external_id` для предотвращения дубликатов:
- Формат: `historical_import_YYYYMMDD_HHMMSS_номер_строки`
- При конфликте запись не вставляется (ON CONFLICT DO NOTHING)

## Troubleshooting

### Ошибка "Файл не найден"

Убедитесь, что файл находится в правильной папке:
```
GLAME AI platform/
  └── 1c/
      └── sales25.xls
```

### Ошибка "Не удалось прочитать Excel файл"

Установите необходимые библиотеки:
```bash
pip install pandas openpyxl xlrd
```

### Много товаров не найдено в каталоге

1. Проверьте формат артикулов в Excel
2. Убедитесь, что товары в каталоге имеют правильные артикулы
3. Проверьте логи скрипта - возможно, артикулы парсятся неправильно

### Ошибка подключения к БД

Проверьте переменные окружения в `.env`:
- `DB_HOST`
- `DB_PORT`
- `DB_USER`
- `DB_PASSWORD`
- `DB_NAME`

## Следующие шаги

После импорта исторических данных:

1. **Проверка данных**:
   ```sql
   SELECT COUNT(*) FROM sales_records WHERE sync_batch_id LIKE 'historical_import%';
   ```

2. **Анализ сопоставления**:
   ```sql
   SELECT 
       COUNT(*) as total,
       COUNT(product_id) as matched,
       COUNT(*) - COUNT(product_id) as unmatched
   FROM sales_records 
   WHERE sync_batch_id LIKE 'historical_import%';
   ```

3. **Использование в аналитике**:
   - Данные доступны для анализа через API `/api/analytics/1c-sales/*`
   - Можно использовать для расчёта оборачиваемости
   - Приоритизация товаров для сайта
   - Рекомендации по закупкам

## Примечания

- Для исторических данных `revenue` устанавливается в 0.0 (если в Excel нет данных о сумме)
- `quantity` устанавливается в 1.0 по умолчанию
- `channel` устанавливается в 'offline' для исторических данных
- Все данные сохраняются в `raw_data` для возможности восстановления
