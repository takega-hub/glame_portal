# Быстрый старт: Импорт исторических данных

## Шаг 1: Установка зависимостей

```bash
cd backend
pip install pandas openpyxl xlrd
```

## Шаг 2: Расширение таблицы

```bash
python extend_sales_record_table.py
```

Это добавит новые поля в таблицу `sales_records`:
- product_name, product_article, product_category, product_brand, product_type

## Шаг 3: Импорт данных

```bash
python import_historical_sales_from_excel.py
```

Или с указанием файла:
```bash
python import_historical_sales_from_excel.py --file "путь/к/файлу.xls"
```

## Результат

Данные будут импортированы в таблицу `sales_records` с:
- Автоматическим сопоставлением товаров по артикулам
- Заполнением категорий и брендов из каталога
- Статистикой импорта

## Проверка

```sql
SELECT COUNT(*) FROM sales_records WHERE sync_batch_id LIKE 'historical_import%';
```

Подробная документация: [HISTORICAL_SALES_IMPORT.md](HISTORICAL_SALES_IMPORT.md)
