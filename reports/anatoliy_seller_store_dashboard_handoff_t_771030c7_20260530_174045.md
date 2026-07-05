# Handoff Анатолию: дашборд магазинов и продавцов с корректными планами

Task: t_771030c7 / GLAME Platform task 2982bd02-1759-48a2-8772-b270fcea4351
Дата проверки: 2026-05-30 17:40 UTC

## Главный вывод

В кодовой базе уже есть основа управленческого dashboard для магазинов и продавцов:

- Backend: `backend/app/services/seller_kpi_service.py`
- Backend routes: `backend/app/api/admin/onec_customers.py` под prefix `/api/admin/1c`
- Frontend API: `frontend/src/lib/api.ts`
- Frontend UI: `frontend/src/components/profile/ProfileSellersPage.tsx`, `SellerKpiMainDashboard.tsx`, `SellerPersonalKpiPage.tsx`
- Навигация: `frontend/src/config/navigation.ts` → `/profile/sellers/dashboard`

Dashboard по KPI за май отвечает по live API и разделяет Ялту и ТРК Центрум. План Ялты не попадает в Центрум: у магазинов отдельные `store_id`, `store_name`, `revenue_plan`, `completion_percent`.

## Проверка live API

Проверенный endpoint:

```text
GET /api/admin/1c/sellers/kpi/dashboard?month=2026-05
```

Результат до последующего 502:

```json
{
  "data_quality": {
    "duplicate_store_rows": 0,
    "seller_field_status": "ok",
    "unmatched_sellers": 0
  },
  "totals": {
    "revenue": 2122512.05,
    "revenue_plan": 4569987.52,
    "completion_percent": 46.44,
    "forecast_percent": 47.99,
    "checks": 158,
    "items_sold": 264.0,
    "avg_check": 13433.62,
    "items_per_check": 1.67,
    "shifts_count": 84
  }
}
```

Магазины:

```json
[
  {
    "store_id": "3daee4e4-a2ab-11f0-96fc-fa163e4cc04e",
    "store_name": "Ялта, Набережная 18",
    "revenue": 1490561.95,
    "revenue_plan": 2854371.52,
    "completion_percent": 52.22,
    "forecast_percent": 53.96,
    "checks": 101,
    "items_sold": 183.0,
    "shifts_count": 47
  },
  {
    "store_id": "6c3a8322-a2ab-11f0-96fc-fa163e4cc04e",
    "store_name": "ТРК Центрум",
    "revenue": 631950.10,
    "revenue_plan": 1715616.00,
    "completion_percent": 36.84,
    "forecast_percent": 38.06,
    "checks": 57,
    "items_sold": 81.0,
    "shifts_count": 37
  }
]
```

Пример seller-level строк:

```json
[
  {
    "seller_external_id": "1d5f839e-ba5a-11f0-836e-fa163e4cc04e",
    "seller_name": "Рогалевич Ирина",
    "store_name": "Ялта, Набережная 18",
    "revenue": 868801.14,
    "revenue_plan": 1103016.72,
    "completion_percent": 78.8,
    "checks": 52,
    "items_sold": 100.0,
    "plan_source": "excel_formula_hours_share"
  },
  {
    "seller_external_id": "eee9caf0-293b-11f1-83c6-fa163e4cc04e",
    "seller_name": "Бешлиева Аджере",
    "store_name": "ТРК Центрум",
    "revenue": 505301.06,
    "revenue_plan": 879057.48,
    "completion_percent": 57.5,
    "checks": 43,
    "items_sold": 63.0,
    "plan_source": "excel_formula_hours_share"
  }
]
```

## Соответствие acceptance criteria

### 1. План Ялты и Центрума невозможно перепутать

Частично выполнено на KPI dashboard:

- `SellerKPIService.dashboard()` строит строки по `store_name` и `store_id`.
- `seller_kpi_target_plans` хранит планы по scope: `scope_type='store'`, `scope_key=<store_name>`.
- Персональные планы продавцов считаются как доля часов продавца от часов магазина:
  `store plan × seller hours / total store hours`.
- В ответе live API Ялта и Центрум имеют разные планы и разные store_id.

Что добавить для полной приемки:

- Явно отдавать в API/UI поля диагностики плана: `plan_source`, `plan_period`, `plan_store_name`, `plan_match_status`, `plan_updated_at` не только на seller rows, но и на store rows / target rows.
- Если план магазина не заведен, показывать предупреждение, а не считать выполнение/перевыполнение по нулевому или чужому плану.

### 2. Если план Центрума не загружен/не подтвержден — показывать warning

Частично выполнено: если `revenue_plan` отсутствует, проценты становятся `null`, а не ложным перевыполнением.

Недостаток: в UI/API пока нет отдельного явного warning вида `plan_missing_or_unconfirmed` для магазина.

Рекомендация: добавить в `SellerKPIService.dashboard()` поле:

```json
"plan_quality": {
  "status": "ok | missing | unconfirmed | derived",
  "source": "manual_admin_ui | yandex_excel | excel_formula_hours_share",
  "message": "..."
}
```

### 3. Доля “Не сопоставлено с продавцом” видна отдельно

В KPI dashboard за май live API показывает:

```json
"seller_field_status": "ok",
"unmatched_sellers": 0
```

Это хорошо для KPI dashboard.

Но endpoint детальных продаж пока не соответствует acceptance на live API.

Проверенный endpoint:

```text
GET /api/analytics/1c-sales/details?period=month&limit=5
```

Live response вернул продажи без seller fields:

```json
{
  "seller_id": null,
  "seller_external_id": null,
  "seller_name": null,
  "seller_match_status": null,
  "check_id": null
}
```

В source-коде `backend/app/api/analytics.py` уже есть логика извлечения seller fields из `raw_data` и `seller_matching/data_warnings`, но live response выглядит как старый backend или stale deployment. Нужно перезапустить/задеплоить backend и повторить проверку.

### 4. Детальные продажи должны отдавать seller_id/seller_name/check/store/date/product/brand/category/revenue/quantity

В source-коде уже подготовлены поля:

- `seller_id`
- `seller_external_id`
- `seller_name`
- `seller_match_status`
- `seller_unmatched`
- `check_id`
- `store_id`, `store_name`
- `sale_date`
- `product_name`, `product_brand`, `product_category`
- `revenue`, `quantity`

Но live API сейчас не подтверждает это. Это deployment blocker.

### 5. Если seller data отсутствует — dashboard не делает персональные выводы и показывает data-warning

Source-код `analytics.py` уже содержит `data_warnings` и `seller_matching`, но live endpoint их не отдает. Нужно применить код на running backend.

## Что передать Анатолию как next engineering actions

1. Перезапустить/задеплоить backend, потому что live `/api/analytics/1c-sales/details` не соответствует текущему source-коду.
2. Повторить read-only checks:

```bash
python /workspace/tools/glame_api.py get /health
python /workspace/tools/glame_api.py get '/api/admin/1c/sellers/kpi/dashboard?month=2026-05'
python /workspace/tools/glame_api.py get '/api/analytics/1c-sales/details?period=month&limit=20'
```

3. Добавить explicit plan diagnostics на store/target rows:

- `plan_source`
- `plan_period`
- `plan_store_name`
- `plan_match_status`
- `plan_updated_at`
- `plan_quality.status`

4. В UI `/profile/sellers/dashboard` показать warning по магазину, если:

- план отсутствует;
- план не подтвержден;
- план источник/магазин не совпадает с текущим store;
- `seller_matching.status='warning'` или `unmatched_share > 0`.

5. Не считать “перевыполнение” и не делать персональные выводы по продавцу, если:

- `seller_field_status != ok`;
- строка имеет `seller_match_status='unmatched'`;
- значительная часть продаж не сопоставлена с продавцом.

6. После deploy проверить, что endpoint детальных продаж реально содержит seller fields и warning:

```json
{
  "seller_matching": {
    "page_unmatched": 0,
    "page_total": 20,
    "page_unmatched_share": 0.0,
    "status": "ok"
  }
}
```

## Верификация в коде

Команды, выполненные локально в контейнере:

```bash
python -m py_compile backend/app/services/seller_kpi_service.py backend/app/services/onec_sellers_service.py backend/app/api/admin/onec_customers.py backend/app/api/analytics.py
cd frontend && npx tsc --noEmit --pretty false --skipLibCheck
cd frontend && npx eslint src/components/profile/ProfileSellersPage.tsx src/components/profile/SellerKpiMainDashboard.tsx src/components/profile/SellerPersonalKpiPage.tsx src/lib/api.ts --max-warnings=0
```

Результат: все команды завершились с exit code 0.

## Риск/блокер

После нескольких API checks nginx bridge начал возвращать `502 Bad Gateway` даже на `/health`. Это не похоже на проблему кода frontend; нужно проверить running backend/service на хосте и логи reverse proxy/backend. До восстановления API нельзя закрывать задачу как Done.

## Итоговый статус

- Handoff для Анатолия подготовлен.
- KPI dashboard частично подтвержден live API: Ялта/Центрум разделены, планы разные, seller KPI есть.
- Детальные продажи и data-warning требуют deploy/restart verification.
- Задачу нельзя закрывать как Done до технического подтверждения live endpoint `/api/analytics/1c-sales/details` и восстановления `/health` после 502.
