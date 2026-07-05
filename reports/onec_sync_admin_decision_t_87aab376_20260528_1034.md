# Проверка устаревания синхронизации 1C — t_87aab376

Время проверки (UTC): 2026-05-28T10:34:24Z
Режим: read-only, без массовых рассылок и без запуска sync.
Platform task id: c6d56e55-1eed-4fc2-84eb-334519ff1994

## Решение для админа/директора

Нарушение freshness 1C подтверждено повторной live API проверкой. Текущий статус нельзя считать resolved: customer sync не обновлялся ~50.11 часов, продажи/чеки за 2026-05-28 не подтверждены, а inventory analytics продолжает работать через live fallback.

Рекомендуемое действие: не запускать CRM/массовые действия, которые зависят от свежести 1C, пока админ/директор явно не выберет один из вариантов:

1. Перезапустить/починить customer sync, sales/checks sync и плановый пересчёт inventory analytics.
2. Либо явно принять текущее stale/fallback состояние на сегодня и зафиксировать, какие решения можно принимать на этих данных.

## Повторно проверенные источники

- GET /health → HTTP 200, status=healthy.
- GET /api/admin/1c/sync/status → HTTP 200, active_tasks=0, errors=[], last_sync=2026-05-26T08:27:30.235770+00:00, total_customers=6216.
- GET /api/auth/onec-sync-status → HTTP 200, status=null, job_id=null, last_attempt_at=null, attempts=0.
- GET /api/analytics/1c-sales/daily?days=7&auto_sync=false → HTTP 200; latest non-zero date=2026-05-27; 2026-05-28: orders=0, revenue=0.
- GET /api/analytics/1c-sales/metrics?days=7&auto_sync=false → HTTP 200; total_orders=35, total_revenue=428065.0, latest metric date=2026-05-27.
- GET /api/inventory/dashboard → HTTP 200; stock.total_stock=5708.0, stock.sku_count=634, sales.checks_count=604, sales.revenue=6312924.19.
- GET /api/analytics/inventory/health-score → HTTP 200; status=poor, health_score=30.44, source=live_inventory_control_fallback, stock_total=5708.0, total_products=3357.
- GET /api/analytics/inventory/analysis?limit=5 → HTTP 200; status=success, records returned from source=live_inventory_control_fallback.
- GET /api/products/sync-1c/status → HTTP 404; no active product sync tasks; API suggests POST /api/products/sync-xml.

## Факты

- Live API доступен и отвечает.
- Customer sync не свежий: last_sync=2026-05-26T08:27:30.235770+00:00, возраст на момент проверки ≈ 50.11 часов.
- Активных customer sync задач нет.
- 1C auth sync job не запущен: job_id=null, status=null, last_attempt_at=null.
- Sales/checks за текущий день не подтверждены: 2026-05-28 orders=0, revenue=0; последние ненулевые продажи в daily API — 2026-05-27.
- Inventory dashboard видит live stock, но analytics/health-score помечает source=live_inventory_control_fallback; это означает, что derived/scheduled analytics freshness всё ещё не подтверждён.
- Product sync status возвращает 404 и сообщает, что нет активных задач синхронизации товаров.

## Статус

Задачу следует держать в Review/Blocked до админского решения. Done/Готово преждевременно, потому что verified resolution или явного принятия stale/fallback состояния нет.
