# Telegram bridge для GLAME AI Agent Boards

Дата: 2026-07-21
Статус: MVP implementation note

## Цель

Telegram остаётся рабочим интерфейсом для всех задач GLAME, включая CRM, но результат работы агента должен храниться в GLAME Platform.

Это означает:

- администратор может писать агенту в Telegram;
- платформа определяет нужную AI-доску/агента;
- создаётся или переиспользуется platform task;
- входящее сообщение сохраняется в `agent_interaction_logs`;
- агент отвечает;
- ответ тоже сохраняется в `agent_interaction_logs`;
- для CRM агент дополнительно может сохранить `task.output_data.crm_plan`;
- Telegram остаётся каналом общения, но не source of truth.

## MVP endpoint

`POST /api/telegram/agent/message`

### Security

Endpoint поддерживает shared secret:

- env: `TELEGRAM_AGENT_BRIDGE_SECRET`
- header: `X-GLAME-Bridge-Secret`
- fallback body field: `bridge_secret`

Если env secret задан — запрос без секрета отклоняется `401`.
Если env secret не задан — endpoint работает в development mode.

Секреты нельзя логировать, возвращать в response или сохранять в task/log payload.

## Request contract

```json
{
  "chat_id": "315851436",
  "message": "Елена: подбери CRM сегмент Ялты и напиши скрипт звонка",
  "from_user": "Elena",
  "message_id": "12345",
  "topic_id": "crm",
  "board_id": "crm",
  "model": null,
  "send_reply": false,
  "metadata": {}
}
```

## Response contract

```json
{
  "ok": true,
  "board_id": "crm",
  "target_agent": "crm-agent",
  "task_id": "...",
  "reply": "...",
  "created_task": true,
  "user_log_id": "...",
  "assistant_log_id": "...",
  "crm_plan_saved": false,
  "telegram_send_result": null
}
```

## Routing

`resolve_telegram_agent_route(...)` routes explicit `board_id` first.

Current MVP routes:

- `crm` → `crm-agent`, `crm_telegram_dialog`
- `analytics` → `analytics-agent`, `analytics_telegram_dialog`
- `assortment` → `assortment-agent`, `assortment_telegram_dialog`
- `brand-media` → `brand-media-agent`, `brand_media_telegram_dialog`

If no explicit board is supplied, CRM keywords route to AI CRM:

- CRM / црм
- клиент / клиенты
- сегмент / сегментация
- скрипт / скрипты
- звонок / обзвон
- сообщение / рассылка
- Ялта / Меганом / Центрум

Default fallback in MVP is CRM because current requirement prioritizes Telegram→CRM continuity.

## Platform persistence

For each Telegram conversation, the bridge creates or reuses an idempotent `AgentInteractionTask`:

```text
telegram:{chat_id}:{topic_id}:{board_id}
```

Stored task context includes:

- `platform_bridge = telegram`
- `source_platform = telegram`
- `source_of_truth = glame_platform`
- `telegram_chat_id`
- `telegram_topic_id`
- `telegram_from_user`
- `last_telegram_message_id`

Every inbound user message is saved as:

```text
agent_interaction_logs.event_type = dialog_message
agent_interaction_logs.agent_name = telegram-bridge
agent_interaction_logs.event_data.role = user
agent_interaction_logs.event_data.source = telegram
```

Every agent reply is saved as:

```text
agent_interaction_logs.event_type = dialog_message
agent_interaction_logs.agent_name = <target_agent>
agent_interaction_logs.event_data.role = assistant
agent_interaction_logs.event_data.source = telegram_agent_bridge
```

Duplicate Telegram events are detected by stable `bridge_event_id` from:

```text
chat_id + message_id + message
```

## CRM-specific behavior

For CRM-routed messages:

- `GLAME_CRM_OPERATING_CONTEXT` is used as system prompt;
- the prompt reminds the agent that Telegram is an input channel only;
- if the agent returns a fenced JSON `crm_plan`, the bridge extracts and stores it in:

```text
agent_interaction_tasks.output_data.crm_plan
```

This connects the earlier Elena Telegram workflow to the platform AI CRM board.

## Telegram delivery mode

The endpoint returns `reply` so the caller/gateway can send it back to Telegram.

Optional `send_reply = true` makes the platform attempt direct Telegram Bot API delivery through `TelegramService`, but the recommended durable pattern is:

1. Telegram gateway receives message.
2. Gateway POSTs to `/api/telegram/agent/message`.
3. Gateway sends returned `reply` back to the same Telegram chat/thread.
4. Platform remains source of truth.

This avoids coupling platform backend too tightly to Telegram Bot polling/webhook ownership.

## Next production steps

1. Configure gateway/webhook worker to call `/api/telegram/agent/message` for GLAME admin Telegram chats.
2. Set `TELEGRAM_AGENT_BRIDGE_SECRET` in platform backend env and gateway env.
3. Map Telegram chat IDs / topic names:
   - Elena CRM → `board_id=crm`, `topic_id=crm`
   - Anatoliy technical/platform tasks → relevant board or director-agent route
4. Add UI backlink from AI CRM task to Telegram chat/message if needed.
5. Extend routing table for all GLAME agent boards as they become operational.

## Acceptance criteria

- Telegram CRM message creates/reuses AI CRM platform task.
- Inbound Telegram message appears in task chat/logs.
- AI CRM reply appears in task chat/logs.
- API response includes reply for Telegram gateway delivery.
- CRM fenced JSON plan is saved to `task.output_data.crm_plan`.
- Endpoint is protected by `TELEGRAM_AGENT_BRIDGE_SECRET` in production.
- No Telegram secret/token is printed or stored in task/log payload.
