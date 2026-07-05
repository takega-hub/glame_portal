Ежедневный маркетинговый анализ GLAME — read-only report
Проверено: 2026-05-28 09:14:52 UTC
Платформенная задача: 19a200b8-0628-4f2e-87cd-1ab123e2dfd9 / Ежедневный маркетинговый анализ
Hermes Kanban: t_fb532c8b

1. Итог
- Отчет собран вручную по реальным read-only данным GLAME API; массовых рассылок, кампаний, customer outreach и API-записей не выполнялось.
- Платформенная cron-задача на момент проверки: status=pending, started_at=None, completed_at=None, output_data=None; audit events=1, handoffs=0.
- Точный операционный блокер сохраняется: cron-scheduler создал pending task, но analytics-agent/processor не забрал задачу в started/processing. Это не блокер данных: ключевые read-only источники ниже отвечают 200 OK.

2. Продажи и трафик
- Сегодня (2026-05-28): revenue=0, orders=0, items_sold=0 — на момент проверки продаж за сегодня в daily endpoint нет.
- Вчера (2026-05-27): revenue=37 569, orders=5, items_sold=23.0.
- Неделя: revenue=142 049, orders=14, items=21, AOV=10 146, visitors=277, revenue/visitor=513.
- По магазинам за неделю: Ялта, Набережная 18: 53 726 / 6 заказов / 28 items; ТРК Центрум: 88 323 / 8 заказов / 42 items.
- Store visits за 2026-05-21..2026-05-28: 550 посетителей против 743 в сравнительном периоде, change=-193 (-25.98%); магазины в источнике: CENTRUM, YALTA.
- Website visits за доступные дни недели: 87 визитов, 77 пользователей; максимум 2026-05-26: 24 визита / 21 пользователь, 2026-05-27: 14 / 12.
- Каналы за 30 дней: API видит только channel=offline — revenue=2 199 324, orders=800, unique_customers=88, unique_products=221; последняя неделя revenue=142 049 против первой 384 183, growth=-63.0%.

3. Клиенты и сегменты
- Клиентская база: total_customers=6216, total_ltv=66 007 133, average_ltv=10 619.
- Churn risk: high=5489 (88.3%), medium=303, low=424.
- RFM низкая зона score 3–5: 5425 клиентов (87.3%).
- Крупнейшие opportunities: 5489 VIP клиентов не покупали 90+ дней - возможна программа реактивации (potential_revenue=27 445 000; actions=Специальные скидки, Персональные предложения).
- Ключевые сегменты: Лояльные покупатели=595, Экономные покупатели=836, Потенциально ценные=836, Больше 2000 бонусов=16, Больше 50 000=92, Активные=434, Спящие=855, Новые клиенты=418.

4. Товары/категории/бренды за 30 дней
- Топ категории по revenue: Серьги: 606 390; Кольца: 385 673; Браслеты: 346 252; Кулоны: 252 849; Колье: 230 885
- Топ бренды по revenue: Raganella Princess: 394 004; PEARL: 245 354; Kalliope: 237 083; UNOde50: 213 305; GEOMETRY: 162 071
- Топ SKU: Kalliope / Серьги / KL02202055/1-G (102 164); Raganella Princess / Кулоны / RP01856-S (74 523); Kalliope / Серьги / KL02202040-G (51 874); UNOde50 / Кулоны / U10084-G (49 980); Kalliope / Кольца / KL02201039-G (47 418).

5. Рекомендации без write-действий
- Не запускать массовую реактивацию автоматически: high-risk база очень большая, а требования задачи запрещают mass send без admin approval.
- Для директора/админа: проверить, нормален ли ноль продаж за текущий день на момент утренней синхронизации; вчерашний и недельный срезы подтверждают, что историческая 1С-аналитика доступна.
- Для маркетинга: подготовить, но не отправлять, реактивационный сегмент high-risk/спящие с персональными офферами; креативы привязать к категориям/брендам из топа за 30 дней.
- Для платформы: исправить или включить consumer/worker analytics-agent для /api/agent-interactions/tasks, потому что cron-задача остается pending без started_at и handoff/output.

6. Sources used / verification notes
- GET /health → HTTP 200 OK
- GET /api/agent-interactions/tasks/19a200b8-0628-4f2e-87cd-1ab123e2dfd9 → HTTP 200 OK
- GET /api/agent-interactions/tasks/19a200b8-0628-4f2e-87cd-1ab123e2dfd9/logs → HTTP 200 OK
- GET /api/agent-interactions/tasks/19a200b8-0628-4f2e-87cd-1ab123e2dfd9/audit → HTTP 200 OK
- GET /api/agent-interactions/tasks?target_agent=analytics-agent&limit=50 → HTTP 200 OK
- GET /api/director/tasks/kanban?limit=200 → HTTP 200 OK
- GET /api/ai-marketer/dashboard → HTTP 200 OK
- GET /api/marketing/ai-marketer/dashboard → HTTP 200 OK
- GET /api/ai-marketer/opportunities → HTTP 200 OK
- GET /api/ai-marketer/segments/analysis → HTTP 200 OK
- GET /api/admin/customers/analytics/overview → HTTP 200 OK
- GET /api/admin/customers/segments/list → HTTP 200 OK
- GET /api/analytics/dashboard?days=30 → HTTP 200 OK
- GET /api/analytics/1c-sales/daily?period=today&auto_sync=false → HTTP 200 OK
- GET /api/analytics/1c-sales/daily?period=yesterday&auto_sync=false → HTTP 200 OK
- GET /api/analytics/1c-sales/metrics?period=week&auto_sync=false → HTTP 200 OK
- GET /api/analytics/products/top-sellers?period=30d&limit=10 → HTTP 200 OK
- GET /api/analytics/products/by-category?period=30d&limit=10 → HTTP 200 OK
- GET /api/analytics/products/by-brand?period=30d&limit=10 → HTTP 200 OK
- GET /api/analytics/channels/performance?period=30d → HTTP 200 OK
- GET /api/analytics/website-visits/daily?days=7 → HTTP 200 OK
- GET /api/analytics/store-visits/daily?days=7 → HTTP 200 OK
- Raw JSON artifact: /workspace/glame-platform/reports/daily_marketing_analysis_t_fb532c8b_20260528_091452.json
- Read-only guarantee: использовались только GET-запросы к GLAME API; endpoints с auto_sync вызваны с auto_sync=false; POST/PUT/PATCH/DELETE не выполнялись.
