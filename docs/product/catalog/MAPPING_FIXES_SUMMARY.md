# Сводка исправлений маппинга товаров из 1С

## Проблема

Ранее в коде `Code` (внутренний код 1С, например "НФ-00001248") использовался как артикул товара. Это неправильно, так как:
- `Code` - это внутренний системный код 1С
- `Артикул` - это реальный артикул товара (например, "AG25059", "KL02204004")

## Исправления

### 1. Маппинг полей (функция `map_1c_to_product`)

**Было:**
```python
external_code = self._get_first(item, ["Code", "code", "external_code", "Артикул", "article"])
article = self._get_first(item, ["Артикул", "article", "Article", "Code", "code"])
```

**Стало:**
```python
# Code - это внутренний код 1С, используем его как external_code
external_code = self._get_first(item, ["Code", "code"])
# Артикул - это реальный артикул товара (приоритет полю "Артикул")
article = self._get_first(item, ["Артикул", "article", "Article"])
```

### 2. Сохранение значений

**Было:**
```python
final_article = self._as_string(article) or self._as_string(external_code)
final_external_code = self._as_string(external_code) or final_article
```

**Стало:**
```python
# Артикул - это реальный артикул товара из поля "Артикул"
final_article = self._as_string(article)
# external_code - это внутренний код 1С из поля "Code"
final_external_code = self._as_string(external_code)
```

### 3. Сопоставление товаров (функция `sync_catalog`)

**Было:**
```python
external_code = mapped.get("external_code") or mapped.get("article")
# Поиск по external_code (который мог быть артикулом)
if external_code:
    result = await self.db.execute(
        select(Product).where(
            or_(
                Product.external_code == external_code,
                Product.article == external_code
            )
        )
    )
```

**Стало:**
```python
# external_code - это Code (внутренний код 1С)
external_code = mapped.get("external_code")
# article - это Артикул (реальный артикул товара)
article = mapped.get("article")

# 1. Поиск по артикулу (приоритет 1) - основной способ сопоставления
if article:
    result = await self.db.execute(
        select(Product).where(Product.article == article)
    )
    product = result.scalars().first()

# 2. Если не найден по артикулу, ищем по external_code (Code из 1С)
if not product and external_code:
    result = await self.db.execute(
        select(Product).where(Product.external_code == external_code)
    )
    product = result.scalars().first()

# 3. Если не найден, ищем по external_id (Ref_Key из 1С)
```

### 4. Обновление существующих товаров

**Было:**
```python
# Обновляем external_code и article из 1С (приоритет 1С)
if external_code:
    product.external_code = external_code
    product.article = external_code  # ❌ Неправильно!
```

**Стало:**
```python
# Обновляем external_code (Code) и article (Артикул) из 1С
if external_code:
    product.external_code = external_code  # Code (внутренний код 1С)
# article обновляется отдельно из поля "Артикул", не из Code
if mapped.get("article"):
    product.article = mapped.get("article")  # Артикул (реальный артикул)
```

### 5. Создание новых товаров

**Было:**
```python
# Убеждаемся, что артикул сохранен в обоих полях
if external_code:
    if not mapped.get("external_code"):
        mapped["external_code"] = external_code
    if not mapped.get("article"):
        mapped["article"] = external_code  # ❌ Неправильно!
```

**Стало:**
```python
# Убеждаемся, что код и артикул правильно сохранены
# external_code - это Code (внутренний код 1С)
if external_code and not mapped.get("external_code"):
    mapped["external_code"] = external_code
# article - это Артикул (реальный артикул товара)
# Не используем external_code как article, так как это разные вещи
```

### 6. Сохранение связи с основной карточкой

**Добавлено:**
```python
# Parent_Key - ссылка на основную карточку (для характеристик)
parent_key = self._get_first(item, ["Parent_Key", "parent_key", "Parent", "parent"])

# Сохраняем Parent_Key в specifications для связи с основной карточкой
if parent_key and parent_key != "00000000-0000-0000-0000-000000000000":
    specifications["parent_external_id"] = self._as_string(parent_key)
```

## Итоговая структура маппинга

| Поле 1С | Назначение | Поле в БД | Пример |
|---------|-----------|-----------|--------|
| `Ref_Key` | UUID товара в 1С | `external_id` | "15d539a2-ba46-11f0-836e-fa163e4cc04e" |
| `Code` | Внутренний код 1С | `external_code` | "НФ-00001248" |
| `Артикул` | Реальный артикул товара | `article` | "AG25059" |
| `Parent_Key` | Ссылка на основную карточку | `specifications["parent_external_id"]` | "b1b9a380-ba4b-11f0-836e-fa163e4cc04e" |

## Проверка

Для проверки правильности маппинга используйте:

```bash
python backend/show_products_table.py
```

Скрипт покажет таблицу товаров с правильным разделением Code и Артикул.

## Результат

✅ `Code` больше не используется как артикул  
✅ `Артикул` правильно извлекается из поля "Артикул"  
✅ Сопоставление товаров происходит по артикулу (приоритет 1)  
✅ Сохранена связь характеристик с основной карточкой через `Parent_Key`
