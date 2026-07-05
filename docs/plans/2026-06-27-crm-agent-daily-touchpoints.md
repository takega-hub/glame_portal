# CRM Agent Daily Touchpoints Implementation Plan

> For Hermes: this is a technical handoff for Anatoliy approval. Do not implement until Anatoliy approves the schema/API/UI scope.

Goal: build the GLAME CRM module that generates a daily seller worklist of customer touchpoints, enforces one active task per customer/day, blocks sales prompts while service issues are active, preserves existing birthday rules, tracks seller statuses, and gives managers daily/weekly reports.

Architecture: add a backend CRM domain with persistent `crm_tasks`, immutable `crm_task_events` audit trail, and optional `crm_daily_runs`; reuse current `users`, `purchase_history`, seller KPI/schedule sources, and `birthday_crm_service.py`. The generator selects candidate touchpoints by priority, deduplicates per customer/day, creates seller-visible tasks without auto-sending messages, and the UI exposes a seller worklist plus manager report.

Tech stack: FastAPI, SQLAlchemy async, Alembic migrations under `data/migrations/versions`, Next.js admin/profile UI, existing auth/access gates.

Approval boundary:
- Elena-approved business direction and birthday rules remain unchanged.
- Development implementation requires Anatoliy technical approval.
- No auto-send to customers in MVP.
- Customer PII is sensitive: do not log phones/messages in raw server logs; expose only to authorized roles.

Current codebase findings:
- Existing birthday helper: `backend/app/services/birthday_crm_service.py` already builds draft birthday CRM cards with `auto_send=False` and has tests in `backend/tests/test_birthday_crm_service.py`.
- Existing role/access registry: `backend/app/services/admin_access.py` and `frontend/src/config/navigation.ts` should receive the new `crm_tasks` section.
- Existing seller sources: `backend/app/services/onec_sellers_service.py`, `backend/app/services/seller_kpi_service.py`, `users.preferred_store_name`, and `purchase_history` can seed responsible seller/store data.
- Existing API mount pattern: add router import in `backend/app/main.py` and include it under `/api/admin/crm`.
- Current environment API health check failed with nginx `502 Bad Gateway`; code planning is still possible, but API smoke verification needs backend runtime fixed first.

Verification already run:
- `PYTHONPATH=/workspace/glame-platform/backend /workspace/glame-platform/venv/bin/python -m unittest backend.tests.test_birthday_crm_service -v` -> 3 tests OK.
- `python /workspace/tools/glame_api.py env && python /workspace/tools/glame_api.py get /health` -> env present, `/health` failed with `502 Bad Gateway` through bridge proxy.

---

## Data model

### New table: `crm_tasks`

Required columns:
- `id UUID PK`
- `task_date DATE NOT NULL`
- `touchpoint_type VARCHAR(64) NOT NULL`
- `reason TEXT NOT NULL`
- `priority INTEGER NOT NULL`
- `customer_id UUID NULL REFERENCES users(id)`
- `customer_name VARCHAR(255) NULL`
- `phone VARCHAR(32) NULL`
- `city_store VARCHAR(255) NULL`
- `total_spent_rub INTEGER NULL`
- `real_total_spent_rub INTEGER NULL`
- `card_number VARCHAR(64) NULL`
- `responsible_seller_id VARCHAR(255) NULL`
- `responsible_seller_name VARCHAR(255) NULL`
- `channel VARCHAR(32) NOT NULL DEFAULT 'message'`
- `seller_instruction TEXT NULL`
- `client_message_text TEXT NULL`
- `status VARCHAR(32) NOT NULL DEFAULT 'Готово'`
- `result_note TEXT NULL`
- `next_action TEXT NULL`
- `next_action_at TIMESTAMPTZ NULL`
- `sale_amount_rub INTEGER NULL`
- `receipt_number VARCHAR(128) NULL`
- `source_data JSONB NULL`
- `crm_agent_comment TEXT NULL`
- `manager_review TEXT NULL`
- `is_active BOOLEAN NOT NULL DEFAULT TRUE`
- `created_by UUID NULL`
- `updated_by UUID NULL`
- `created_at TIMESTAMPTZ DEFAULT now()`
- `updated_at TIMESTAMPTZ NULL`

Indexes/constraints:
- index `(task_date, status)`
- index `(customer_id, task_date)`
- index `(responsible_seller_id, task_date)`
- index `(touchpoint_type, priority)`
- partial unique index: one generated active task per customer/date, e.g. `UNIQUE (customer_id, task_date) WHERE is_active = true AND source_data->>'manual_override' IS DISTINCT FROM 'true'`
- status check or app-level validation for allowed statuses.

### New table: `crm_task_events`

Immutable audit trail:
- `id UUID PK`
- `task_id UUID NOT NULL REFERENCES crm_tasks(id) ON DELETE CASCADE`
- `event_type VARCHAR(64) NOT NULL` (`created`, `generated`, `status_changed`, `field_updated`, `manager_reviewed`)
- `actor_user_id UUID NULL`
- `from_status VARCHAR(32) NULL`
- `to_status VARCHAR(32) NULL`
- `payload JSONB NULL`
- `created_at TIMESTAMPTZ DEFAULT now()`

### Optional new table: `crm_daily_runs`

For idempotent generation:
- `id UUID PK`
- `task_date DATE NOT NULL UNIQUE`
- `status VARCHAR(32) NOT NULL`
- `created_count INTEGER NOT NULL DEFAULT 0`
- `skipped_count INTEGER NOT NULL DEFAULT 0`
- `source_summary JSONB NULL`
- `started_at TIMESTAMPTZ DEFAULT now()`
- `finished_at TIMESTAMPTZ NULL`
- `created_by UUID NULL`

---

## Business constants

Create `backend/app/services/crm_reference.py`:

```python
CRM_STATUSES = [
    'Готово',
    'Связались',
    'Нет связи',
    'В диалоге',
    'Сервис',
    'Фото отправлены',
    'Ждём в магазине',
    'Купил',
    'Закрыто',
]

OPEN_STATUSES_REQUIRING_NEXT_ACTION = {
    'Нет связи',
    'В диалоге',
    'Сервис',
    'Фото отправлены',
    'Ждём в магазине',
}

TOUCHPOINT_PRIORITIES = [
    ('service_issue', 'Сервисный вопрос', 1),
    ('warranty', 'Гарантия', 2),
    ('active_dialog', 'Активный диалог', 3),
    ('thank_you_care', 'Благодарность + уход', 4),
    ('cleaning_care', 'Чистка / уход', 5),
    ('birthday_bonus', 'Бонусы / ДР', 6),
    ('gift', 'Подарок', 7),
    ('brand_new_arrival', 'Новинки конкретного бренда', 8),
    ('brand_life_update', 'Жизнь бренда / общий апдейт', 9),
]
```

Preserve birthday rules:
- 3% -> 500 бонусов
- 5% -> 1 000 бонусов
- 7% -> 2 000 бонусов
- 10% -> 3 000 бонусов
- VIP -> 5 000 бонусов
- birthday window: D-3 / D / D+3
- only show birthday tasks where bonus is already accrued/verified and not previously processed.

---

## Implementation tasks

### Task 1: Add CRM SQLAlchemy models and migration

Objective: persist CRM tasks, generation runs, and audit trail.

Files:
- Create: `backend/app/models/crm_task.py`
- Modify: `backend/app/models/__init__.py`
- Create: `data/migrations/versions/063_crm_daily_tasks.py`

Steps:
1. Create models `CrmTask`, `CrmTaskEvent`, `CrmDailyRun` with columns above.
2. Import models in `backend/app/models/__init__.py` if this project uses model imports for metadata discovery.
3. Create Alembic migration after `062_gift_certificates`.
4. Include indexes and partial unique constraint for one active task per customer/date.
5. Verify syntax:
   - `PYTHONPATH=backend /workspace/glame-platform/venv/bin/python -m py_compile backend/app/models/crm_task.py`

Acceptance:
- Migration creates/drops all tables cleanly.
- Model fields match task passport fields.

### Task 2: Add validation/reference service

Objective: centralize CRM statuses, touchpoint priorities, and update validation.

Files:
- Create: `backend/app/services/crm_reference.py`
- Create: `backend/tests/test_crm_reference.py`

Validation rules:
- Status must be in `CRM_STATUSES`.
- Status `Купил` requires `sale_amount_rub > 0`.
- Status in `OPEN_STATUSES_REQUIRING_NEXT_ACTION` requires non-empty `next_action`; `next_action_at` is recommended but not hard-fail unless Anatoliy chooses strict mode.
- Seller cannot update immutable generated fields: customer, phone, reason, touchpoint_type, priority, client_message_text, source_data.

Tests:
- `Купил` without amount -> validation error.
- `Нет связи` without next_action -> validation error.
- `Связались` with result_note -> OK.
- Unknown status -> validation error.

### Task 3: Implement CRM generation service

Objective: generate daily worklist without auto-sending and with priority/dedup safeguards.

Files:
- Create: `backend/app/services/crm_task_service.py`
- Modify if needed: `backend/app/services/birthday_crm_service.py` only to expose a helper that can mark already-processed birthday customers; do not change business rules.
- Create: `backend/tests/test_crm_task_service.py`

Service functions:
- `generate_daily_tasks(task_date: date, actor_user_id: UUID | None) -> dict`
- `list_tasks(filters) -> list[dict]`
- `update_task_status(task_id, payload, actor_user_id) -> CrmTask`
- `build_report(from_date, to_date, store=None, seller=None) -> dict`

Candidate selection MVP:
1. Load active service tasks first from existing CRM history once available; until service-source integration exists, allow manual/service seed candidates from `source_data`.
2. Birthday candidates from `BirthdayCrmService.get_upcoming_cards`, but only include records that are already verified/accrued and not already processed. If current data cannot prove accrued status, skip with `skipped_reason='birthday_bonus_not_verified'` instead of showing unsafe tasks.
3. Post-purchase care candidates from `purchase_history` after recent purchase window, excluding customers with active service tasks.
4. Brand/product update candidates only if there is a concrete brand/category match in `purchase_preferences` or purchase history; no generic “может быть интересно”.

Dedup algorithm:
- Build candidates with `customer_id`, `priority`, `touchpoint_type`, `reason`.
- Sort by priority asc, then stronger source confidence, then recency.
- For each customer/date, keep only first candidate unless `manual_override=True`.
- If any active service task exists for customer, drop sales/new-arrival candidates.
- Insert only if no active generated task for same customer/date already exists.

Tests:
- priority selection keeps service over birthday/new arrival.
- one customer/date gets one task.
- active service blocks sales reasons.
- birthday candidate with `pending/not_verified/net0/already_processed` is skipped.
- generation is idempotent if called twice for same date.

### Task 4: Add API router

Objective: expose admin/seller CRM endpoints.

Files:
- Create: `backend/app/api/admin/crm.py`
- Modify: `backend/app/main.py`

Endpoints:
- `GET /api/admin/crm/tasks?date=&store=&seller=&status=&touchpoint=`
- `POST /api/admin/crm/tasks/generate-daily`
- `PATCH /api/admin/crm/tasks/{task_id}`
- `GET /api/admin/crm/tasks/report?from=&to=&store=&seller=`
- `GET /api/admin/crm/reference`

Security:
- Admin/manager can list all and generate.
- Seller can list assigned/current-store tasks only if role model supports that mapping; if not, MVP restricts seller UI until seller identity mapping is explicit.
- Patch endpoint must allow sellers/managers to update only status/result/next_action/sale/receipt fields.
- Every patch writes `crm_task_events`.

API smoke tests:
- reference endpoint returns statuses/priorities.
- generate endpoint creates tasks without auto-sending.
- patch `Купил` without sale amount returns 400.
- patch open status without next_action returns 400.
- report endpoint returns daily totals.

### Task 5: Add frontend API client helpers

Objective: make CRM endpoints consumable by UI.

Files:
- Modify: `frontend/src/lib/api.ts`
- Create if preferred: `frontend/src/lib/crm.ts`

Functions:
- `getCrmReference()`
- `getCrmTasks(filters)`
- `generateCrmDailyTasks(date)`
- `updateCrmTask(taskId, payload)`
- `getCrmReport(filters)`

Do not include customer auto-send functions.

### Task 6: Add CRM worklist UI

Objective: seller/manager sees daily tasks and can update allowed status fields.

Files:
- Create: `frontend/src/app/admin/crm/page.tsx`
- Create: `frontend/src/components/crm/CrmTasksPage.tsx`
- Create: `frontend/src/components/crm/CrmTaskTable.tsx`
- Create: `frontend/src/components/crm/CrmTaskDrawer.tsx`

UI requirements:
- Filters: date, store, seller, touchpoint, status, overdue/without next action.
- Table shows concise fields: priority, reason, customer, phone, store, seller, channel, status, next_action_at.
- Drawer/card shows full seller_instruction and client_message_text.
- Read-only fields must be visually locked: customer, phone, reason, touchpoint, original message text.
- Inline status change validates required fields before submitting.
- Status `Купил` shows required sale amount field.
- Open statuses show required next action field.

### Task 7: Add CRM report UI

Objective: manager sees daily/weekly completion and sales outcomes.

Files:
- Create: `frontend/src/components/crm/CrmReportPanel.tsx`
- Add tab/section to `CrmTasksPage.tsx`

Metrics:
- total tasks
- contacted
- no contact
- in dialog
- service
- photos sent
- waiting in store
- bought
- CRM sale RUB
- tasks without next action
- overdue tasks
- completion by seller

### Task 8: Register navigation and access section

Objective: make CRM module discoverable and permission-controlled.

Files:
- Modify: `backend/app/services/admin_access.py`
- Modify: `frontend/src/config/navigation.ts`

Suggested section:
- id: `crm_tasks`
- name: `CRM задачи`
- href: `/admin/crm`
- group: `AI инструменты` or `Управление`

Default access proposal:
- admin: yes
- manager: yes
- marketer: read-only or yes depending on Anatoliy decision
- seller: yes only after seller identity mapping is safe; otherwise expose seller route through profile account area later.

### Task 9: Add scheduled/manual generation policy

Objective: support daily generation safely.

Files:
- Possibly add admin cron entry through existing `backend/app/services/cron_registry.py`
- Or keep MVP manual-only through `POST /generate-daily` until Anatoliy approves automated schedule.

Recommendation:
- MVP: manual generation from manager/admin button.
- Phase 2: scheduled generation once birthday accrual source and seller mapping are verified.

### Task 10: End-to-end verification

Commands:
- `PYTHONPATH=backend /workspace/glame-platform/venv/bin/python -m unittest backend.tests.test_birthday_crm_service -v`
- `PYTHONPATH=backend /workspace/glame-platform/venv/bin/python -m pytest backend/tests/test_crm_reference.py backend/tests/test_crm_task_service.py -q` if pytest is installed in backend runtime; otherwise use unittest or project test runner.
- `PYTHONPATH=backend /workspace/glame-platform/venv/bin/python -m py_compile backend/app/api/admin/crm.py backend/app/services/crm_task_service.py backend/app/models/crm_task.py`
- `cd frontend && npm run lint` if lint config is healthy.
- API smoke after backend is reachable:
  - `python /workspace/tools/glame_api.py get /health`
  - `python /workspace/tools/glame_api.py get /api/admin/crm/reference`
  - manual POST/PATCH smoke using an approved tool/script, without printing PII.

---

## Open decisions for Anatoliy

1. Seller identity mapping: should seller users be linked by `User.id`, 1C seller Ref_Key, phone, or manually maintained mapping?
2. Birthday accrual verification source: which table/API proves `ДР-бонус начислен и проверен` and `не отработан ранее`?
3. Service issue source: is there an existing service/warranty dataset, or should MVP support manual service-task creation first?
4. Generation schedule: manual only for MVP, or cron every morning after data sync?
5. Access level for marketer role: CRM read/report only or full task operations?
6. Strictness of `next_action_at`: recommended field or required for all open statuses?

## Recommended MVP cut

Implement first:
- persistent CRM task/audit tables;
- reference/validation service;
- manual generate endpoint with birthday + post-purchase candidates only where source confidence is safe;
- task list/patch/report API;
- manager-facing UI;
- unit tests for priority, dedup, birthday filter, sale amount, next action, audit.

Defer:
- customer auto-messages;
- fully automated cron generation;
- brand-new-arrival generation until inventory/new-arrival source is mapped;
- seller self-service route until seller identity mapping is verified.
