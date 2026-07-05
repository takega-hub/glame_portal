# ТЗ: план магазина на месяц + персональные планы продавцов

Дата: 2026-05-31 19:24 UTC
Инициатор: Anatoly / GLAME
Контекст: Аккаунт → Продавцы → KPI и выполнение (`/profile/sellers?tab=kpi`)

## 1. Цель

Доработать страницу месячного плана магазина так, чтобы администратор/управляющий видел:

1. План магазина на выбранный месяц по KPI-показателям.
2. Панель продавцов выбранной торговой точки.
3. По клику на продавца — персональный месячный план и выполнение продавца, рассчитанные от плана магазина.
4. Прозрачную формулу/источники данных: прошлый год, последние 3 месяца, 1С, график смен, бенчмаркинг конверсии.

## 2. Текущее состояние, проверено

Файлы реализации:

- `frontend/src/components/profile/ProfileSellersPage.tsx`
- `frontend/src/components/profile/SellerPersonalKpiPage.tsx`
- `frontend/src/components/profile/SellerKpiMainDashboard.tsx`
- `frontend/src/lib/api.ts`
- `backend/app/services/seller_kpi_service.py`
- `backend/app/api/admin/onec_customers.py`

Доступные endpoint-ы:

- `GET /api/admin/1c/sellers/kpi?month=YYYY-MM&store_name=...`
- `GET /api/admin/1c/sellers/kpi/targets?month=YYYY-MM&store_name=...`
- `PUT /api/admin/1c/sellers/kpi/targets`
- `GET /api/admin/1c/sellers/shifts?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&store_name=...`
- `GET /api/admin/1c/sellers/kpi/snapshots?month=YYYY-MM`

Проверка live API:

- `/health` → `HTTP 200 OK`, статус `healthy`.
- `2026-05`, `ТРК Центрум`, targets возвращают 12 строк KPI, план выручки `1 715 616`, факт `822 434.5`, план трафика `1400`, конверсия `0.09`.
- `2026-06`, `ТРК Центрум` пока без загруженных планов/фактов: планы нулевые/пустые.

Важно: в backend уже есть базовая формула персональных планов по часам:

```text
seller_revenue_plan = store_revenue_plan × seller_hours / store_total_hours
```

Метод: `SellerKPIService._formula_seller_plans()`.

## 3. UX-требование

### 3.1. Верх страницы KPI магазина

На текущей странице после блока фильтров `Магазин / Месяц` добавить управленческий блок:

- карточка «План магазина»:
  - магазин;
  - месяц;
  - плановая выручка;
  - факт;
  - % выполнения;
  - прогноз выполнения;
  - статус источника плана: `агент / ручная корректировка / импорт прошлый план-факт`;
- кнопка/бейдж `Собрать план агентом` для admin;
- предупреждение, если нет исходных данных для расчета.

### 3.2. Панель продавцов на странице плана магазина

Разместить панель продавцов рядом/под таблицей KPI, но выше длинной аналитики:

- горизонтальные карточки или левая колонка;
- показывать только продавцов выбранного магазина и месяца;
- поля карточки:
  - ФИО;
  - план выручки;
  - факт;
  - % выполнения;
  - часы/смены;
  - источник персонального плана;
- клик по карточке должен открывать/переключать персональный план продавца.

Рекомендуемое поведение MVP:

1. Без ухода со страницы: `selectedSeller` в состоянии страницы.
2. Справа/ниже показывать блок «Персональный план продавца».
3. Сохранять возможность открыть полную страницу: `/profile/sellers/personal?month=YYYY-MM&store_name=...&seller_external_id=...`.

### 3.3. Блок персонального плана продавца

По клику на продавца показывать:

- заголовок: ФИО, магазин, месяц;
- план продавца на месяц;
- факт и % выполнения;
- часы/смены и доля часов от магазина;
- таблицу KPI продавца:
  - выручка;
  - кол-во изделий;
  - средний чек;
  - средняя стоимость изделия;
  - длина чека;
  - кол-во чеков;
  - трафик;
  - выручка на вошедшего;
  - конверсия;
- формулу расчета:
  - `план магазина × часы продавца / часы магазина`;
  - для трафика: `трафик магазина × часы продавца / часы магазина`;
  - средний чек, средняя стоимость, длина чека, конверсия наследуются от магазина;
  - кол-во изделий и чеков считаются через производные KPI.

## 4. Логика сбора плана магазина агентом

### 4.1. Источники

Агент первоначально собирает месячный план магазина по каждому KPI из:

1. Показатели прошлого года за аналогичный месяц:
   - факт LFL;
   - прошлый план/факт после загрузки в БД.
2. Статистика последних 3 месяцев по магазину:
   - выручка;
   - кол-во изделий;
   - средний чек;
   - средняя стоимость единицы товара по 1С;
   - длина чека;
   - кол-во чеков;
   - трафик;
   - конверсия.
3. Данные 1С по каждой торговой точке:
   - продажи/чеки из `sales_records`;
   - средняя стоимость единицы товара = выручка / кол-во KPI-изделий, исключая упаковку/сопутствующие позиции;
   - товары считаются по текущим правилам исключений KPI.
4. Трафик торговой точки:
   - текущий источник store visits / FTP / analytics, если есть;
   - если нет — показатель остается с data-quality warning.
5. Конверсия:
   - первоначально по бенчмаркингу;
   - после накопления данных — факт магазина `checks / traffic`.

### 4.2. Формулы плана магазина

Рекомендуемый расчет:

```text
base_revenue = weighted_average(
  last_year_same_month_fact * lfl_growth_factor,
  avg_last_3_months_revenue,
  previous_plan_fact_adjustment
)

avg_item_price_plan = avg_1c_item_price_last_3_months_by_store
items_per_check_plan = avg_items_per_check_last_3_months_by_store
avg_check_plan = avg_item_price_plan × items_per_check_plan
traffic_plan = weighted_last_3_months_traffic_or_manual
conversion_plan = benchmark_conversion_by_store_type_or_fact
checks_plan = traffic_plan × conversion_plan
items_plan = checks_plan × items_per_check_plan
revenue_plan = checks_plan × avg_check_plan
revenue_per_visitor_plan = revenue_plan / traffic_plan
avg_sales_per_shift_plan = revenue_plan / planned_store_shifts
```

Если `revenue_plan` задан как главный KPI вручную/агентом, остальные показатели должны проверяться на математическую согласованность:

```text
revenue ≈ checks × avg_check
avg_check ≈ avg_item_price × items_per_check
checks ≈ traffic × conversion
items ≈ checks × items_per_check
```

### 4.3. Прозрачность агентского расчета

Нужно хранить/возвращать в API не только число, но и источник:

```json
{
  "metric_key": "revenue",
  "plan_value": 1715616,
  "source": "agent_initial_plan",
  "confidence": 0.82,
  "formula": "checks_plan * avg_check_plan",
  "inputs": {
    "last_year_same_month_fact": 1500000,
    "last_3_months_avg": 1620000,
    "benchmark_conversion": 0.092
  },
  "warnings": []
}
```

## 5. Доработки backend

### 5.1. Таблицы/поля

Текущая таблица `seller_kpi_target_plans` хранит только `plan_value`. Нужно добавить provenance:

- `source VARCHAR(64)` — `manual`, `agent_initial_plan`, `imported_plan_fact`, `excel_import`;
- `confidence NUMERIC(5,4) NULL`;
- `formula TEXT NULL`;
- `inputs JSONB NULL`;
- `warnings JSONB NULL`;
- `created_by_agent VARCHAR(128) NULL`;
- `approved_by_user_id UUID NULL` — на будущее, если агентский план требует подтверждения;
- `approved_at TIMESTAMPTZ NULL`.

Миграция должна быть отдельной, не через `ensure_tables()`.

### 5.2. Новый сервис расчета

Добавить метод в `SellerKPIService` или отдельный `SellerKpiPlanAgentService`:

```python
async def generate_store_month_plan(month: str, store_name: str, mode: str = "draft") -> dict:
    ...
```

Он должен:

1. собрать факты аналогичного месяца прошлого года;
2. собрать последние 3 месяца;
3. собрать/проверить трафик;
4. применить бенчмарк конверсии;
5. рассчитать KPI-план;
6. вернуть план + источники + предупреждения;
7. в `draft` режиме не писать в БД;
8. в `save` режиме писать только для admin и желательно после подтверждения.

### 5.3. Endpoint-ы

Добавить:

- `POST /api/admin/1c/sellers/kpi/targets/generate`
  - admin only;
  - body: `{ month, store_name, save?: boolean }`;
  - если `save=false`, вернуть draft;
  - если `save=true`, сохранить план с source `agent_initial_plan`.

Доработать:

- `GET /api/admin/1c/sellers/kpi/targets`
  - добавить metadata по источникам плана;
  - добавить `last_year_fact` и `lfl_deviation`, когда прошлый план/факт загружен в БД.

### 5.4. Персональные планы продавцов

Текущую формулу `_formula_seller_plans()` сохранить как базовую. Доработать вывод строк продавцов:

- `hours_share = seller_hours / store_total_hours`;
- `store_hours_plan`;
- персональные планы по всем KPI, а не только в отдельных optional полях:
  - `personal_metrics: { metric_key: { plan, fact, percent, source } }`.

## 6. Доработки frontend

### 6.1. `ProfileSellersPage.tsx`

Добавить состояние:

```ts
const [selectedSellerKey, setSelectedSellerKey] = useState<string | null>(null);
const selectedSeller = useMemo(...mergedSellerRows...);
```

Добавить блок `SellerPlanPanel`:

- список карточек продавцов выбранного магазина;
- по клику меняет `selectedSellerKey`;
- активная карточка подсвечена золотым;
- если продавцов нет — warning о графике/плане/привязке 1С.

Добавить блок `SelectedSellerMonthlyPlan`:

- читает `selectedSeller`;
- показывает личные KPI и формулу;
- ссылка на полную страницу персонального KPI.

### 6.2. `SellerPersonalKpiPage.tsx`

Проверить, что страница использует `seller_external_id` как основной ключ и не fallback-ится на первого продавца.

Добавить отображение:

- source плана;
- hours share;
- store total hours;
- personal KPI table.

### 6.3. `frontend/src/lib/api.ts`

Добавить типы:

- `SellerKpiPlanSource`;
- `SellerKpiTargetRow.source/confidence/formula/inputs/warnings`;
- `SellerPersonalMetricPlan`;
- метод `generateSellerKpiTargets()`.

## 7. Acceptance criteria

1. На `/profile/sellers?tab=kpi&store_name=ТРК Центрум&month=2026-05` видна панель продавцов выбранного магазина.
2. Клик по продавцу показывает его персональный план без перехода на другую страницу.
3. Персональный план выручки = `план магазина × часы продавца / часы магазина`.
4. Сумма персональных планов продавцов по магазину ≈ план магазина, допустимое расхождение только округление.
5. У каждого KPI плана магазина отображается источник: manual/agent/import.
6. Агентский draft плана можно получить без записи в БД.
7. Сохранение агентского плана доступно только admin.
8. `last_year_fact` и `lfl_deviation` заполняются после загрузки прошлых план/фактов в БД.
9. Manager видит аналитику и персональные планы, но не может сохранять план магазина.
10. Если трафик/прошлый год/3 месяца недоступны, UI показывает data-quality warning, а не молча ставит 0.

## 8. Проверки после реализации

Backend:

```bash
cd /workspace/glame-platform/backend
python -m py_compile app/services/seller_kpi_service.py app/api/admin/onec_customers.py
pytest tests/test_seller_kpi_receipt_facts.py tests/test_seller_personal_kpi_shift_calendar.py -q
```

Frontend:

```bash
cd /workspace/glame-platform/frontend
npx tsc --noEmit --pretty false
npx eslint src/components/profile/ProfileSellersPage.tsx src/components/profile/SellerPersonalKpiPage.tsx src/lib/api.ts --max-warnings=0
```

Live API smoke:

```bash
python /workspace/tools/glame_api.py get '/api/admin/1c/sellers/kpi/targets?month=2026-05&store_name=%D0%A2%D0%A0%D0%9A%20%D0%A6%D0%B5%D0%BD%D1%82%D1%80%D1%83%D0%BC'
python /workspace/tools/glame_api.py get '/api/admin/1c/sellers/kpi?month=2026-05&store_name=%D0%A2%D0%A0%D0%9A%20%D0%A6%D0%B5%D0%BD%D1%82%D1%80%D1%83%D0%BC'
```

## 9. Риски

- В рабочем дереве сейчас много несвязанных изменений; перед кодовой реализацией нужен отдельный branch и аккуратный diff только по KPI-файлам.
- Нельзя писать ALTER TABLE из request-time `ensure_tables()` — только миграция.
- Нельзя считать персональный план равным делению на количество продавцов; только через часы/смены.
- Конверсия хранится как ratio (`0.09` = 9%), UI форматирует как процент.
- Store names должны оставаться точными 1С/API значениями: `ТРК Центрум`, `Ялта, Набережная 18`, `Меганом`.
