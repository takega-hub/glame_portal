# GLAME AI Platform Boards — Implementation Plan

Дата сверки: 2026-05-21

## 1. Что уже реализовано

### Data layer
- 1C catalog/products: CommerceML XML import.
- Остатки: `product_stocks`, синхронизация из `offers.xml`.
- Продажи/чеки: `sales_records`, 1C OData sync.
- Покупатели: `users`, `purchase_history`, sync дисконтных карт и покупок.
- Посещения: `store_visits`, FTP/nightly sync.
- CRM сегменты: `customer_segments`, `user_segments`.
- Контент: `content_plans`, `content_items`, публикации, медиа.
- Агентские задачи: `agent_interaction_tasks`, logs, validation, queue/process/cancel/delete.

### API layer
- `/api/ai-marketer/dashboard`
- `/api/agent-interactions/tasks`
- `/api/agent-interactions/tasks/{id}/approve`
- `/api/agent-interactions/tasks/{id}/reject`
- `/api/agent-interactions/tasks/{id}/revise`
- `/api/inventory/dashboard`
- `/api/inventory/report`
- `/api/inventory/order`
- `/api/inventory/clearance`
- `/api/inventory/assortment`
- `/api/inventory/marketing-link`
- `/api/analytics/*`
- `/api/content/*`
- `/api/customer-segmentation/*`

### Frontend layer
- Main AI Marketing Director overview with live board cards.
- Marketing Command Board connected to real tasks, approvals, inventory, CRM and traffic data.
- Task list and task detail pages.
- Task creation with extended board fields from ТЗ:
  - priority
  - deadline
  - risk level
  - campaign
  - city
  - DNA
  - channel/platform
  - assigned human
  - expected result
  - attachments

## 2. Частично реализовано

### Global task object
Current implementation uses `agent_interaction_tasks` as the source of truth.

Covered:
- task id
- status
- priority
- assigned agent
- deadline
- input data
- context
- validation
- output
- logs
- approval actions

Still stored mostly inside JSON:
- title
- description
- campaign
- city
- DNA
- assigned human
- attachments
- result / next step
- analytics

Next step: keep JSON flexibility for MVP, then promote high-use fields to DB columns only after patterns stabilize.

### Approval UI
Covered:
- approve
- reject
- revise
- risk display
- requesting agent
- deadline

Missing:
- comments history visible in UI
- escalation warning UI
- approval preview per content/CRM/campaign object

### Command Board
Covered:
- priority strip
- agent status grid
- approval queue
- analytics snapshot
- weekly focus from live tasks
- export report

Missing:
- operational timeline today/tomorrow/7 days
- system health panel
- anomaly detection beyond current task/data status

## 3. Missing by board

### Content Board
Needs:
- calendar view day/week/month/campaign
- production pipeline columns from ТЗ
- filters: media layer, content type, city mood, DNA
- content card actions:
  - duplicate
  - attach assets
  - attach references
  - create production task
  - send to approval
  - connect to CRM
  - connect to campaign
  - archive
  - compare performance

Existing base:
- `content_plans`
- `content_items`
- `/api/content/*`

### Personal Media Board
Needs:
- viral opportunities
- authority layer
- bridge to GLAME
- personal storylines

Recommended source:
- agent tasks with `media_layer=personal`
- future social metrics
- content items tagged personal.

### CRM Board
Needs:
- segment dashboard
- CRM flow pipeline
- return flow tracker
- CRM performance layer

Existing base:
- customer segments
- communication agent
- customer messages
- purchase history
- churn/RFM analytics.

### Partnership Board
Needs:
- partnership/collab data model
- partner pipeline
- partner categories
- collab content tracker
- outcome analytics.

### Traffic/Growth Board
Needs:
- active growth campaigns
- amplification recommendations
- app return layer
- budget/KPI tracking.

Existing base:
- analytics channels
- Yandex Metrika
- store visits
- sales metrics.

### Product Focus Board
Needs:
- product focus strip
- styling combination layer
- city availability layer
- product-card links to content/CRM/campaign.

Existing base:
- `/api/inventory/marketing-link`
- `/api/inventory/clearance`
- `/api/inventory/order`
- product/catalog/stock/sales tables.

### Analytics Board
Needs:
- unified executive dashboard
- cross-system correlations
- alerts layer
- AI recommendation layer.

Existing base:
- `/api/analytics/unified`
- product analytics
- inventory analytics
- channel analytics
- store visits.

## 4. Recommended implementation sequence

### Phase 1 — Board Operating Foundation
1. Finish global task UI actions everywhere:
   - approve
   - reject
   - revise
   - queue
   - process
   - cancel
   - delete
2. Add visible task fields to task detail:
   - campaign
   - city
   - DNA
   - attachments
   - expected result
   - result
   - next step
3. Add operational timeline API and UI:
   - today
   - tomorrow
   - next 7 days.

### Phase 2 — Content Board
1. Convert Content Board from demo/static view to `content_plans` + `content_items`.
2. Add production pipeline statuses from ТЗ.
3. Implement content card actions:
   - duplicate
   - attach assets
   - send to approval
   - publish/measure status.

### Phase 3 — CRM Board
1. Connect CRM Board to customer segments and communication generations.
2. Add return-flow tracker:
   - inactive customers
   - VIP reminders
   - saved selections
   - event reminders.
3. Add CRM performance placeholders first, then real metrics as sends/clicks arrive.

### Phase 4 — Product + Traffic + Analytics Boards
1. Product Focus Board: connect inventory marketing-link, clearance, order recommendations.
2. Traffic Board: connect store visits, website visits, sales by source.
3. Analytics Board: add unified snapshot and alerts.

### Phase 5 — New Data Models
Add only after Phase 1/2 proves the data shape:
- `board_events` for timeline items across boards.
- `board_approvals` if approval needs object-level history outside task logs.
- `partnerships` for PR/collab pipeline.
- `growth_campaigns` for paid/amplification tracking.
- `board_alerts` for anomaly/system-health layer.

## 5. Immediate next implementation tasks

1. Task detail page: show and edit new task fields.
2. Command Board: add Operational Timeline.
3. Content Board: replace static content with real content plan/items.
4. CRM Board: connect segment dashboard and CRM task pipeline.
5. Product Board: connect inventory marketing-link and reorder/clearance data.
