# Структура таблиц товаров в базе данных

## 1. Таблица `products` (Товары)

**Основная таблица товаров**

### Колонки:

| Колонка | Тип | Nullable | Описание |
|---------|-----|----------|----------|
| `id` | UUID | NOT NULL | Первичный ключ (автогенерация) |
| `name` | VARCHAR(255) | NOT NULL | Название товара |
| `brand` | VARCHAR(100) | NULL | Бренд |
| `price` | INTEGER | NOT NULL | Цена в копейках |
| `category` | VARCHAR(100) | NULL | Категория (название раздела каталога) |
| `images` | JSONB | NULL | Массив URL изображений |
| `tags` | JSONB | NULL | Массив тегов |
| `description` | TEXT | NULL | Описание товара |
| `article` | VARCHAR(100) | NULL | Артикул товара |
| `vendor_code` | VARCHAR(100) | NULL | Код производителя |
| `barcode` | VARCHAR(100) | NULL | Штрихкод |
| `unit` | VARCHAR(50) | NULL | Единица измерения |
| `weight` | FLOAT | NULL | Вес |
| `volume` | FLOAT | NULL | Объем |
| `country` | VARCHAR(100) | NULL | Страна производства |
| `warranty` | VARCHAR(100) | NULL | Гарантия |
| `full_description` | TEXT | NULL | Полное описание |
| `specifications` | JSONB | NULL | Технические характеристики (включая `parent_external_id` для вариантов) |
| `onec_data` | JSONB | NULL | Полные данные из 1С |
| `external_id` | VARCHAR(255) | NULL | ID товара в 1С (уникальный) |
| `external_code` | VARCHAR(100) | NULL | Код товара в 1С |
| `is_active` | BOOLEAN | NOT NULL | Активен ли товар (по умолчанию true) |
| `sync_status` | VARCHAR(50) | NULL | Статус синхронизации (synced, pending, error) |
| `sync_metadata` | JSONB | NULL | Метаданные синхронизации (дата, источник, `parent_external_id` для вариантов) |
| `created_at` | TIMESTAMP WITH TIME ZONE | NULL | Дата создания (автоматически) |
| `updated_at` | TIMESTAMP WITH TIME ZONE | NULL | Дата обновления (автоматически) |

### Индексы:

- `products_pkey` - первичный ключ на `id`
- `ix_products_external_id` - индекс на `external_id` (для быстрого поиска по ID из 1С)
- `ix_products_external_code` - индекс на `external_code`
- `ix_products_is_active` - индекс на `is_active`
- `ix_products_article` - индекс на `article` (для поиска по артикулу)

### Особенности:

- **Варианты товаров**: Варианты связываются с основным товаром через `parent_external_id` в поле `specifications` или `sync_metadata`
- **Изображения**: Хранятся как JSON массив URL
- **Характеристики**: Хранятся в JSON формате в поле `specifications`

---

## 2. Таблица `product_stocks` (Остатки товаров)

**Остатки товаров по складам**

### Колонки:

| Колонка | Тип | Nullable | Описание |
|---------|-----|----------|----------|
| `id` | UUID | NOT NULL | Первичный ключ |
| `product_id` | UUID | NOT NULL | Ссылка на товар (FK -> products.id) |
| `store_id` | VARCHAR(255) | NOT NULL | ID склада из 1С |
| `quantity` | FLOAT | NOT NULL | Общее количество на складе |
| `reserved_quantity` | FLOAT | NOT NULL | Зарезервированное количество |
| `available_quantity` | FLOAT | NOT NULL | Доступное количество (quantity - reserved_quantity) |
| `last_synced_at` | TIMESTAMP WITH TIME ZONE | NULL | Дата последней синхронизации (автоматически) |

### Индексы:

- `product_stocks_pkey` - первичный ключ на `id`
- `ix_product_stocks_product_id` - индекс на `product_id`
- `ix_product_stocks_store_id` - индекс на `store_id`
- `ix_product_stocks_product_store` - уникальный индекс на пару `(product_id, store_id)` (один товар - один остаток на склад)

### Внешние ключи:

- `product_id` -> `products.id` (ON DELETE CASCADE)

### Особенности:

- Один товар может иметь остатки на нескольких складах
- Уникальная комбинация `(product_id, store_id)` - один остаток на товар на склад
- Работает как для основных товаров, так и для вариантов

---

## 3. Таблица `catalog_sections` (Разделы каталога)

**Разделы каталога (группы) из 1С**

### Колонки:

| Колонка | Тип | Nullable | Описание |
|---------|-----|----------|----------|
| `id` | UUID | NOT NULL | Первичный ключ (автогенерация) |
| `external_id` | VARCHAR(255) | NOT NULL | ID раздела в 1С (уникальный) |
| `external_code` | VARCHAR(100) | NULL | Код раздела в 1С |
| `name` | VARCHAR(255) | NOT NULL | Название раздела (например, "SALE", "AGAFI") |
| `parent_external_id` | VARCHAR(255) | NULL | ID родительского раздела (для иерархии) |
| `description` | TEXT | NULL | Описание раздела |
| `onec_metadata` | JSONB | NULL | Полные данные из 1С |
| `is_active` | BOOLEAN | NOT NULL | Активен ли раздел (по умолчанию true) |
| `sync_status` | VARCHAR(50) | NULL | Статус синхронизации |
| `sync_metadata` | JSONB | NULL | Метаданные синхронизации |
| `created_at` | TIMESTAMP WITH TIME ZONE | NULL | Дата создания (автоматически) |
| `updated_at` | TIMESTAMP WITH TIME ZONE | NULL | Дата обновления (автоматически) |

### Индексы:

- `catalog_sections_pkey` - первичный ключ на `id`
- `catalog_sections_external_id_key` - уникальный индекс на `external_id`
- `ix_catalog_sections_external_id` - индекс на `external_id`
- `ix_catalog_sections_external_code` - индекс на `external_code`
- `ix_catalog_sections_parent_external_id` - индекс на `parent_external_id` (для иерархии)
- `ix_catalog_sections_is_active` - индекс на `is_active`

### Особенности:

- Разделы импортируются из `<Группы>` в `import.xml`
- Товары связываются с разделами через поле `category` (название раздела)
- Поддерживается иерархия разделов через `parent_external_id`

---

## Связи между таблицами:

```
products
  ├── product_stocks (product_id -> products.id)
  └── category -> catalog_sections.name

catalog_sections
  └── parent_external_id -> catalog_sections.external_id (иерархия)
```

---

## Статистика (на момент проверки):

- **products**: 387 записей
- **product_stocks**: 1548 записей
- **catalog_sections**: 21 запись

---

## Важные моменты:

1. **Варианты товаров**: 
   - Связываются через `parent_external_id` в `specifications` или `sync_metadata`
   - Имеют свой `external_id` в формате `product_id#characteristic_id`
   - Имеют свой артикул (например, `71136-G`, `71136-S`)

2. **Остатки**:
   - Хранятся отдельно для каждого товара и склада
   - Работают для основных товаров и вариантов

3. **Разделы каталога**:
   - Импортируются из XML перед товарами
   - Товары привязываются к разделам по названию
