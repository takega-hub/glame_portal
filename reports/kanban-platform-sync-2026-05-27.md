# GLAME Kanban ↔ platform AI tasks sync

Generated: 2026-05-27T09:12:09+00:00
Scope: read-only sync of GLAME platform task APIs and Hermes Kanban. No GLAME API writes were performed.

## Sources checked

- `GET /health` → healthy
- `GET /api/auth/me` → authenticated as admin service user; credentials present and redacted
- `GET /api/agent-interactions/tasks` → 3 platform agent tasks
- `GET /api/director/tasks/kanban` → director board: todo 2, in_progress 0, done 1, blocked 0
- `GET /api/marketing/ai-marketer/dashboard` → active_tasks 0, completed_today 0, pending_approvals 0, tomorrow_plan_ready false
- `GET /api/ai-marketer/dashboard` → customer/segment dashboard available; PII not copied into this report
- `GET /api/ai-marketer/opportunities` → 1 re-engagement opportunity
- Local Hermes Kanban DB read-only query for current `GLAME%` cards

## Platform task state

### Pending on GLAME platform

1. `director-agent` / `tomorrow_plan_preparation`
   - Platform id: `f8e38839-c63a-4a23-855d-afb00e3387b1`
   - Title: `Ежедневный план на завтра`
   - Status: `pending`
   - Created: 2026-05-26T19:00:08Z
   - Meaning for Hermes: needs a Hermes-visible follow-up or an explicit update on the existing sync/director lane so it does not disappear behind the platform-only queue.

2. `analytics-agent` / `daily_marketing_analysis`
   - Platform id: `cc69d9ff-06f6-4473-82b2-1a098482d5f6`
   - Title: `Ежедневный маркетинговый анализ`
   - Status: `pending`
   - Created: 2026-05-26T18:00:07Z
   - Meaning for Hermes: should be tracked as a recurring analytics input to release/store/marketing decisions, not executed as a mass-send action.

### Completed but requiring director attention

3. `crm-agent` / `crm_segmentation_and_messaging`
   - Platform id: `6116f32b-e417-4e1d-bbee-30b631431a5e`
   - Title: `Сегмент для рассылки бренд | магазин`
   - Status: `completed`
   - `needs_user_attention`: true
   - Result summary: agent answered, but readiness was not explicit; task is on director review.
   - Key decision still needed: approve channel, final audience size, message text, and send date before any campaign/messaging action.
   - PII note: the source contains customer identifiers/contact data; these were intentionally not copied into this report.

## Marketing/customer state relevant to Kanban

- `/api/marketing/ai-marketer/dashboard`: no active tasks, no pending approvals, tomorrow plan not ready.
- `/api/ai-marketer/dashboard`: 6,216 customers in churn-risk view: high 5,489, medium 302, low 425.
- Segment overview contains 22 segments. Useful visible examples: loyal buyers 595, economical buyers 836, potentially valuable 836, active 434, sleeping 855, new customers 418.
- `/api/ai-marketer/opportunities`: one re-engagement opportunity: 5,489 VIP/high-risk customers inactive 90+ days, potential revenue 27,445,000. Recommended by platform as discounts/personal offers, but GLAME should not run one mass blast; split into controlled segments and require approval.

## Current Hermes GLAME cards observed

- `t_33fdf04e` — GLAME P0: release audit клиентского приложения — running — priority 100
- `t_ded3c143` — GLAME P0: publishable catalog subset для приложения — running — priority 95
- `t_710831c6` — GLAME P1: синхронизация задач платформы и AI-агентов — running — priority 90
- `t_37330f40` — GLAME P1: магазин 15 м² в МРИИ — launch plan — running — priority 85
- `t_4ee52f64` — GLAME P1: sales playbook + 7 радикалов — running — priority 80
- `t_6a26c49a` — GLAME P1: CRM decision по UNO/Симферополь сегменту — running — priority 78
- `t_a7a4c3ce` — GLAME P2: качество каталога — фото, описания, категории — running — priority 70

## What should be created or updated in Hermes Kanban

### Create: not necessary right now

No new Hermes Kanban cards are required from this sync because the current Hermes board already covers the main platform signals:

- app release readiness → `t_33fdf04e`
- publishable catalog subset → `t_ded3c143`
- platform/agent sync → `t_710831c6`
- MRII 15 m² store launch → `t_37330f40`
- sales playbook and seven-radicals work → `t_4ee52f64`
- UNO/Simferopol CRM decision → `t_6a26c49a`
- catalog quality → `t_a7a4c3ce`

### Update / annotate existing cards

1. Update or comment on `t_6a26c49a` (CRM decision) with the platform CRM result:
   - completed platform task still needs director attention;
   - segment/audience decision is unresolved;
   - no campaign/send should happen until channel, final audience size, text, and timing are approved.

2. Keep `t_710831c6` recurring/scheduled or re-runnable:
   - source platform queues currently have 2 pending daily tasks and 1 completed-with-attention CRM task;
   - next sync should check whether the pending director/analytics tasks moved out of `pending` and whether `tomorrow_plan_ready` changed to true.

3. Feed the analytics/dashboard findings into existing business cards, not new duplicates:
   - churn/reactivation opportunity → `t_4ee52f64` and `t_6a26c49a`
   - app/catalog readiness → `t_33fdf04e`, `t_ded3c143`, `t_a7a4c3ce`
   - store-opening assortment/customer priorities → `t_37330f40`

### Potential future cards only if the state persists

Create new cards only if these conditions remain true after the next sync:

1. If `Ежедневный план на завтра` remains pending after the director window:
   - Proposed title: `GLAME P1: unblock platform director daily plan`
   - Goal: investigate why `director-agent` task is pending and prepare the plan manually from real data.

2. If `Ежедневный маркетинговый анализ` remains pending:
   - Proposed title: `GLAME P1: unblock daily marketing analytics task`
   - Goal: determine whether the analytics agent/cron is stuck, or produce the daily analysis from available data.

3. If the 5,489-customer re-engagement opportunity becomes an approved initiative:
   - Proposed title: `GLAME P1: segmented reactivation experiment design`
   - Goal: split into VIP/high-LTV, active/frequent, brand-loyal, new customers, and value-conscious cohorts; define offer/message/metric/guardrail. Do not send messages from this task without explicit approval.

## Operational guardrails

- No API write operations were performed.
- Do not trigger campaigns, customer messages, task processing, or agent actions from this sync without explicit approval.
- Do not copy raw customer PII from `/api/ai-marketer/dashboard` into Kanban comments or reports.
- Prefer updating/commenting existing Hermes cards over creating duplicates while the current seven GLAME cards are already active.
