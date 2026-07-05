# GLAME product-доска — обновление данных заблокировано

Задача Kanban: `t_ae0795a9`
Platform task: `4c66355e-32d8-4f7f-b85f-f64e0c2ca48a`

## Что проверено

- Рабочая директория в контейнере: `/workspace/glame-platform`.
- GLAME API helper доступен: `/workspace/tools/glame_api.py`.
- На старте `/health` через helper один раз вернул `HTTP 200 OK` / `healthy`.
- При попытке собрать полный snapshot для product-доски backend/proxy стабильно начал возвращать `HTTP 502 Bad Gateway` на `http://172.17.0.1:18000/health`.
- Проверены альтернативные адреса из контейнера:
  - `http://172.17.0.1:18000/health` → `502 Bad Gateway`
  - `http://172.17.0.1:8000/health` → connection refused
  - `http://127.0.0.1:8000/health` → connection refused
  - `host.docker.internal` → не резолвится
- Выполнено 6 повторных попыток с паузой 10 секунд; все вернули `502 Bad Gateway`.

## Почему не закрываю как Done

Задача требует обновить данные по product-доске и зафиксировать изменения. Без живого API нельзя верифицированно обновить данные по:

- `/api/inventory/dashboard`
- `/api/inventory/marketing-link`
- `/api/inventory/order`
- `/api/inventory/clearance`
- `/api/analytics/inventory/website-priority`
- `/api/analytics/products/top-sellers`
- `/api/marketing/campaigns`

В репозитории есть предыдущий snapshot/отчёт по похожей задаче (`product_focus_t_dd8d52cd`), но использовать его как свежий результат нельзя — это было бы не verified update.

## Следующий шаг

Нужно восстановить доступность GLAME backend/nginx bridge (`172.17.0.1:18000`) или дать альтернативный доступ к API. После этого задача должна быть перезапущена: собрать свежий snapshot, сравнить с предыдущим product refresh, записать отчёт и handoff в platform task chat.
