# ТЗ: AI CRM как рабочий агент CRM внутри GLAME Platform

Дата: 2026-07-21
Статус: draft для Anatoliy / Elena approval

## Цель

Перенести рабочую логику CRM-диалогов, которые ранее велись с Еленой в Telegram, в раздел GLAME Platform `AI CRM`, чтобы:

- Елена могла ставить CRM-задачу агенту прямо на платформе или через Telegram;
- Hermes / AI CRM вел уточняющий диалог как CRM-агент;
- сегменты, скрипты, решения, согласования и итоги сохранялись в БД платформы;
- результат можно было превратить в операционные CRM-задачи продавцов;
- Telegram оставался удобным входом, но source of truth был на платформе.

## Текущая реализация, которую нужно использовать

### Frontend

- Страница CRM Board: `frontend/src/app/ai-marketer/boards/crm/page.tsx`
- Чат агента на board: `frontend/src/components/agents/AgentBoardChat.tsx`
- CRM Board уже отображает:
  - `AgentBoardChat` для `agentId="crm-agent"`;
  - список CRM-задач;
  - active CRM campaigns;
  - кнопки `Создать рассылку`, `Обновить`, `Дашборд`, `Пайплайн`.

### Backend

- Board API: `backend/app/api/ai_marketer.py`
  - `GET /api/ai-marketer/boards/{board_id}`
  - `POST /api/ai-marketer/boards/{board_id}/tasks/ensure`
- Agent task/chat API: `backend/app/api/agent_interactions.py`
  - `GET /api/agent-interactions/tasks/{task_id}/chat`
  - `POST /api/agent-interactions/tasks/{task_id}/chat`
  - `POST /api/agent-interactions/tasks/{task_id}/process`
- Canonical agent: `crm-agent`
- Runtime execution alias: `communication-agent`
- Prompt storage: `agent_system_prompts.agent_type = crm-agent`
- Task storage:
  - `agent_interaction_tasks`
  - `agent_interaction_logs`
- Dialog logs are already indexed into vector collection `task_dialogs`.

## Что уже работает

1. Раздел `AI CRM` существует и открывается как CRM Board.
2. Чат в верхней части страницы работает внутри конкретной задачи агента.
3. Сообщения пользователя и ответы агента сохраняются в `agent_interaction_logs` как `event_type="dialog_message"`.
4. Если задача связана с сегментацией, backend умеет создавать/обновлять `customer_segments` и `user_segments`.
5. В board уже видны CRM-задачи, статусы и результат.
6. `/process` для `crm-agent` фактически использует `communication-agent` и может генерировать `customer_messages` для найденных клиентов.

## Ограничение текущей реализации

Текущий AI CRM — это технически рабочий чат по задачам, но пока не полноценный бизнес-процесс уровня Telegram-диалогов с Еленой.

Сейчас не хватает:

1. Явного режима `CRM strategy session` / `рабочая CRM-сессия с Еленой`.
2. Структурированного сохранения результата диалога:
   - сегмент;
   - причина выбора сегмента;
   - канал;
   - скрипт звонка;
   - текст сообщения;
   - VIP-вариант;
   - правила исключения;
   - статус согласования;
   - дата запуска;
   - следующий шаг.
3. Привязки Telegram-диалогов Елены к платформенной CRM-задаче.
4. Кнопки/действия `Зафиксировать как CRM-план`, `Передать продавцам`, `Создать задачи продавцов`.
5. Отдельной сущности `crm_agent_sessions` или расширенного contract в `task_context/output_data`.
6. Специального промпта CRM-агента с правилами, согласованными с Еленой.

## Требуемая бизнес-логика CRM-агента

AI CRM должен работать как Hermes ранее работал с Еленой в Telegram:

1. Уточнить цель:
   - продажи;
   - возврат клиентов;
   - допродажа;
   - birthday CRM;
   - новая поставка;
   - локальная акция;
   - VIP/private offer.

2. Проверить/выбрать сегмент:
   - Ялта;
   - Симферополь / Центрум / Меганом;
   - VIP;
   - активные;
   - спящие;
   - свежая покупка;
   - 14–21 дней после покупки;
   - 30–45 дней;
   - 60–90 дней;
   - 120+ дней;
   - туристы / не Крым;
   - исключения и `не трогать`.

3. Подобрать сценарий:
   - звонок;
   - WhatsApp/SMS;
   - комбинированный сценарий;
   - видео-подборка;
   - private selection;
   - delivery / упаковка / подарок;
   - перенос на продавца.

4. Написать скрипты:
   - короткий opener;
   - основной текст;
   - VIP-вариант;
   - ответ на возражение;
   - follow-up;
   - комментарий для продавца.

5. Проверить GLAME tone:
   - не использовать `комфортный бюджет` для Крыма;
   - не говорить `посмотреть подборку`, использовать `подготовлю видео-подборку`;
   - не звучать как массовая распродажа;
   - не давить жалостью;
   - честно объяснять сложный сезон, если это релевантно;
   - для VIP не отправлять общий текст.

6. Зафиксировать результат:
   - `segment_id`;
   - фактический размер сегмента;
   - канал;
   - скрипт;
   - статус `draft / needs_elena_approval / approved / ready_for_sellers / launched / measured`;
   - risks;
   - next action.

## Рекомендуемая архитектура MVP

### Вариант A — минимальный и быстрый

Использовать текущие таблицы:

- `agent_interaction_tasks`
- `agent_interaction_logs`
- `customer_segments`
- `user_segments`
- уже добавленные `crm_tasks` / `crm_task_events` для продавцов

Доработать:

1. `AgentBoardChat`:
   - добавить CRM quick actions:
     - `Подобрать сегмент`;
     - `Написать скрипты`;
     - `Зафиксировать CRM-план`;
     - `Передать продавцам`;
     - `Вернуть на согласование Елене`.
2. `agent_interactions.chat_with_agent`:
   - для `crm-agent` добавлять CRM operating context;
   - сохранять structured output в `task.output_data.crm_plan`.
3. Добавить endpoint:
   - `POST /api/agent-interactions/tasks/{task_id}/crm/finalize-plan`
   - извлекает из последнего ответа/ручной формы structured CRM plan и сохраняет в `output_data`.
4. Добавить endpoint:
   - `POST /api/agent-interactions/tasks/{task_id}/crm/create-seller-tasks`
   - создаёт `crm_tasks` из согласованного сегмента и скрипта.

Плюс: быстро, мало миграций.
Минус: `crm_plan` хранится в JSON внутри task, а не как отдельная сущность.

### Вариант B — правильный production слой

Добавить отдельные таблицы:

- `crm_agent_sessions`
- `crm_agent_plans`
- `crm_agent_plan_versions`
- `crm_agent_plan_approvals`

Это лучше для долгой истории, версионности и аудита, но дольше.

## Рекомендация

Для MVP выбрать Вариант A:

1. Использовать существующий `AI CRM` board как рабочий интерфейс.
2. Сохранять диалог в `agent_interaction_logs`.
3. Сохранять результат в `agent_interaction_tasks.output_data.crm_plan`.
4. После согласования создавать операционные `crm_tasks` продавцам.
5. Позже вынести в отдельные таблицы, если процесс станет постоянным.

## Минимальный contract `crm_plan`

```json
{
  "status": "draft|needs_elena_approval|approved|ready_for_sellers|launched|measured",
  "goal": "string",
  "campaign_name": "string",
  "segment": {
    "segment_id": "uuid|null",
    "segment_name": "string",
    "customer_count": 0,
    "rules_summary": "string",
    "exclusions": ["string"]
  },
  "scenario": {
    "channel": "call|whatsapp|sms|combined|video_selection",
    "seller_action": "string",
    "timing": "string",
    "priority": "normal|high|vip"
  },
  "scripts": {
    "call_opener": "string",
    "main_message": "string",
    "vip_message": "string",
    "follow_up": "string",
    "objection_reply": "string",
    "seller_note": "string"
  },
  "approval": {
    "required_by": "elena|anatoliy|manager",
    "approved_by": null,
    "approved_at": null,
    "approval_notes": "string"
  },
  "risks": ["string"],
  "next_action": "string"
}
```

## Telegram bridge

Telegram можно оставить как входной канал, но каждый Telegram-запрос Елены должен зеркалиться в платформу:

1. Найти или создать задачу `crm-agent` на board `crm`.
2. Записать сообщение Елены как `dialog_message`.
3. Получить ответ AI CRM.
4. Сохранить ответ в `agent_interaction_logs`.
5. Отправить ответ обратно Елене в Telegram.
6. В платформе оставить полный источник истины: задача, чат, план, сегмент, скрипты, approvals.

## Acceptance criteria

1. Елена открывает `AI CRM` и видит рабочий чат с CRM-агентом.
2. Любой диалог сохраняется в платформе, а не теряется в Telegram.
3. AI CRM может собрать/привязать сегмент и показать фактический размер из БД.
4. AI CRM формирует скрипты общения по правилам GLAME.
5. Результат можно зафиксировать как `crm_plan`.
6. После approval можно создать CRM-задачи продавцам.
7. Продавец видит конкретные задачи в seller CRM разделе.
8. Результаты продавца попадают в карточку клиента → `Сообщения`.
9. Массовая рассылка/запуск без approval невозможны.
10. Telegram может использоваться как дополнительный интерфейс, но не как единственное хранилище результата.

## Следующий этап реализации

1. Обновить системный prompt `crm-agent` под GLAME CRM operating protocol.
2. Добавить structured `crm_plan` extraction/finalization endpoint.
3. Добавить UI-блок `CRM-план` в карточку задачи и на CRM Board.
4. Добавить action `Создать задачи продавцам` из `crm_plan`.
5. Добавить Telegram bridge для зеркалирования диалогов Елены в AI CRM task.
6. Прогнать backend/frontend проверки.
