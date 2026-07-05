# Handoff для Анатолия: дашборд магазинов и продавцов с корректными планами

Задача Kanban: `t_771030c7`
Platform task: `2982bd02-1759-48a2-8772-b270fcea4351`
Статус: подготовлено к техническому ревью / deploy decision.

## Контекст

Елена указала критичную ошибку в майском отчёте: ссылка Яндекс.Диска относится к Ялте, а не к ТРК Центрум. Поэтому нельзя подставлять план Ялты в Центрум и показывать ложное перевыполнение.

Бизнес-ограничение: не делать персональные выводы по консультанту, если продажа не сопоставлена с продавцом или товар не был в наличии.

## Что уже есть в рабочем дереве

### Backend

1. `backend/app/services/seller_kpi_service.py`
   - есть `SellerKPIService.dashboard(...)` для главного read-only dashboard по всем магазинам/продавцам;
   - планы берутся отдельно по store-level target metrics;
   - факты считаются из 1C sales records;
   - упаковка/пакеты/сертификаты и похожие служебные позиции исключаются из KPI item facts;
   - есть `data_quality`: `unmatched_sellers`, `duplicate_store_rows`, `seller_field_status`.

2. `backend/app/api/admin/onec_customers.py`
   - есть endpoint:
     `GET /api/admin/1c/sellers/kpi/dashboard?month=YYYY-MM`
   - доступ: `admin`, `manager`.

3. `backend/app/api/analytics.py`
   - доработан detailed sales endpoint:
     `GET /api/analytics/1c-sales/details`
   - для каждой строки продаж добавляются поля:
     - `document_id`
     - `check_id`
     - `seller_id`
     - `seller_external_id`
     - `seller_name`
     - `seller_match_status`
     - `seller_unmatched`
   - seller берётся из `sales_records.raw_data`: `Продавец_Key`, `Сотрудник_Key`, `Кассир_Key`, `Ответственный_Key`, `Менеджер_Key`, затем name fallback.
   - zero GUID `00000000-0000-0000-0000-000000000000` не считается валидным seller id.

### Frontend

1. `frontend/src/lib/api.ts`
   - есть типы `SellerKpiDashboardResponse`, `SellerKpiDashboardStore`, `SellerKpiDashboardMetricCell`;
   - есть метод `api.getSellerKpiDashboard({ month })`.

2. `frontend/src/components/profile/SellerKpiMainDashboard.tsx`
   - главный dashboard:
     - выручка/план/%;
     - прогноз месяца;
     - средний чек;
     - изделия/чек;
     - сравнение магазинов;
     - карточки магазинов;
     - seller leaderboard;
     - risk sellers;
     - KPI heatmap;
     - insights;
     - data quality warning.
   - fallback: если dashboard endpoint ещё не развернут и отдаёт 404, UI показывает базовую сводку из `/api/admin/1c/sellers/kpi` и предупреждение.

3. `frontend/src/app/profile/sellers/dashboard/page.tsx`
   - route: `/profile/sellers/dashboard`.

## Проверка live API

Команды выполнялись из `/workspace/glame-platform`.

### API health

`python /workspace/tools/glame_api.py get /health`

Результат: `HTTP 200 OK`, `{"status":"healthy"}`.

### Главный KPI dashboard, май 2026

`python /workspace/tools/glame_api.py get '/api/admin/1c/sellers/kpi/dashboard?month=2026-05'`

Результат: `HTTP 200 OK`.

Сводка payload:

```json
{
  "success": true,
  "month": "2026-05-01",
  "totals": {
    "revenue": 2122512.05,
    "revenue_plan": 4569987.52,
    "completion_percent": 46.44,
    "forecast_revenue": 2193262.45,
    "forecast_percent": 47.99,
    "checks": 158,
    "items_sold": 264.0,
    "shifts_count": 84,
    "avg_check": 13433.62,
    "avg_item_price": 8039.82,
    "items_per_check": 1.67,
    "avg_sales_per_shift": 25268.0
  },
  "stores_count": 2,
  "stores": [
    ["Ялта, Набережная 18", 2854371.52, 52.22, "critical"],
    ["ТРК Центрум", 1715616.0, 36.84, "critical"]
  ],
  "sellers_count": 7,
  "metric_matrix_count": 2,
  "data_quality": {
    "duplicate_store_rows": 0,
    "seller_field_status": "ok",
    "unmatched_sellers": 0
  },
  "insights_count": 10
}
```

Вывод: план Ялты и Центрума не смешан в текущем dashboard endpoint; оба магазина видны отдельными строками с отдельными планами.

### Detailed sales endpoint

Первичная проверка live endpoint до backend restart/redeploy ещё отдавала sample без seller fields:

`GET /api/analytics/1c-sales/details?period=month&limit=3`

Live sample keys: `product_name`, `quantity`, `store_name`.

Кодовая правка для seller fields внесена в `backend/app/api/analytics.py`, но live backend нужно перезапустить/redeploy, затем повторить проверку.

После статических проверок API bridge начал отдавать `502 Bad Gateway` на `/health` и login; backend на `172.17.0.1:8000` из контейнера не отвечает. Код синтаксически проверен, но live-проверку seller fields нужно делать после восстановления/restart backend.

## Static verification

Успешно:

```bash
python -m py_compile backend/app/api/analytics.py backend/app/services/seller_kpi_service.py backend/app/api/admin/onec_customers.py
cd frontend && npx eslint src/components/profile/SellerKpiMainDashboard.tsx --max-warnings=0
cd frontend && npx tsc --noEmit --pretty false
```

## Что проверить Анатолию перед deploy/merge

1. Подтвердить, что route `/profile/sellers/dashboard` доступен только admin/manager через текущий layout/access gate. Seller не должен видеть общий dashboard.
2. Перезапустить/redeploy backend и повторить:
   ```bash
   python /workspace/tools/glame_api.py get '/api/admin/1c/sellers/kpi/dashboard?month=2026-05'
   python /workspace/tools/glame_api.py get '/api/analytics/1c-sales/details?period=month&limit=3'
   ```
3. В detailed sales строках должны быть seller поля:
   `seller_id`, `seller_external_id`, `seller_name`, `seller_match_status`, `check_id`, `document_id`.
4. Если seller fields отсутствуют в live data — dashboard должен показывать data warning и не делать персональные выводы.
5. Проверить май 2026 вручную в UI: Ялта и ТРК Центрум отдельными карточками; для каждого плана виден магазин/период/status сопоставления.

## Риск / замечание

В репозитории уже был большой dirty tree до этой задачи. Я не делал broad cleanup и не трогал unrelated files. Для review лучше смотреть целевые файлы seller KPI/dashboard и `backend/app/api/analytics.py`.
