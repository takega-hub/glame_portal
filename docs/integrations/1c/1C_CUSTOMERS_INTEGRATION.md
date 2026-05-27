# Интеграция покупателей и истории покупок из 1С УНФ ФРЕШ

## Обзор

Данный документ описывает интеграцию данных о покупателях, дисконтных картах и истории покупок из 1С УНФ ФРЕШ для создания профилей покупателей и персонализации.

Исправления в коде:

onec_customers_service.py - обновлён метод get_customer_purchases для использования AccumulationRegister_Продажи
onec_customers_service.py - добавлена обработка ошибки AUTOORDER с уменьшением batch_size
onec_customers_service.py - исправлен бесконечный цикл при ошибке AUTOORDER
customer_sync_service.py - обновлён метод sync_purchase_history для использования AccumulationRegister_Продажи
admin/customers.py - удалена автоматическая синхронизация при заходе в кабинет покупателя
Обновлена документация:

1C_CUSTOMERS_INTEGRATION.md - добавлены разделы о проблемах и решениях, скриптах для работы с данными
Созданные скрипты:

backend/get_1c_sales_parsing.py - самый точный парсинг покупок из 1С
backend/sync_customer_correct.py - синхронизация покупок по контрагенту
backend/restore_initial_balance.py - восстановление "Ввода начальных остатков"
backend/check_amounts.py - проверка сумм между 1С и БД
Для синхронизации данных:

cd /root/glame-platform/backend && python3 get_1c_sales_parsing.py

## Ключевые сущности

### 1. Дисконтные карты (Catalog_ДисконтныеКарты)

**Назначение:** Синхронизация зарегистрированных покупателей

**Важные поля:**
- `КодКартыШтрихкод` - **номер телефона = логин для входа на сайт**
- `Code` - внутренний код карты
- `ВладелецКарты_Key` - связь с контрагентом (покупателем)
- `Ref_Key` - уникальный идентификатор карты
- `Description` - описание (обычно содержит номер телефона)

**Использование:**
```python
# Получение всех дисконтных карт
GET /odata/standard.odata/Catalog_ДисконтныеКарты?$top=100

# Фильтрация по номеру телефона
GET /odata/standard.odata/Catalog_ДисконтныеКарты?$filter=КодКартыШтрихкод eq '79787450654'
```

**Маппинг для синхронизации:**
- `КодКартыШтрихкод` → `phone` (логин пользователя)
- `ВладелецКарты_Key` → `customer_id` (ID покупателя в 1С)
- `Ref_Key` → `discount_card_id` (ID дисконтной карты)

### 2. История покупок (AccumulationRegister_Продажи)

**Назначение:** Получение истории покупок для создания образа покупателя

**Важные поля:**
- `Period` - дата покупки
- `Сумма` - сумма покупки
- `Количество` - количество товара
- `Номенклатура_Key` - ID товара
- `Контрагент_Key` - ID покупателя
- `Документ` - ID документа продажи
- `Организация_Key` - ID организации
- `Склад_Key` - ID склада/магазина

**Важно:** Использовать регистр `AccumulationRegister_Продажи` (без `_RecordType`), так как 1С Fresh возвращает ошибку 500 при запросах к регистрам с `_RecordType` суффиксом.

**Использование:**
```python
# Получение истории покупок конкретного покупателя
# ВАЖНО: Не использовать $orderby, так как 1С Fresh возвращает ошибку 500
GET /odata/standard.odata/AccumulationRegister_Продажи?$filter=Контрагент_Key eq guid'c6c1ea96-bb11-11f0-836e-fa163e4cc04e'&$top=100

# Пагинация для получения всех записей
GET /odata/standard.odata/AccumulationRegister_Продажи?$filter=Контрагент_Key eq guid'...'&$top=100&$skip=0
GET /odata/standard.odata/AccumulationRegister_Продажи?$filter=Контрагент_Key eq guid'...'&$top=100&$skip=100
```

**Парсинг данных:**
Данные хранятся в поле `RecordSet` - массиве движений. Нужно парсить каждый элемент массива:

```python
# Пример парсинга
for record in records:
    record_set = record.get("RecordSet", [])
    if not isinstance(record_set, list):
        continue

    for movement in record_set:
        kontragent_key = movement.get("Контрагент_Key", "")
        if kontragent_key == customer_id:
            # Обработка покупки
            period = movement.get("Period", "")
            amount = movement.get("Сумма", 0)
            quantity = movement.get("Количество", 0)
```

**Фильтрация дубликатов:**
- "Ночные" отчеты (время 20:00-05:00 UTC) с типом "ОтчетОРозничныхПродажах" и без склада
- Дубликаты с одинаковым `document_id_1c + product_id_1c + date`

**Для создания образа покупателя:**
- Анализ предпочтений по товарам (Номенклатура_Key)
- Частота покупок (анализ Period)
- Средний чек (Сумма / количество покупок)
- Сезонность (группировка по месяцам)
- Любимые категории (через связь с Catalog_Номенклатура)

### 3. Документы продаж (DocumentJournal_РозничныеПродажи)

**Назначение:** Информация о чеках и документах продаж

**Важные поля:**
- `Ref` - ID документа
- `Date` - дата чека
- `Number` - номер документа
- `Сумма` - сумма чека
- `НомерЧека` - номер чека ККМ
- `Покупатель_Key` - ID покупателя
- `КассаККМ_Key` - ID кассы
- `Организация_Key` - ID организации

**Использование:**
```python
# Чеки конкретного покупателя
GET /odata/standard.odata/DocumentJournal_РозничныеПродажи?$filter=Покупатель_Key eq guid'...'
```

### 4. Контрагенты (Catalog_Контрагенты)

**Назначение:** Полная информация о покупателях

**Важные поля:**
- `Ref_Key` - ID контрагента
- `Code` - код контрагента
- `Description` - наименование
- Дополнительные поля контактов (если доступны)

**Связь:**
- Дисконтные карты → `ВладелецКарты_Key` → `Catalog_Контрагенты.Ref_Key`

### 5. Номенклатура (Catalog_Номенклатура)

**Назначение:** Каталог товаров для анализа предпочтений

**Использование:**
- Связь с покупками через `Номенклатура_Key`
- Анализ категорий товаров
- Определение предпочтений по брендам

## Структура данных для образа покупателя

### Базовые данные
```json
{
  "phone": "79787450654",  // из Catalog_ДисконтныеКарты.КодКартыШтрихкод
  "discount_card_id": "c25d2f16-bb1a-11f0-836e-fa163e4cc04e",
  "customer_id": "747c54ec-bb11-11f0-836e-fa163e4cc04e",  // ВладелецКарты_Key
  "name": "Имя покупателя"  // из Catalog_Контрагенты (если доступно)
}
```

### История покупок
```json
{
  "purchases": [
    {
      "date": "2025-11-10T10:24:27",
      "amount": 8090.00,
      "quantity": 1,
      "product_id": "aea37de4-ba6c-11f0-836e-fa163e4cc04e",
      "document_id": "4ac25816-be06-11f0-9138-fa163e4cc04e",
      "store_id": "3daee4e4-a2ab-11f0-96fc-fa163e4cc04e"
    }
  ],
  "statistics": {
    "total_revenue": 21267.00,
    "total_purchases": 5,
    "average_check": 4253.40,
    "favorite_categories": ["necklace", "earrings"],
    "purchase_frequency": "monthly"
  }
}
```

## Рекомендации по интеграции

### 1. Синхронизация дисконтных карт

**Частота:** Ежедневно или при изменении

**Процесс:**
1. Получить все дисконтные карты из `Catalog_ДисконтныеКарты`
2. Создать/обновить пользователей на сайте:
   - `phone` = `КодКартыШтрихкод`
   - `login` = `КодКартыШтрихкод`
   - `discount_card_id` = `Ref_Key`
   - `customer_id` = `ВладелецКарты_Key`

**Пример кода:**
```python
async def sync_discount_cards():
    url = f"{ONEC_API_URL}/Catalog_ДисконтныеКарты"
    response = await client.get(url)
    cards = response.json()['value']

    for card in cards:
        phone = card['КодКартыШтрихкод']
        # Создать/обновить пользователя
        await create_or_update_user(
            phone=phone,
            login=phone,
            discount_card_id=card['Ref_Key'],
            customer_id=card['ВладелецКарты_Key']
        )
```

### 2. Загрузка истории покупок

**Частота:** По запросу (через API `/api/admin/customers/{user_id}?sync=true`)

**Важно:** Автоматическая синхронизация при заходе в кабинет покупателя отключена для предотвращения бесконечных запросов к 1С.

**Процесс:**
1. Использовать скрипт `get_1c_sales_parsing.py` для получения покупок из 1С
2. Фильтровать по `Контрагент_Key`
3. Парсить поле `RecordSet` для извлечения движений
4. Дедуплицировать по `document_id_1c + product_id_1c + date`
5. Сохранить в БД для анализа
6. Обновить профиль покупателя

**Пример кода:**
```python
async def get_customer_purchase_history(customer_key: str, days: int = 365):
    start_date = datetime.now() - timedelta(days=days)

    url = f"{ONEC_API_URL}/AccumulationRegister_Продажи"
    params = {
        "$filter": f"Контрагент_Key eq guid'{customer_key}'",
        "$top": 100,  # Уменьшенный batch_size для обхода AUTOORDER ошибки
    }

    all_purchases = []
    skip = 0

    while True:
        params["$skip"] = skip
        response = await client.get(url, params=params)
        data = response.json()['value']

        if not data:
            break

        # Парсим RecordSet
        for record in data:
            for movement in record.get("RecordSet", []):
                if movement.get("Контрагент_Key") == customer_key:
                    all_purchases.append(movement)

        if len(data) < 100:
            break

        skip += 100

    return all_purchases
```

### 3. Создание образа покупателя

**Анализируемые метрики:**
- Средний чек
- Частота покупок
- Любимые категории товаров
- Сезонность покупок
- Предпочтения по брендам
- Любимые магазины (склады)

**Пример анализа:**
```python
def build_customer_profile(purchases):
    if not purchases:
        return None

    total_revenue = sum(p['Сумма'] for p in purchases)
    total_items = sum(p['Количество'] for p in purchases)

    # Категории товаров
    product_ids = [p['Номенклатура_Key'] for p in purchases]
    categories = get_product_categories(product_ids)

    # Частота покупок
    dates = [datetime.fromisoformat(p['Period']) for p in purchases]
    frequency = calculate_purchase_frequency(dates)

    return {
        "total_revenue": total_revenue,
        "average_check": total_revenue / len(purchases),
        "total_items": total_items,
        "purchase_count": len(purchases),
        "favorite_categories": get_top_categories(categories),
        "purchase_frequency": frequency,
        "last_purchase": max(dates).isoformat()
    }
```

## Настройка переменных окружения

```env
# 1С OData API
ONEC_API_URL=https://msk1.1cfresh.com/a/sbm/3322419/odata/standard.odata
ONEC_API_TOKEN=your_1c_api_token_here

# Endpoints для синхронизации
ONEC_DISCOUNT_CARDS_ENDPOINT=/Catalog_ДисконтныеКарты
ONEC_SALES_ENDPOINT=/AccumulationRegister_Продажи
ONEC_CUSTOMERS_ENDPOINT=/Catalog_Контрагенты
ONEC_PRODUCTS_ENDPOINT=/Catalog_Номенклатура

# Бонусы/лояльность
ONEC_LOYALTY_ENABLED=true
ONEC_LOYALTY_ENDPOINT=/AccumulationRegister_БонусныеБаллы_RecordType
ONEC_LOYALTY_ACCRUAL_ENDPOINT=/AccumulationRegister_НачисленияБонусныхБаллов_RecordType
# Поля для фильтрации (пробуются по порядку): БонуснаяКарта_Key - правильное поле для регистра бонусов
ONEC_LOYALTY_FILTER_FIELDS=БонуснаяКарта_Key,ДисконтнаяКарта_Key,ВладелецКарты_Key,Контрагент_Key,Покупатель_Key

# Планировщик синхронизации
CUSTOMER_SYNC_ENABLED=true
CUSTOMER_SYNC_INTERVAL_HOURS=4
CUSTOMER_SYNC_NIGHTLY_ENABLED=true
CUSTOMER_SYNC_NIGHTLY_HOUR=3
CUSTOMER_SYNC_NIGHTLY_MINUTE=0
CUSTOMER_SYNC_NIGHTLY_PURCHASE_DAYS=30
CUSTOMER_SYNC_NIGHTLY_CARDS_LIMIT=10000
```

## Известные проблемы и решения

### 1. Ошибка 500 при запросах к регистрам накопления

**Проблема:** 1С Fresh возвращает ошибку 500 при запросах к регистрам с суффиксом `_RecordType` или при использовании `$orderby`.

**Решение:**
- Использовать регистр `AccumulationRegister_Продажи` (без `_RecordType`)
- Не использовать `$orderby` в запросах
- Использовать пагинацию с меньшим `batch_size` (100-500)
- Сортировать данные на стороне приложения

**Пример:**
```python
# НЕПРАВИЛЬНО (вызывает ошибку 500)
GET /AccumulationRegister_Продажи_RecordType?$filter=...&$orderby=Period desc

# ПРАВИЛЬНО
GET /AccumulationRegister_Продажи?$filter=...&$top=100&$skip=0
```

### 2. Бесконечные запросы при заходе в кабинет покупателя

**Проблема:** Автоматическая синхронизация при загрузке страницы вызывает бесконечные запросы к 1С.

**Решение:** Отключена автоматическая синхронизация при заходе в кабинет. Синхронизация выполняется только через общую синхронизацию или по запросу.

## Полезные запросы OData

### Получить все дисконтные карты
```
GET /Catalog_ДисконтныеКарты?$top=1000&$orderby=Code
```

### Получить историю покупок покупателя
```
GET /AccumulationRegister_Продажи?$filter=Контрагент_Key eq guid'...'&$top=100
```

### Получить чеки покупателя
```
GET /DocumentJournal_РозничныеПродажи?$filter=Покупатель_Key eq guid'...'&$orderby=Date desc
```

### Получить информацию о товаре
```
GET /Catalog_Номенклатура(guid'...')
```

## Тестирование

Используйте скрипты для проверки подключения и анализа данных:

```bash
# Получение покупок из 1С
python get_1c_sales_parsing.py

# Проверка сумм между 1С и БД
python check_amounts.py

# Синхронизация покупок конкретного покупателя
python sync_customer_correct.py

# Восстановление начальных остатков
python restore_initial_balance.py
```

## Следующие шаги

1. **Реализовать синхронизацию дисконтных карт** - создать/обновить пользователей на сайте
2. **Загрузить историю покупок** - для существующих пользователей
3. **Создать систему анализа** - для построения образов покупателей
4. **Интегрировать с рекомендательной системой** - использовать данные для персонализации

## Скрипты для работы с данными

| Скрипт | Описание |
|--------|----------|
| `get_1c_sales_parsing.py` | Получение покупок из 1С через AccumulationRegister_Продажи |
| `sync_customer_correct.py` | Синхронизация покупок конкретного покупателя по контрагенту |
| `restore_initial_balance.py` | Восстановление "Ввода начальных остатков" |
| `check_amounts.py` | Проверка сумм между 1С и БД |
| `import_all_1c_purchases.py` | Импорт всех покупок из 1С в БД |
| `remove_extra_purchases.py` | Удаление лишних покупок из БД |
| `sync_with_1c.py` | Точная синхронизация с 1С (удаление и импорт) |
| `sync_customer_only.py` | Синхронизация только покупок данного покупателя |

## Примеры использования

### Синхронизация покупок покупателя
```bash
cd /root/glame-platform/backend
python3 sync_customer_correct.py
```

### Проверка данных
```bash
python3 check_amounts.py
```

### Получение покупок из 1С
```bash
python3 get_1c_sales_parsing.py
```
