# Передача Анатолию: дашборд магазинов и продавцов с корректными планами

Задача: t_771030c7 / GLAME Platform 2982bd02-1759-48a2-8772-b270fcea4351
Дата проверки: 2026-05-30

## Что проверено

1. Backend доступен через GLAME API bridge: `/health` вернул `200 OK`.
2. Локальный код содержит управленческий KPI dashboard:
   - `GET /api/admin/1c/sellers/kpi/dashboard?month=2026-05`
   - `GET /api/admin/1c/sellers/kpi?month=2026-05&store_name=...`
   - `GET /api/admin/1c/sellers/kpi/targets`
   - `GET /api/admin/1c/sellers/shifts`
3. Майские планы по магазинам в live API не смешиваются:
   - Ялта, Набережная 18: план 2 854 371.52, выполнение 52.22%
   - ТРК Центрум: план 1 715 616.00, выполнение 36.84%
4. Личные планы продавцов считаются по правилу Excel: `план магазина × часы продавца / часы магазина`, источник в строке: `plan_source=excel_formula_hours_share`.
5. Доля несопоставленных продавцов в seller KPI dashboard сейчас `0`, `seller_field_status=ok`.

## Что исправлено в рабочей копии

Файл: `backend/app/api/analytics.py`

В endpoint `GET /api/analytics/1c-sales/details` добавлен явный блок качества сопоставления продавца:

- `seller_id`
- `seller_external_id`
- `seller_name`
- `seller_match_status`
- `seller_unmatched`
- `seller_match_summary`
- `data_warnings[]`, если в строках продаж нет seller data

Важно: live backend на момент проверки всё ещё отдаёт `/api/analytics/1c-sales/details` без seller-полей, то есть running service, вероятно, не перезапущен/не поднят с текущей рабочей копии.

## Проверка

Команды выполнены в `/workspace/glame-platform`:

```bash
python -m py_compile backend/app/api/analytics.py backend/app/services/seller_kpi_service.py
cd frontend && npx tsc --noEmit --pretty false
cd frontend && npx eslint src/components/profile/SellerKpiMainDashboard.tsx src/components/profile/ProfileSellersPage.tsx src/components/profile/SellerPersonalKpiPage.tsx src/components/analytics/SalesPanel.tsx
```

Результат:

- `py_compile`: OK
- `tsc`: OK
- `eslint`: 0 errors, 1 existing warning in `SalesPanel.tsx` про dependencies `fetchMetrics`/`fetchSalesDetails`

## Риск / что нужно сделать Анатолию

1. Посмотреть diff, потому что рабочая копия репозитория уже содержит много несвязанных изменений; коммитить всё целиком нельзя.
2. Аккуратно выделить релевантные изменения:
   - `backend/app/api/analytics.py`
   - `backend/app/services/seller_kpi_service.py`
   - `backend/app/api/admin/onec_customers.py`
   - `frontend/src/components/profile/SellerKpiMainDashboard.tsx`
   - `frontend/src/components/profile/ProfileSellersPage.tsx`
   - `frontend/src/components/profile/SellerPersonalKpiPage.tsx`
   - `frontend/src/lib/api.ts`
   - при необходимости `frontend/src/components/analytics/SalesPanel.tsx`
3. После review/rebuild backend повторить live checks:

```bash
python /workspace/tools/glame_api.py get '/api/admin/1c/sellers/kpi/dashboard?month=2026-05'
python /workspace/tools/glame_api.py get '/api/admin/1c/sellers/kpi?month=2026-05&store_name=%D0%A2%D0%A0%D0%9A%20%D0%A6%D0%B5%D0%BD%D1%82%D1%80%D1%83%D0%BC'
python /workspace/tools/glame_api.py get '/api/analytics/1c-sales/details?period=month&limit=5'
```

Acceptance gate after deploy:

- Ялта and Центрум have separate visible plan source/store/period/status.
- If Центрум plan is missing/not confirmed, UI shows warning and does not show false overperformance.
- Detail sales rows include seller fields or `seller_unmatched=true` + `data_warnings`.
- Dashboard does not make personal conclusions from unmatched sales.
