# Передача Анатолию: дашборд магазинов и продавцов с корректными планами

Дата: 2026-05-30T17:38:45+00:00
Kanban: t_771030c7
Platform task: 2982bd02-1759-48a2-8772-b270fcea4351
Запрос от: Елена
Получатель: Анатолий

## Главное

Нужно довести управленческий дашборд магазинов и продавцов до состояния, где Елена не может перепутать план Ялты и Центрума, а персональные выводы по продавцам строятся только при наличии seller data.

Критичная бизнес-правка: ссылка Яндекс.Диска из исходной задачи относится к Ялте, не к ТРК Центрум. Нельзя использовать её как план Центрума.

## Что проверено в коде

1. Backend/API:
   - `backend/app/api/admin/onec_customers.py`
     - `GET /api/admin/1c/sellers/kpi/dashboard`
     - `GET /api/admin/1c/sellers/kpi`
     - `GET /api/admin/1c/sellers/kpi/targets`
     - `PUT /api/admin/1c/sellers/kpi/targets`
     - `GET /api/admin/1c/sellers/shifts`
   - `backend/app/services/seller_kpi_service.py`
     - считает KPI по продавцам из `sales_records.raw_data` через поля `Продавец_Key`, `Сотрудник_Key`, `Кассир_Key`, `Ответственный_Key`, `Менеджер_Key`;
     - хранит ручные планы в `seller_kpi_target_plans`;
     - формирует `data_quality.seller_field_status`, `data_quality.unmatched_sellers`, store/seller rows, прогнозы и insights.
   - `backend/app/api/analytics.py`
     - `GET /api/analytics/1c-sales/details` до текущей правки не отдавал seller-поля в детальных продажах.

2. Frontend:
   - `frontend/src/components/profile/SellerKpiMainDashboard.tsx` — главный дашборд магазинов/продавцов.
   - `frontend/src/lib/api.ts` — типы и методы `getSellerKpiDashboard`, `getSellerKpi`, `getSellerKpiTargets`, `saveSellerKpiTargets`, `getSellerShifts`.

## Live API проверка

Проверено через `/workspace/tools/glame_api.py`:

- `GET /health` → HTTP 200 OK.
- `GET /api/admin/1c/sellers/kpi/dashboard?month=2026-05` → HTTP 200 OK.
- `GET /api/analytics/1c-sales/details?period=month&limit=3` → HTTP 200 OK.

Live KPI dashboard за май 2026 возвращает:

- `data_quality.seller_field_status = ok`
- `data_quality.unmatched_sellers = 0`
- магазины:
  - Ялта, Набережная 18: факт 1 490 561.95, план 2 854 371.52, выполнение 52.22%, прогноз 53.96%, чеки 101, изделия 183, продавцов 3.
  - ТРК Центрум: факт 631 950.10, план 1 715 616.00, выполнение 36.84%, прогноз 38.06%, чеки 57, изделия 81, продавцов 4.

Важно: эти цифры показывают, что backend уже умеет различать Ялту и Центрум в KPI dashboard. Но источник планов должен быть явно видим в интерфейсе, иначе бизнес-риск остаётся.

## Найденный технический разрыв

`GET /api/analytics/1c-sales/details` в live backend сейчас отдаёт строки продаж без seller fields. В ответе есть:

- `id`
- `sale_date`
- `product_name`
- `product_article`
- `product_brand`
- `product_category`
- `quantity`
- `revenue`
- `store_id`
- `store_name`
- `channel`
- `external_id`

Но нет:

- `seller_id`
- `seller_external_id`
- `seller_name`
- `check_id/document_id`
- `seller_match_status`

Это нарушает acceptance criteria для детальных продаж и мешает диагностике доли «Не сопоставлено с продавцом».

## Локальная правка, которую надо ревьюить и задеплоить

В `backend/app/api/analytics.py` исправлен `GET /api/analytics/1c-sales/details`:

- select теперь берёт `SalesRecord.document_id` и `SalesRecord.raw_data`;
- seller fields извлекаются из `raw_data` по 1C-кандидатам:
  - `Продавец_Key`
  - `Сотрудник_Key`
  - `Кассир_Key`
  - `Ответственный_Key`
  - `Менеджер_Key`
  - `Продавец`, `Сотрудник`, `Кассир`, `Ответственный`, `Менеджер`
- каждая строка продаж получает:
  - `document_id`
  - `check_id`
  - `seller_id`
  - `seller_external_id`
  - `seller_name`
  - `seller_unmatched`
  - `seller_match_status`
- ответ получает блок:
  - `seller_matching.page_unmatched`
  - `seller_matching.page_total`
  - `seller_matching.page_unmatched_share`
  - `seller_matching.status`

Проверка синтаксиса прошла:

```bash
python -m py_compile backend/app/api/analytics.py backend/app/api/admin/onec_customers.py backend/app/services/seller_kpi_service.py
```

## Что нужно сделать Анатолию

1. Review локальной правки в `backend/app/api/analytics.py`.
2. Проверить, что нет конфликта с другими незакоммиченными изменениями в репозитории: workspace сильно dirty, поэтому коммитить без ручного ревью нельзя.
3. После review/redeploy проверить live endpoint:

```bash
python /workspace/tools/glame_api.py get '/api/analytics/1c-sales/details?period=month&limit=5'
```

Ожидаемо в каждой строке должны появиться seller/check fields и общий блок `seller_matching`.

4. В UI дашборда добавить/проверить явную маркировку источника плана для каждого магазина:
   - источник;
   - период;
   - магазин;
   - статус сопоставления (`confirmed`, `missing`, `ambiguous`, `not_loaded`).

5. Для Центрума: если отдельный подтверждённый план не загружен, UI должен показывать warning и не считать ложное перевыполнение/невыполнение на основании плана Ялты.

6. В дашборде отдельно показывать долю `seller_unmatched` / «Не сопоставлено с продавцом». Если seller data отсутствует или доля выше целевого порога, блокировать персональные выводы по продавцам и показывать data-warning.

## Acceptance checklist

- [ ] План Ялты и Центрума невозможно перепутать.
- [ ] Для каждого плана виден источник, период, магазин, статус сопоставления.
- [ ] Если план Центрума не загружен/не подтверждён — warning, без ложного выполнения.
- [ ] Доля «Не сопоставлено с продавцом» видна отдельно.
- [ ] Детальные продажи отдают seller/check/product/store/date/amount/quantity fields.
- [ ] При отсутствии seller data dashboard показывает data-warning и не делает персональных выводов.

## Риск

Задачу нельзя закрывать как Done до review и live verification: локальный файл поправлен и компилируется, но running backend ещё отдаёт старую форму details endpoint без seller fields.
