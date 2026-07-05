# Решение для админа/директора: устаревание синхронизации 1С

Задача Hermes Kanban: `t_87aab376`
GLAME platform task: `c6d56e55-1eed-4fc2-84eb-334519ff1994`
Время повторной проверки: `2026-05-28T10:18:14Z`

## Короткий вывод

Инцидент подтверждён повторной read-only проверкой live API: backend здоров, 1C-facing endpoints читаются, но регламент hourly freshness не выполняется.

Рекомендуемое решение: держать задачу в Review/Blocked до решения администратора/директора. Не запускать массовые рассылки или CRM-действия, зависящие от свежести 1С, пока не подтверждён перезапуск/исправление расписаний либо явное принятие текущего состояния.

## Подтверждённые факты

1. `GET /health` → `status=healthy`.
2. `GET /api/admin/1c/sync/status` → `last_sync=2026-05-26T08:27:30.235770+00:00`, `active_tasks=0`, `errors=[]`, `total_customers=6216`.
   - На момент повторной проверки это примерно `49.85` часа без подтверждённого customer sync.
3. `GET /api/analytics/1c-sales/daily?days=7&auto_sync=false` → 2026-05-28: `orders=0`, `revenue=0`; latest non-zero day: 2026-05-27.
4. `GET /api/analytics/1c-sales/metrics?days=7&auto_sync=false` → latest metric date: 2026-05-27.
5. `GET /api/inventory/dashboard` → live stock читается: `total_stock=5708.0`, `sku_count=634`, `checks_count=604`, `sales_revenue=6312924.19`.
6. `GET /api/analytics/inventory/health-score` → `status=excellent`, но `source=live_inventory_control_fallback`, `stock_total=5708.0`, `total_products=3357`.
7. `GET /api/analytics/inventory/analysis?limit=5` → `status=success`, но source в строках анализа: `live_inventory_control_fallback`.
8. `GET /api/products/sync-1c/status` → 404 с текстом: нет активных задач синхронизации товаров; запустить через `POST /api/products/sync-xml`.
9. `GET /api/auth/onec-sync-status` → `status=null`, `job_id=null`, `last_attempt_at=null`.

## Что должен подтвердить админ/директор

1. Почему customer sync не обновлялся после `2026-05-26T08:27:30Z`.
2. Почему нет подтверждённых продаж/чеков за `2026-05-28` в 1C sales analytics на момент проверки.
3. Должна ли inventory analytics сейчас работать через `live_inventory_control_fallback`, или нужно восстановить штатный пересчёт/витрину.
4. Какое решение принять:
   - A. Перезапустить/исправить расписания customer sync, sales/checks sync и inventory analytics recalculation, затем повторить мониторинг.
   - B. Явно принять текущее состояние как допустимое на сегодня, указав причину, почему freshness >49 часов и fallback inventory analytics не блокируют действия.

## Ограничения

- Массовые отправки не запускались.
- Данные проверялись read-only через GLAME API.
- Секреты/токены не выводились.
