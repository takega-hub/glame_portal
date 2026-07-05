# Импорт исторических отчетов план/факт по магазинам

Дата: 2026-05-31
Файлы от пользователя:

- `Ежемесячные отчеты_ЯЛта.zip`
- `Ежемесячные Отчеты_Центрум.zip`

## Статус доступа к файлам

Hermes получил ссылки на host upload paths:

- `/root/hermes-web-ui/upload/default/9822549993f2a2ac.zip`
- `/root/hermes-web-ui/upload/default/fd4177e233de0254.zip`

В текущем Docker terminal backend эти пути не смонтированы: файлов нет в `/root/hermes-web-ui/upload/default`, поиск `*.zip` по контейнеру также не нашел эти архивы.

Следующий технический шаг: переложить архивы в доступный для контейнера путь, например:

```text
/workspace/glame-platform/data/imports/plan_fact/
```

После этого можно выполнить read-only inventory и подготовить dry-run импорт.

## Назначение данных

Эти архивы — исторические отчеты план/факт по магазинам. Они нужны для БД как источник:

1. аналогичного месяца прошлого года;
2. предыдущих планов и факта по KPI;
3. LFL-сравнения;
4. агентского расчета будущих планов магазина;
5. проверки качества планирования по магазинам и продавцам.

## Рекомендуемая staging-модель БД

Создать отдельные таблицы исторического импорта, не смешивая их сразу с текущими target plans.

### `seller_kpi_store_plan_fact_imports`

Один импортированный файл/лист/период.

Поля:

- `id UUID PRIMARY KEY`
- `store_name TEXT NOT NULL`
- `period_month DATE NOT NULL`
- `source_file TEXT NOT NULL`
- `source_archive TEXT NULL`
- `source_sheet TEXT NULL`
- `source_hash TEXT NOT NULL`
- `import_status TEXT NOT NULL DEFAULT 'parsed'`
- `raw_metadata JSONB NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Уникальность:

```sql
UNIQUE (store_name, period_month, source_hash)
```

### `seller_kpi_store_plan_fact_rows`

Нормализованные KPI-строки магазина за месяц.

Поля:

- `id UUID PRIMARY KEY`
- `import_id UUID REFERENCES seller_kpi_store_plan_fact_imports(id)`
- `store_name TEXT NOT NULL`
- `period_month DATE NOT NULL`
- `metric_key TEXT NOT NULL`
- `metric_label TEXT NULL`
- `plan_value NUMERIC(18, 6) NULL`
- `fact_value NUMERIC(18, 6) NULL`
- `completion_percent NUMERIC(10, 4) NULL`
- `forecast_value NUMERIC(18, 6) NULL`
- `forecast_percent NUMERIC(10, 4) NULL`
- `deviation_value NUMERIC(18, 6) NULL`
- `raw_row JSONB NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Уникальность:

```sql
UNIQUE (store_name, period_month, metric_key, import_id)
```

## Маппинг KPI

Нормализовать русские строки отчетов в ключи платформы:

| Русское название / варианты | metric_key | Формат |
|---|---|---|
| Выручка, Оборот, Продажи | `revenue` | money |
| Кол-во изделий, Количество изделий | `items_count` | number |
| Средний чек | `avg_check` | money |
| Средняя стоимость изделия, Средняя стоимость ед. товара | `avg_item_price` | money |
| Длина чека, Изделий в чеке | `items_per_check` | decimal |
| Кол-во чеков, Чеки | `checks_count` | number |
| Кол-во смен, Смены | `shifts_count` | number |
| Средние продажи в смену | `avg_sales_per_shift` | money |
| Трафик, Вошедшие | `traffic` | number |
| Выручка на вошедшего | `revenue_per_visitor` | money |
| Конверсия | `conversion` | ratio/percent |

Важно: конверсию хранить как ratio (`0.09` = 9%), даже если в Excel она указана как `9%`.

## Как использовать в текущем KPI-сервисе

После импорта:

1. `GET /api/admin/1c/sellers/kpi/targets` должен подтягивать `last_year_fact` из `seller_kpi_store_plan_fact_rows`:
   - текущий месяц `2026-06` → аналогичный исторический месяц `2025-06`;
   - фильтр по `store_name` и `metric_key`.
2. `lfl_deviation` считать как:

```text
current_fact - last_year_fact
```

или процентно в дополнительном поле:

```text
(current_fact / last_year_fact - 1) × 100
```

3. Агентский расчет будущего плана должен использовать:
   - `last_year_fact` из импортированной истории;
   - `plan_value` прошлого периода для анализа качества планирования;
   - последние 3 месяца из 1С/live DB;
   - фактический traffic/conversion, если есть.

## Безопасный workflow импорта

1. Распаковать архивы в staging-директорию.
2. Прочитать имена файлов, листы, размеры и хэши.
3. Dry-run parsing:
   - определить store;
   - определить month;
   - распознать KPI строки;
   - показать первые 20 нормализованных строк;
   - показать неизвестные/неразобранные строки.
4. Сформировать CSV/JSON preview.
5. Только после подтверждения Anatoly — записывать в staging-таблицы БД.
6. После записи выполнить контроль:
   - количество месяцев по каждому магазину;
   - количество KPI строк по месяцу;
   - отсутствие дублей;
   - корректность conversion ratio;
   - сравнение суммы/выручки с исходным отчетом.

## Команды проверки после доступа к файлам

```bash
python - <<'PY'
import zipfile, pathlib
for p in pathlib.Path('/workspace/glame-platform/data/imports/plan_fact').glob('*.zip'):
    print(p, p.stat().st_size)
    with zipfile.ZipFile(p) as z:
        for i in z.infolist():
            print(' ', i.filename, i.file_size)
PY
```

Если внутри Excel:

```bash
python - <<'PY'
import pandas as pd, pathlib
for f in pathlib.Path('/workspace/glame-platform/data/imports/plan_fact').rglob('*.xls*'):
    xl = pd.ExcelFile(f)
    print(f, xl.sheet_names)
    for sheet in xl.sheet_names[:5]:
        df = pd.read_excel(f, sheet_name=sheet, header=None, nrows=20)
        print(sheet)
        print(df.head(10).to_string())
PY
```
