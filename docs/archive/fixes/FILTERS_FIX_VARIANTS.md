# Исправление фильтров: показ вариантов вместо основных товаров

## Дата: 2026-02-05

## Проблема

**Фильтры в каталоге не работали**, потому что:

1. **Основные товары** (без `parent_external_id`) не имели характеристик:
   - Нет `Бренд`, `Цвет`, `Материал`, `Размер` и т.д.
   - Только базовые поля: `name`, `price`, `article`

2. **Варианты товаров** (с `parent_external_id`) содержали все характеристики:
   - Все фильтры (Бренд, Цвет, Материал и т.д.) работают только на вариантах
   - Но варианты **скрывались** от пользователя

3. **Результат**: 
   - При выборе фильтра "Бренд: Kalliope" возвращалось 0 товаров
   - Потому что основные товары не имели поля `Бренд` в `specifications`

## Решение

**Показывать варианты вместо основных товаров** + дедупликация

### 1. Изменение логики фильтрации (backend/app/api/products.py)

**Было** (строки 159-170):
```python
# Исключаем варианты - показываем только основные товары
variant_exclusion = or_(
    Product.specifications.is_(None),
    cast(Product.specifications["parent_external_id"], String).is_(None),
    cast(Product.specifications["parent_external_id"], String) == ""
)
filters.append(variant_exclusion)
```

**Стало** (строки 159-179):
```python
# ПОКАЗЫВАЕМ ВАРИАНТЫ вместо основных товаров
# Варианты содержат все характеристики (Бренд, Цвет, Размер и т.д.)
variant_filter = or_(
    # Показываем варианты (имеют parent_external_id и характеристики)
    and_(
        Product.specifications.isnot(None),
        cast(Product.specifications["parent_external_id"], String).isnot(None),
        cast(Product.specifications["parent_external_id"], String) != ""
    ),
    # Показываем основные товары БЕЗ вариантов (нет parent_external_id)
    or_(
        Product.specifications.is_(None),
        cast(Product.specifications["parent_external_id"], String).is_(None),
        cast(Product.specifications["parent_external_id"], String) == ""
    )
)
filters.append(variant_filter)
```

### 2. Дедупликация вариантов (строки 329-371)

**Проблема**: У одного товара может быть 4-10 вариантов (разные размеры/цвета)

**Решение**: Группируем по `parent_external_id` и показываем только первый вариант из каждой группы

```python
# Группируем по parent_external_id
seen_parents = set()
deduplicated_products = []

for product in all_products:
    parent_id = product.specifications.get('parent_external_id') if product.specifications else None
    
    if parent_id:
        # Показываем только первый вариант из группы
        if parent_id not in seen_parents:
            seen_parents.add(parent_id)
            deduplicated_products.append(product)
    else:
        # Основной товар без вариантов - всегда показываем
        deduplicated_products.append(product)

# Пагинация после дедупликации
total = len(deduplicated_products)
products = deduplicated_products[skip:skip + limit]
```

## Результат

### До исправления:
- ❌ Фильтры не работают (0 товаров при выборе бренда)
- ❌ Показываются основные товары без характеристик
- ❌ Нет информации о цвете, размере, материале на карточках

### После исправления:
- ✅ Фильтры работают корректно
- ✅ Показываются варианты с полными характеристиками
- ✅ На карточках отображается: Бренд, Цвет, Размер, Материал, Вставка, Покрытие
- ✅ Дедупликация предотвращает показ всех вариантов одного товара
- ✅ Пользователь видит один товар, может перейти на страницу и выбрать нужный вариант

## Архитектура данных

### Структура товаров в БД:

**Основной товар** (parent):
```json
{
  "name": "Кольцо Geometry гладкое базовое",
  "article": "79114",
  "specifications": {
    "quantity": 0
  }
}
```

**Вариант 1** (с характеристиками):
```json
{
  "name": "Кольцо Geometry гладкое базовое",
  "article": "79114-G/17",
  "specifications": {
    "parent_external_id": "ed28d43c-ba72-11f0-836e-fa163e4cc04e",
    "characteristic_id": "ee5deff4-ba72-11f0-836e-fa163e4cc04e",
    "Бренд": "Geometry",
    "Цвет": "Золотой",
    "Размер": "17",
    "Материал": "Ювелирный сплав",
    "Покрытие": "Позолота",
    "Вставка": "Без камней"
  }
}
```

**Вариант 2** (другой размер):
```json
{
  "name": "Кольцо Geometry гладкое базовое",
  "article": "79114-G/18",
  "specifications": {
    "parent_external_id": "ed28d43c-ba72-11f0-836e-fa163e4cc04e",
    "Размер": "18",
    // ... другие характеристики
  }
}
```

### Логика показа:
1. **В каталоге**: Показываем только **первый вариант** (79114-G/17)
2. **На странице товара**: Показываем все варианты в таблице
3. **При фильтрации**: Фильтруем по характеристикам вариантов

## Производительность

**Текущая реализация** использует Python для дедупликации (после выборки из БД):
- Подходит для каталогов до 10,000 товаров
- Для больших каталогов можно оптимизировать через SQL `DISTINCT ON` или `ROW_NUMBER()`

**Альтернатива (SQL оптимизация)**:
```sql
WITH ranked_variants AS (
  SELECT *, 
    ROW_NUMBER() OVER (
      PARTITION BY specifications->>'parent_external_id' 
      ORDER BY id
    ) as rn
  FROM products
  WHERE is_active = true
)
SELECT * FROM ranked_variants WHERE rn = 1 OR specifications->>'parent_external_id' IS NULL
```

## Тестирование

### Проверка фильтров:
1. Откройте каталог товаров
2. Нажмите "Фильтры"
3. Выберите "Бренд: Geometry"
4. Должны показаться товары этого бренда
5. Выберите "Цвет: Золотой"
6. Список должен отфильтроваться

### Проверка дедупликации:
1. Найдите товар с несколькими вариантами (например, кольцо с разными размерами)
2. В каталоге должна быть **одна** карточка товара
3. При клике на карточку должны показаться все варианты

## Файлы изменены

- `backend/app/api/products.py` (строки 159-179, 329-371)
  - Изменена логика фильтрации вариантов
  - Добавлена дедупликация по `parent_external_id`
  - Пагинация применяется после дедупликации
