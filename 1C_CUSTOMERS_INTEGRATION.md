# Интеграция покупателей и истории покупок из 1С УНФ ФРЕШ

## Обзор

Данный документ описывает интеграцию данных о покупателях, дисконтных картах и истории покупок из 1С УНФ ФРЕШ для создания профилей покупателей и персонализации.

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

### 2. История покупок (AccumulationRegister_Продажи_RecordType)

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

**Использование:**
```python
# Получение истории покупок конкретного покупателя
GET /odata/standard.odata/AccumulationRegister_Продажи_RecordType?$filter=Контрагент_Key eq guid'c6c1ea96-bb11-11f0-836e-fa163e4cc04e'&$orderby=Period desc

# Покупки за период
GET /odata/standard.odata/AccumulationRegister_Продажи_RecordType?$filter=Period ge 2025-01-01T00:00:00 and Period le 2025-12-31T23:59:59
```

**Для создания образа покупателя:**
- Анализ предпочтений по товарам (Номенклатура_Key)
- Частота покупок (анализ Period)
- Средний чек (Сумма / количество покупок)
- Сезонность (группировка по месяцам)
- Любимые категории (через связь с Catalog_Номенклатура)

### 3. Продажи по дисконтным картам (AccumulationRegister_ПродажиПоДисконтнымКартам_RecordType)

**Назначение:** Прямая связь продаж с дисконтными картами

**Важные поля:**
- `Period` - дата продажи
- `Сумма` - сумма продажи
- `Количество` - количество товара
- `ДисконтнаяКарта_Key` - ID дисконтной карты
- `ВладелецКарты_Key` - ID владельца карты
- `Номенклатура_Key` - ID товара

**Использование:**
```python
# Продажи по конкретной дисконтной карте
GET /odata/standard.odata/AccumulationRegister_ПродажиПоДисконтнымКартам_RecordType?$filter=ДисконтнаяКарта_Key eq guid'...'
```

### 4. Документы продаж (DocumentJournal_РозничныеПродажи)

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

### 5. Контрагенты (Catalog_Контрагенты)

**Назначение:** Полная информация о покупателях

**Важные поля:**
- `Ref_Key` - ID контрагента
- `Code` - код контрагента
- `Description` - наименование
- Дополнительные поля контактов (если доступны)

**Связь:**
- Дисконтные карты → `ВладелецКарты_Key` → `Catalog_Контрагенты.Ref_Key`

### 6. Номенклатура (Catalog_Номенклатура)

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

**Частота:** Ежедневно или по запросу

**Процесс:**
1. Для каждого покупателя получить историю покупок
2. Сохранить в БД для анализа
3. Обновить профиль покупателя

**Пример кода:**
```python
async def get_customer_purchase_history(customer_key: str, days: int = 365):
    start_date = datetime.now() - timedelta(days=days)
    filter_query = f"Контрагент_Key eq guid'{customer_key}' and Period ge {start_date.isoformat()}"
    
    url = f"{ONEC_API_URL}/AccumulationRegister_Продажи_RecordType"
    params = {
        "$filter": filter_query,
        "$orderby": "Period desc"
    }
    response = await client.get(url, params=params)
    return response.json()['value']
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
ONEC_API_TOKEN=b2RhdGEudXNlcjpvcGV4b2JvZQ==

# Endpoints для синхронизации
ONEC_DISCOUNT_CARDS_ENDPOINT=/Catalog_ДисконтныеКарты
ONEC_SALES_ENDPOINT=/AccumulationRegister_Продажи_RecordType
ONEC_SALES_BY_CARD_ENDPOINT=/AccumulationRegister_ПродажиПоДисконтнымКартам_RecordType
ONEC_SALES_BY_CARD_FILTER_FIELDS=ДисконтнаяКарта_Key,ДисконтнаяКарта,Карта_Key,Карта
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

## Полезные запросы OData

### Получить все дисконтные карты
```
GET /Catalog_ДисконтныеКарты?$top=1000&$orderby=Code
```

### Получить историю покупок покупателя
```
GET /AccumulationRegister_Продажи_RecordType?$filter=Контрагент_Key eq guid'...'&$orderby=Period desc&$top=100
```

### Получить продажи по дисконтной карте
```
GET /AccumulationRegister_ПродажиПоДисконтнымКартам_RecordType?$filter=ДисконтнаяКарта_Key eq guid'...'&$orderby=Period desc
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

Используйте скрипт `test_customers_and_purchases.py` для проверки подключения и анализа данных:

```bash
python test_customers_and_purchases.py
```

Скрипт покажет:
- Структуру данных дисконтных карт
- Примеры истории покупок
- Статистику по покупателям
- Рекомендации по интеграции

## Следующие шаги

1. **Реализовать синхронизацию дисконтных карт** - создать/обновить пользователей на сайте
2. **Загрузить историю покупок** - для существующих пользователей
3. **Создать систему анализа** - для построения образов покупателей
4. **Интегрировать с рекомендательной системой** - использовать данные для персонализации
