# Контроль синхронизации 1С — 2026-05-28 10:05 UTC

Задача: t_edbb0e9b / GLAME platform task 35a0e2bf-ae46-48fd-8820-94fae2cd5d20

## Итог

Статус: требует внимания администратора / директора.

Live API доступен, критичного 500 на `/api/admin/1c/sync/status` нет. Данные продаж, остатков и покупателей читаются, но регламент свежести 60 минут не выполняется по нескольким источникам:

- Покупатели: `/api/admin/1c/sync/status` показывает `last_sync=2026-05-26T08:27:30.235770+00:00`, что старше 49 часов на момент проверки 2026-05-28 10:05 UTC.
- Продажи/чеки: `/api/analytics/1c-sales/daily?days=7&auto_sync=false` возвращает последнюю ненулевую дату 2026-05-27; за 2026-05-28 сейчас 0 заказов / 0 выручки. Это может быть нормой для начала дня, но по регламенту hourly-фрешнесса нет подтверждения обновления за последний час.
- Остатки: `/api/inventory/dashboard` возвращает live stock `total_stock=5708`, `sku_count=634`; `/api/analytics/inventory/health-score` и `/api/analytics/inventory/analysis` работают через `source=live_inventory_control_fallback`, то есть аналитический fallback живой, но не подтверждает штатный пересчёт/синхронизацию аналитической витрины.
- `/api/products/sync-1c/status` возвращает 404 `Нет активных задач синхронизации товаров`, то есть активной синхронизации товаров/остатков сейчас нет.

Рекомендация: не запускать массовых рассылок/CRM-действий на основании этого мониторинга. Передать администратору на проверку расписаний 1С sync/recalculate: customer sync, sales/checks sync и stock/inventory analytics recalculation.

## Проверенные источники

1. `GET /health` → HTTP 200, `status=healthy`.
2. `GET /api/admin/1c/sync/status` → HTTP 200, `active_tasks=0`, `errors=[]`, `last_sync=2026-05-26T08:27:30.235770+00:00`, `total_customers=6216`.
3. `GET /api/analytics/1c-sales/metrics?days=7&auto_sync=false` → HTTP 200, `total=6`, `total_orders=35`, `total_revenue=428065.0`, период до 2026-05-28 10:05 UTC; последние метрики есть за 2026-05-27.
4. `GET /api/analytics/1c-sales/daily?days=7&auto_sync=false` → HTTP 200, строки 2026-05-21..2026-05-28; 2026-05-28 = 0 заказов / 0 выручки.
5. `GET /api/analytics/1c-sales/daily-sources?days=7&dimension=store` → HTTP 200; по магазинам Ялта и ТРК Центрум есть данные до 2026-05-27, 2026-05-28 пусто.
6. `GET /api/inventory/dashboard` → HTTP 200, `stock.total_stock=5708.0`, `stock.sku_count=634`, `sales.checks_count=604`, `sales.revenue=6312924.19`.
7. `GET /api/analytics/inventory/health-score` → HTTP 200, `status=excellent`, `metrics.source=live_inventory_control_fallback`, `stock_total=5708.0`, `total_products=3357`.
8. `GET /api/analytics/inventory/analysis?limit=5` → HTTP 200, `status=success`, `source=live_inventory_control_fallback` в строках анализа.
9. `GET /api/admin/customers/analytics/overview` → HTTP 200, `total_customers=6216`, `total_revenue=66007132.58`.
10. `GET /api/products/sync-1c/status` → HTTP 404, нет активных задач синхронизации товаров.
11. `GET /api/auth/onec-sync-status` → HTTP 200, `status=null`, `job_id=null`, `last_attempt_at=null`.

## Вывод по источникам из задачи

- `1c_sales`: readable, stale/suspicious for hourly freshness; latest non-zero sales day is 2026-05-27, current day is zero at 10:05 UTC.
- `1c_stock`: readable via live inventory/dashboard and fallback analytics; active product/stock sync is not running; derived inventory analytics appears to rely on fallback.
- `1c_customers`: readable, but admin sync status last customer sync is stale (`2026-05-26T08:27:30Z`).

## Что передать администратору

Проверить, почему 1C customer sync не обновлялся после 2026-05-26 08:27 UTC, почему на момент 2026-05-28 10:05 UTC нет подтвержденных сегодняшних продаж/чеков в 1C analytics, и должен ли stock/inventory analytics работать через `live_inventory_control_fallback` вместо штатной пересчитанной витрины.
