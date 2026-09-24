# ТЗ: Операционный CRM-раздел продавца в GLAME Platform

**Дата:** 2026-07-21  
**Инициатор:** GLAME / Anatoliy  
**Исполнитель:** Anatoliy / техническая команда  
**Статус:** ТЗ для технической оценки и реализации  
**Приоритет:** высокий  

---

## 0. Статус реализации на 2026-07-21

### Сделано

- Созданы DDL и SQLAlchemy-модели `crm_tasks` / `crm_task_events`.
- Миграция `backend/apply_crm_tasks_migration.py` применена к текущей БД `glame_db`.
- Подключены backend routes:
  - `/api/seller/crm/tasks`;
  - `/api/seller/crm/tasks/{task_id}`;
  - `/api/seller/crm/tasks/{task_id}/start`;
  - `/api/seller/crm/tasks/{task_id}/result`;
  - `/api/seller/crm/tasks/{task_id}/postpone`;
  - `/api/seller/crm/tasks/{task_id}/complete`;
  - `/api/admin/crm/tasks`;
  - `/api/admin/crm/tasks/dashboard`;
  - `/api/admin/crm/tasks/import`;
  - `/api/admin/crm/tasks/{task_id}/assign`;
  - `/api/admin/crm/tasks/attribute-purchases`.
- Реализован `CrmTaskService`: список задач, карточка, старт, результат, перенос, закрытие, переназначение, импорт, dashboard, базовая атрибуция.
- Добавлена backend-валидация обязательного комментария, обязательной даты переноса и seller access control.
- Результат CRM-задачи пишет событие в `crm_task_events` и сохраняет CRM-взаимодействие в `customer_messages`.
- Созданы frontend API-клиенты `sellerCrm` и `adminCrm`.
- Создан UI продавца `/profile/sellers/crm`.
- Создан UI менеджера `/admin/crm/tasks`; dashboard KPI встроен в эту страницу.
- Добавлен пункт навигации CRM продавца/админа.
- Реализован dry-run/apply импорт из Google Sheet `backend/scripts/import_seller_crm_tasks_from_sheet.py`.
- Импорт из Google Sheet применен: 938 задач, 938 уникальных idempotency keys, 0 сырых/невалидных статусов и CRM-групп.
- Повторный импорт идемпотентен: существующие задачи обновляются, дубли не создаются.
- `glame-stack.service` перезапущен; backend, admin frontend и storefront отвечают `200`.
- Текущий MVP-check: `PYTHONPATH=backend python3 -m pytest backend/tests/test_seller_crm_mvp.py -q` — 8 passed.

### Частично сделано

- Атрибуция продаж реализована технически, но фактически пока 0 атрибутированных задач, потому что импортированные строки не заполняют `last_contacted_at` для уже отработанных контактов.
- Dashboard есть в API и KPI-блоках `/admin/crm/tasks`, но отдельной страницы `/admin/crm/dashboard` нет.
- Admin import API есть, но в UI менеджера нет формы/кнопки импорта.
- История событий есть, но из-за повторных apply в текущей БД накоплено 938 `created_from_import` и 1876 `updated_from_import`.
- Импорт сопоставляет клиента по телефону и сохраняет имя продавца, но не связывает продавца с `assigned_seller_user_id` / external id, если в Sheet нет явного external id.

### Осталось

- Решить 5 строк импорта `customer_not_found`; две выглядят как склеенные телефоны в одной ячейке источника.
- Добавить отдельный маршрут/страницу `/admin/crm/dashboard` или зафиксировать в ТЗ, что dashboard живет внутри `/admin/crm/tasks`.
- Добавить UI импорта для менеджера или оставить импорт только техническим скриптом/admin JSON API.
- Дозаполнить `last_contacted_at` для импортированных уже отработанных задач, чтобы атрибуция продаж начала считать исторические касания.
- Добавить API tests на seller access control, admin filters, idempotency импорта и attribution.
- Добавить более полные backend tests из раздела 20: создание задачи, список продавца, чужая задача, dashboard, покупка после контакта.
- Добавить frontend/manual checks: мобильная верстка, длинные скрипты, фильтры, обязательность комментария, быстрые итоги.
- Реализовать/проверить ограничение 45 активных задач на продавца в день.
- Реализовать дедупликацию не только по `source_idempotency_key`, но и по активной задаче клиента в той же кампании/поводу.
- Добавить cooldown/защиту от повторных касаний после `do_not_disturb`, постоянного `not_relevant` и свежего сообщения без ответа.
- Добавить export/report для менеджера, если он нужен как часть MVP.
- Убрать/снизить Pydantic/SQLAlchemy deprecation warnings в тестах отдельной техзадачей.

---

## 1. Цель

Сделать в GLAME Platform операционный CRM-раздел для продавцов, который заменяет ежедневную работу в Google Sheets.

Продавец должен видеть назначенные CRM-задачи по клиентам, открывать карточку клиента, использовать готовый скрипт/текст, фиксировать результат контакта, комментарий и следующую дату действия.

Менеджер/Елена должны видеть выполнение по продавцам, магазинам, датам, статусам и результатам, включая продажи после CRM-касания.

---

## 2. Почему это нужно

Текущая работа через Google Sheets ограничивает контроль и масштабирование:

- продавцы могут не заполнить результат или комментарий;
- сложно контролировать просрочки;
- сложно видеть историю клиента в одном месте;
- CRM-волны требуют ручной подготовки и переноса;
- нет полноценной связки “CRM-касание → покупка после контакта” в рабочем интерфейсе продавца/менеджера;
- Google Sheets должен остаться архивом/резервом, а не основным рабочим инструментом.

Платформа уже содержит часть нужной базы:

- пользователи/клиенты в `users`;
- покупательские метрики: телефон, город, ДР, total purchases, total spent, average check, last purchase date, customer segment, preferred store;
- история коммуникаций в `customer_messages`;
- админские покупатели и сегментация;
- seller/profile-разделы и KPI продавцов;
- `CrmInteractionAttributionService` для атрибуции покупок после CRM-взаимодействий;
- импорт истории звонков/CRM из Google Sheets.

Нужно добавить отдельный слой **операционных CRM-задач**, не перегружая `customer_messages`.

---

## 3. Область MVP

### Входит в MVP

1. Новая сущность `crm_tasks`.
2. История изменений `crm_task_events`.
3. API продавца для списка задач, карточки и фиксации результата.
4. API менеджера для контроля задач.
5. UI-раздел продавца.
6. UI-раздел менеджера/Елены.
7. Импорт текущих рабочих строк из Google Sheets в `crm_tasks`.
8. Базовая атрибуция продаж после CRM-касания через существующий CRM attribution service или его расширение.
9. Ролевой доступ: продавец видит только свои задачи; менеджер/admin видит все.

### Не входит в MVP

1. Автоматическая массовая отправка сообщений клиентам.
2. Автоматическое начисление бонусов.
3. Автоматическое создание СДЭК-накладных.
4. Полностью автоматический AI-генератор CRM-волн без подтверждения менеджера.
5. Публичные клиентские уведомления без ручного действия/подтверждения.

---

## 4. Пользовательские роли

### Продавец

Может:

- видеть свои CRM-задачи;
- открывать карточку клиента;
- звонить/писать клиенту вручную по готовому скрипту;
- фиксировать статус, итог, комментарий;
- переносить задачу на другую дату;
- закрывать задачу только с обязательным результатом.

Не может:

- видеть задачи других продавцов;
- менять назначенного продавца;
- массово создавать задачи;
- удалять CRM-задачи;
- менять CRM-правила/сегменты.

### Менеджер / Елена / admin

Может:

- видеть все CRM-задачи;
- фильтровать по магазину, продавцу, дате, статусу, CRM-группе, кампании;
- назначать/переназначать задачи;
- импортировать задачи из сегмента/Google Sheets;
- контролировать просрочки и задачи без комментария;
- видеть продажи после CRM-касания;
- выгружать отчет.

---

## 5. Навигация и страницы

### Продавец

Рекомендуемый маршрут:

```text
/profile/sellers/crm
```

Альтернативный вариант:

```text
/seller/crm
```

Страница должна быть доступна из текущего seller/profile-раздела рядом с KPI, сменами и личным кабинетом продавца.

### Менеджер / admin

Рекомендуемые маршруты:

```text
/admin/crm/tasks
/admin/crm/dashboard
```

Или как раздел внутри существующего seller/admin блока:

```text
/profile/sellers/crm-admin
```

Важно: существующий `/ai-marketer/boards/crm` не считать заменой этому разделу. Он относится к маркетинговому pipeline/agent tasks, а новый CRM-раздел — к ежедневной операционной работе продавцов.

---

## 6. Основные сценарии

### 6.1. Продавец открывает задачи на сегодня

1. Продавец логинится.
2. Переходит в CRM-раздел.
3. По умолчанию видит задачи на сегодня:
   - `Новая`;
   - `В работе`;
   - `Перенести`, если `next_action_date` = сегодня;
   - просроченные незакрытые задачи.
4. Список отсортирован по приоритету и времени создания/дедлайну.

### 6.2. Продавец отрабатывает клиента

1. Открывает задачу.
2. Видит клиентскую карточку:
   - имя;
   - телефон;
   - город;
   - предпочитаемый магазин;
   - сумма покупок;
   - количество покупок;
   - средний чек;
   - последняя покупка;
   - сегмент;
   - повод CRM-касания;
   - готовый скрипт/текст;
   - история прошлых CRM-коммуникаций.
3. Связывается с клиентом вручную.
4. Выбирает итог.
5. Пишет комментарий.
6. При необходимости ставит следующую дату действия.
7. Сохраняет результат.

### 6.3. Менеджер контролирует выполнение

1. Менеджер открывает CRM dashboard.
2. Видит:
   - задач назначено сегодня;
   - выполнено;
   - просрочено;
   - без комментария;
   - перенесено;
   - продажи после касания;
   - эффективность по продавцам;
   - эффективность по CRM-группам.
3. Фильтрует по магазину/продавцу/дате.
4. Открывает проблемные задачи и видит историю изменений.

### 6.4. Импорт из Google Sheets

1. Менеджер/админ запускает импорт.
2. Система читает строки из текущих рабочих CRM-файлов.
3. Сопоставляет клиента по телефону.
4. Сопоставляет продавца по имени/1C external id, если возможно.
5. Создает или обновляет `crm_tasks` с idempotency key.
6. Возвращает отчет:
   - создано;
   - обновлено;
   - пропущено как дубль;
   - не найден клиент;
   - не найден продавец;
   - ошибки строк.

---

## 7. CRM-группы

Использовать фиксированные группы:

```text
A. Личный звонок
B. Личное сообщение
C. Сегментированное сообщение
D. Не трогать / проверить
```

Технические значения:

```text
personal_call
personal_message
segmented_message
do_not_touch_review
```

---

## 8. Статусы задачи

### Статус работы

```text
new          — Новая
in_progress  — В работе
worked       — Проверено / отработано
postponed    — Перенести
not_relevant — Неактуально
do_not_disturb — Не беспокоить
closed       — Закрыто
```

Правила:

- `closed`, `not_relevant`, `do_not_disturb` — терминальные статусы.
- `postponed` требует `next_action_date`.
- `worked` и `closed` требуют `seller_outcome` и `seller_comment`.
- Просрочка считается по `due_date` или `work_date`, если `due_date` пустой.

---

## 9. Итоги продавца

Фиксированный справочник:

```text
no_answer               — Не дозвонились
sent_no_reply           — Отправлено, ответа нет
replied                 — Ответила
requested_photo_video   — Попросила видео/фото
photo_video_sent        — Видео/фото отправлено
sale                    — Продажа
postpone                — Перенести
not_relevant            — Неактуально
do_not_disturb          — Не беспокоить
create_cdek             — Создать накладную СДЭК
```

Правила:

- `postpone` требует `next_action_date`.
- `sale` не должен вручную создавать продажу; продажа подтягивается из 1С/истории покупок и атрибутируется после касания.
- `create_cdek` только фиксирует потребность в доставке/накладной, без автоматического создания в MVP.

---

## 10. Карточка CRM-задачи

### Обязательные поля в карточке

- клиент;
- телефон;
- город;
- предпочитаемый магазин;
- ответственный продавец;
- дата работы;
- дедлайн;
- CRM-группа;
- приоритет;
- причина попадания в сегмент;
- действие для продавца;
- готовый скрипт/текст;
- статус;
- итог;
- комментарий;
- следующая дата действия;
- источник/кампания;
- история событий;
- продажи после касания, если есть.

### Клиентский блок

Показывать из `users` и покупательской аналитики:

- `full_name`;
- `phone`;
- `city`;
- `birth_date`, если доступна и уместна;
- `preferred_store_name`;
- `secondary_store_name`;
- `total_purchases`;
- `total_spent`;
- `average_check`;
- `last_purchase_date`;
- `customer_segment`;
- `loyalty_points`.

### История коммуникаций

Показывать последние CRM-коммуникации из:

- `customer_messages`;
- `crm_tasks` / `crm_task_events`;
- импортированной истории звонков, если она уже хранится в `customer_messages.payload` или другом источнике.

---

## 11. Ограничения бизнес-логики

1. Не назначать продавцу больше ориентировочно **45 активных задач в день** без ручного подтверждения менеджера.
2. Не создавать дубли по одному клиенту в одной CRM-волне.
3. Не создавать новую задачу клиенту, если есть активная незакрытая задача по той же кампании/поводу.
4. Не включать клиента в массовые повторные касания, если последний статус:
   - `do_not_disturb`;
   - `not_relevant`, если причина постоянная;
   - недавнее отправленное сообщение без ответа в пределах cooldown-периода.
5. Для ДР-CRM соблюдать отдельную утвержденную логику GLAME:
   - D−3 — старт коммуникации/начисления, а не срок действия подарка;
   - до 20 000 ₽ → 500 бонусов, действуют 30 дней;
   - 20 000–49 999 ₽ → 1 000 бонусов, действуют 30 дней;
   - 50 000–99 999 ₽ → 2 000 бонусов, действуют 30 дней;
   - 100 000–299 999 ₽ → сертификат 5 000 ₽ + звонок, действует 6 месяцев;
   - 300 000 ₽+ → сертификат 5 000 ₽ + звонок + цветы, действует 6 месяцев;
   - не публиковать/не отправлять без одобрения, если сценарий требует approval.
6. Для Ялты в 2026 не использовать туристические офферы.
7. Для Центрума учитывать стратегию минимизации/выхода; не создавать задачи, которые предполагают активное развитие Центрума без отдельного решения.
8. Сообщения продавцам/клиентам должны сохранять premium tone GLAME: без давления, без массово-дешевого звучания, без “комфортный бюджет”.

---

## 12. Модель данных

### 12.1. Таблица `crm_tasks`

```sql
CREATE TABLE crm_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    customer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    assigned_seller_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    assigned_seller_external_id VARCHAR(255) NULL,
    assigned_seller_name VARCHAR(255) NULL,

    store_id VARCHAR(255) NULL,
    store_name VARCHAR(255) NULL,

    work_date DATE NOT NULL,
    due_date TIMESTAMPTZ NULL,
    priority INTEGER NOT NULL DEFAULT 3,

    crm_group VARCHAR(64) NOT NULL,
    reason TEXT NULL,
    seller_action TEXT NULL,

    script_key VARCHAR(128) NULL,
    script_text TEXT NULL,

    status VARCHAR(32) NOT NULL DEFAULT 'new',
    seller_outcome VARCHAR(64) NULL,
    seller_comment TEXT NULL,
    next_action_date DATE NULL,

    campaign_id VARCHAR(255) NULL,
    campaign_name VARCHAR(255) NULL,
    source VARCHAR(64) NOT NULL DEFAULT 'manual',
    source_row_id VARCHAR(255) NULL,
    source_idempotency_key VARCHAR(255) NULL,
    source_payload JSONB NULL,

    last_contacted_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL,

    attributed_purchase_count INTEGER NOT NULL DEFAULT 0,
    attributed_revenue_kopecks INTEGER NOT NULL DEFAULT 0,
    attributed_purchase_ids JSONB NULL,
    attributed_at TIMESTAMPTZ NULL,

    created_by_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NULL
);
```

### 12.2. Индексы `crm_tasks`

```sql
CREATE INDEX ix_crm_tasks_customer ON crm_tasks(customer_id);
CREATE INDEX ix_crm_tasks_seller_date ON crm_tasks(assigned_seller_external_id, work_date);
CREATE INDEX ix_crm_tasks_seller_user_date ON crm_tasks(assigned_seller_user_id, work_date);
CREATE INDEX ix_crm_tasks_store_date ON crm_tasks(store_name, work_date);
CREATE INDEX ix_crm_tasks_status ON crm_tasks(status);
CREATE INDEX ix_crm_tasks_campaign ON crm_tasks(campaign_id);
CREATE UNIQUE INDEX ux_crm_tasks_source_idempotency ON crm_tasks(source_idempotency_key) WHERE source_idempotency_key IS NOT NULL;
```

### 12.3. Таблица `crm_task_events`

```sql
CREATE TABLE crm_task_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES crm_tasks(id) ON DELETE CASCADE,
    event_type VARCHAR(64) NOT NULL,
    actor_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    actor_name VARCHAR(255) NULL,
    previous_status VARCHAR(32) NULL,
    next_status VARCHAR(32) NULL,
    payload JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 12.4. Индексы `crm_task_events`

```sql
CREATE INDEX ix_crm_task_events_task_created ON crm_task_events(task_id, created_at);
CREATE INDEX ix_crm_task_events_type_created ON crm_task_events(event_type, created_at);
```

---

## 13. Backend: файлы и сервисы

Рекомендуемая структура:

```text
backend/app/models/crm_task.py
backend/app/schemas/crm_tasks.py
backend/app/services/crm_task_service.py
backend/app/services/crm_task_import_service.py
backend/app/api/seller_crm.py
backend/app/api/admin/crm_tasks.py
backend/scripts/import_crm_tasks_from_google_sheets.py
```

### 13.1. Модель

Создать SQLAlchemy-модели:

- `CrmTask`;
- `CrmTaskEvent`.

Подключить их в `backend/app/models/__init__.py`, если проект использует централизованный импорт моделей.

### 13.2. Сервис задач

`CrmTaskService` должен уметь:

- получить задачи продавца;
- получить карточку задачи;
- обновить результат;
- перенести задачу;
- закрыть задачу;
- создать event при каждом изменении;
- проверить обязательные поля перед закрытием;
- проверить доступ продавца к задаче;
- считать dashboard-агрегации.

### 13.3. Сервис импорта

`CrmTaskImportService` должен уметь:

- принимать нормализованные строки из Google Sheets/CSV;
- нормализовать телефон;
- искать клиента в `users` по телефону;
- сопоставлять продавца по external id/name;
- строить `source_idempotency_key`;
- создавать/обновлять задачу;
- возвращать подробный отчет.

---

## 14. API

### 14.1. API продавца

#### `GET /api/seller/crm/tasks`

Параметры:

```text
date=YYYY-MM-DD | today
status=new,in_progress,postponed,worked
include_overdue=true|false
limit=100
offset=0
```

Возвращает список задач текущего продавца.

#### `GET /api/seller/crm/tasks/{task_id}`

Возвращает полную карточку CRM-задачи.

#### `PATCH /api/seller/crm/tasks/{task_id}/start`

Переводит задачу в `in_progress` и пишет event `started`.

#### `PATCH /api/seller/crm/tasks/{task_id}/result`

Payload:

```json
{
  "seller_outcome": "sent_no_reply",
  "seller_comment": "Отправила подборку в WhatsApp, ответа пока нет",
  "next_action_date": "2026-07-23"
}
```

Правила:

- комментарий обязателен;
- если outcome = `postpone`, `next_action_date` обязателен;
- если outcome терминальный, статус меняется соответственно;
- иначе статус становится `worked` или `postponed`.

#### `PATCH /api/seller/crm/tasks/{task_id}/postpone`

Payload:

```json
{
  "next_action_date": "2026-07-24",
  "seller_comment": "Клиент попросила написать в пятницу"
}
```

#### `PATCH /api/seller/crm/tasks/{task_id}/complete`

Закрывает задачу, если заполнены обязательные поля.

### 14.2. API менеджера/admin

#### `GET /api/admin/crm/tasks`

Фильтры:

```text
start_date=YYYY-MM-DD
end_date=YYYY-MM-DD
store_name=...
seller_external_id=...
seller_name=...
status=...
crm_group=...
campaign_id=...
only_overdue=true|false
only_without_comment=true|false
limit=100
offset=0
```

#### `GET /api/admin/crm/tasks/{task_id}`

Полная карточка, включая события.

#### `POST /api/admin/crm/tasks/import`

Импорт из файла/нормализованного JSON.

Payload вариант JSON:

```json
{
  "source": "google_sheets",
  "campaign_id": "yalta_crm_2026_07_wave_01",
  "campaign_name": "Ялта CRM июль 2026 — волна 1",
  "rows": [
    {
      "phone": "79780000000",
      "customer_name": "Имя клиента",
      "seller_name": "Имя продавца",
      "store_name": "Ялта, Набережная 18",
      "work_date": "2026-07-22",
      "crm_group": "personal_call",
      "priority": 1,
      "reason": "30k+ сумма покупок",
      "seller_action": "Позвонить, предложить видео-подборку",
      "script_text": "...",
      "source_row_id": "sheet:row:123"
    }
  ]
}
```

#### `PATCH /api/admin/crm/tasks/{task_id}/assign`

Переназначение продавца.

#### `GET /api/admin/crm/dashboard`

Агрегации по периоду.

#### `POST /api/admin/crm/tasks/attribute-purchases`

Запускает атрибуцию продаж после CRM-касания по задачам/периоду.

---

## 15. Frontend

### 15.1. API-клиент

Добавить методы в `frontend/src/lib/api.ts`:

```ts
sellerCrm: {
  listTasks(params): Promise<CrmTaskListResponse>;
  getTask(id: string): Promise<CrmTaskDetail>;
  startTask(id: string): Promise<CrmTaskDetail>;
  updateResult(id: string, payload: CrmTaskResultPayload): Promise<CrmTaskDetail>;
  postponeTask(id: string, payload: CrmTaskPostponePayload): Promise<CrmTaskDetail>;
  completeTask(id: string): Promise<CrmTaskDetail>;
}

adminCrm: {
  listTasks(params): Promise<CrmTaskListResponse>;
  getTask(id: string): Promise<CrmTaskDetail>;
  importTasks(payload): Promise<CrmTaskImportResponse>;
  assignTask(id: string, payload): Promise<CrmTaskDetail>;
  dashboard(params): Promise<CrmDashboardResponse>;
  attributePurchases(payload): Promise<CrmAttributionResponse>;
}
```

### 15.2. Страница продавца

Создать:

```text
frontend/src/app/profile/sellers/crm/page.tsx
frontend/src/components/profile/SellerCrmPage.tsx
```

UI-блоки:

- фильтр даты: сегодня / завтра / просрочено / период;
- быстрые счетчики: всего, новые, в работе, просрочено, перенесено;
- список карточек задач;
- детальная карточка задачи;
- кнопки быстрых итогов;
- поле комментария;
- поле следующей даты;
- сохранение результата;
- история коммуникаций.

### 15.3. Страница менеджера

Создать:

```text
frontend/src/app/admin/crm/tasks/page.tsx
frontend/src/app/admin/crm/dashboard/page.tsx
frontend/src/components/admin/AdminCrmTasksPage.tsx
frontend/src/components/admin/AdminCrmDashboardPage.tsx
```

UI-блоки:

- фильтры: магазин, продавец, статус, дата, CRM-группа, кампания;
- KPI-карточки;
- таблица задач;
- проблемные задачи: просрочка, без комментария, без следующего действия;
- эффективность по продавцам;
- эффективность по CRM-группам;
- блок атрибуции продаж;
- импорт задач.

---

## 16. Импорт из Google Sheets

### Источники для первичной миграции

Использовать текущие рабочие CRM-таблицы/экспорты:

- `GLAME CRM — полная база Ялты`;
- `GLAME CRM — полная база Симферополя`;
- `GLAME — Симферополь CRM / SMS и прозвон`;
- другие актуальные CRM-файлы только после подтверждения владельца файла.

### Маппинг полей

```text
Телефон               -> users.phone / crm_tasks.source_payload.phone
Имя клиента           -> users.full_name fallback / source_payload.customer_name
Город                 -> users.city / source_payload.city
Магазин               -> crm_tasks.store_name
Продавец              -> assigned_seller_name / assigned_seller_external_id
Дата                  -> work_date
Группа CRM            -> crm_group
Статус                -> status
Итог                  -> seller_outcome
Комментарий           -> seller_comment
Следующая дата        -> next_action_date
Текст/скрипт          -> script_text
Причина сегмента      -> reason
Источник строки       -> source_row_id
```

### Idempotency key

Формат:

```text
google_sheets:<sheet_id>:<worksheet_name>:<row_number>
```

Если sheet row id недоступен:

```text
google_sheets:<campaign_id>:<normalized_phone>:<work_date>:<crm_group>
```

---

## 17. Атрибуция продаж после CRM-касания

MVP-логика:

1. После результата `worked`, `sent_no_reply`, `replied`, `photo_video_sent`, `sale` фиксировать `last_contacted_at`.
2. Атрибутировать покупки клиента после `last_contacted_at` в окне, например 14 дней.
3. Не учитывать товары/строки, исключенные из аналитических продаж по текущим правилам `sales_record_filters`.
4. Записывать:
   - `attributed_purchase_count`;
   - `attributed_revenue_kopecks`;
   - `attributed_purchase_ids`;
   - `attributed_at`.
5. Не считать ручной итог `sale` единственным источником истины; продажа должна подтверждаться продажами из 1С/истории покупок.

Можно расширить существующий `CrmInteractionAttributionService`, чтобы он работал не только с `customer_messages`, но и с `crm_tasks`.

---

## 18. Валидация и безопасность

### Backend validation

- Нельзя закрыть задачу без `seller_outcome`.
- Нельзя закрыть задачу без `seller_comment`.
- Нельзя перенести задачу без `next_action_date`.
- Нельзя назначить задачу на продавца, если продавец не найден и не указан хотя бы `assigned_seller_name`.
- Продавец не может обновлять чужие задачи.
- Admin/manager может обновлять любые задачи.
- Все изменения пишутся в `crm_task_events`.

### PII / данные клиентов

- Не логировать полные телефоны массово в error logs.
- В админском UI показывать телефон полностью только авторизованным ролям.
- В экспорт включать клиентские данные только для admin/manager.
- Не отправлять customer-facing сообщения автоматически в MVP.

---

## 19. Acceptance criteria

### Продавец

1. Продавец с ролью seller открывает `/profile/sellers/crm`.
2. Видит только свои задачи.
3. Видит задачи на сегодня и просроченные активные задачи.
4. Может открыть карточку клиента.
5. Видит телефон, повод, скрипт, метрики клиента и историю коммуникаций.
6. Не может сохранить результат без комментария.
7. Не может перенести задачу без следующей даты.
8. После сохранения результата задача меняет статус и появляется event.
9. Закрытая задача исчезает из активного списка, но доступна в истории/фильтре.

### Менеджер/admin

1. Admin открывает `/admin/crm/tasks`.
2. Видит задачи всех продавцов.
3. Фильтры по дате, магазину, продавцу, статусу, CRM-группе работают.
4. Dashboard показывает назначено/выполнено/просрочено/без комментария.
5. Импорт из тестового файла создает задачи и возвращает отчет.
6. Повторный импорт того же файла не создает дубли.
7. Переназначение продавца создает event.
8. Атрибуция продаж обновляет поля attributed purchase/revenue.

### Техническая проверка

1. Миграция создает таблицы и индексы.
2. Unit tests покрывают валидацию статусов и обязательных полей.
3. API tests покрывают seller access control.
4. API tests покрывают admin filters.
5. Import tests покрывают idempotency.
6. Frontend build проходит без TypeScript errors.
7. Нет автоматической отправки сообщений клиентам.

---

## 20. Тестовые сценарии

### Backend tests

Создать тесты на:

- создание CRM-задачи;
- список задач продавца;
- запрет доступа продавца к чужой задаче;
- сохранение результата с комментарием;
- ошибка при сохранении без комментария;
- перенос без даты возвращает 400;
- закрытие без outcome возвращает 400;
- импорт создает задачу;
- повторный импорт обновляет/пропускает дубль;
- dashboard считает статусы;
- attribution подтягивает покупку после контакта.

### Frontend checks

Проверить вручную:

- seller route открывается;
- admin route открывается;
- фильтры работают;
- комментарий обязателен;
- быстрые кнопки итогов сохраняют правильный outcome;
- мобильная верстка карточки не ломается;
- длинный скрипт/комментарий не ломает карточку.

---

## 21. Рекомендуемые этапы реализации

### Этап 1 — Backend core

- модели `CrmTask`, `CrmTaskEvent`;
- миграция/DDL;
- service layer;
- seller API;
- admin API;
- базовые tests.

### Этап 2 — Seller UI

- `/profile/sellers/crm`;
- список задач;
- карточка клиента;
- сохранение результата;
- перенос/закрытие;
- история коммуникаций.

### Этап 3 — Admin UI

- `/admin/crm/tasks`;
- фильтры;
- dashboard;
- переназначение;
- проблемные задачи.

### Этап 4 — Import

- импорт из Google Sheets/CSV;
- idempotency;
- отчет импорта;
- первичная миграция текущих рабочих строк.

### Этап 5 — Attribution

- расширение CRM attribution;
- расчет продаж после касания;
- отображение в dashboard.

---

## 22. Риски и решения

### Риск: дубли клиентов из-за разного формата телефона

Решение:

- использовать существующую нормализацию телефона из auth/API;
- хранить normalized phone в import payload;
- показывать строки без найденного клиента в import report.

### Риск: продавцы не будут заполнять комментарии

Решение:

- backend validation: комментарий обязателен;
- UI не дает закрыть без комментария;
- dashboard показывает “без комментария”.

### Риск: Google Sheets содержит нестабильные названия колонок

Решение:

- делать нормализатор колонок;
- поддержать mapping config;
- неизвестные поля складывать в `source_payload`.

### Риск: CRM-продажи будут считаться некорректно

Решение:

- продажа подтверждается только из 1С/истории покупок;
- итог `sale` от продавца — сигнал, не источник истины;
- использовать существующие фильтры аналитически допустимых продаж.

### Риск: смешение marketing CRM board и seller CRM tasks

Решение:

- marketing board оставить для кампаний/agent tasks;
- seller CRM сделать отдельной операционной сущностью `crm_tasks`.

---

## 23. Definition of Done

Задача считается выполненной только если:

1. Таблицы CRM-задач созданы миграцией.
2. API продавца и admin API работают и покрыты тестами.
3. Продавец видит и отрабатывает свои задачи в интерфейсе.
4. Менеджер видит общий контроль и фильтры.
5. Импорт тестового CRM-файла работает без дублей.
6. Результаты продавца сохраняются с event history.
7. Нельзя закрыть задачу без обязательных полей.
8. Атрибуция продаж после контакта работает хотя бы в базовом режиме.
9. Frontend build проходит.
10. Нет автоматической отправки сообщений клиентам без явного отдельного approval.

---

## 24. Краткая формулировка для Kanban / platform task

**Название:** Операционный CRM-раздел продавца в GLAME Platform

**Описание:** Сделать раздел, который заменяет Google Sheets для ежедневной CRM-работы продавцов: назначенные клиентские задачи, карточка клиента, готовый скрипт, фиксация результата/комментария/следующей даты, менеджерский контроль выполнения и продажи после CRM-касания.

**Acceptance criteria:** продавец видит только свои задачи и не может закрыть без результата/комментария; менеджер видит все задачи, фильтры, просрочки и эффективность; импорт из Google Sheets работает идемпотентно; продажи после касания атрибутируются из данных 1С/истории покупок.
