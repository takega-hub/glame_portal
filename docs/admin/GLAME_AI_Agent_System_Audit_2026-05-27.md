# GLAME AI Agent System Audit — 2026-05-27

## Scope

Reviewed all files in `docs/admin/` that describe the GLAME AI agent operating system and compared them with the current backend/frontend implementation.

Reviewed docs:

- `docs/admin/GLAME_AI_Agent_System_Prompts_v1_2.md`
- `docs/admin/GLAME_AI_Platform_Boards_Implementation_Plan.md`
- `docs/admin/GLAME_AI_Platform_Enterprise_Blueprint.md`
- `docs/admin/GLAME_AI_Platform_TZ_Team_Agents_UPDATED.md`
- `docs/admin/glame_ai_platform_boards_ui_logic_specification.md`

Reviewed implementation areas:

- Backend agent registry and agent classes: `backend/app/agents/*`
- Backend task/interaction models: `backend/app/models/agent_interaction.py`, `backend/app/models/agent_system_prompt.py`
- Backend APIs: `backend/app/api/agent_interactions.py`, `backend/app/api/agent_system_prompts.py`, `backend/app/api/ai_marketer.py`
- Frontend AI marketer pages: `frontend/src/app/ai-marketer/**/page.tsx`
- Frontend shared agent chat: `frontend/src/components/agents/AgentBoardChat.tsx`

## Target architecture from docs

The docs define GLAME AI as an AI-native luxury retail operating system, not a generic kanban/task list. The core ideas are:

1. One central orchestration layer: **AI Marketing Director**.
2. Seven specialist agents under the director:
   - AI Personal Media
   - AI Brand Media
   - AI CRM
   - AI PR & Partnerships
   - AI Traffic & Growth
   - AI Analytics
   - AI Assortment
3. Agents exchange **structured objects**, not only free-form chat.
4. Work must be traceable through task status, approvals, reports, escalations, memory and board views.
5. Elena/human approval is mandatory for sensitive changes, offers, discounts, CRM sends, positioning, risky partnerships and push campaigns.
6. Boards are operational command surfaces:
   - Marketing Command Board
   - Content Board
   - Personal Media Board
   - CRM Board
   - Partnership Board
   - Traffic/Growth Board
   - Product Focus Board
   - Analytics Board
7. The system must avoid isolated agent work; content, CRM, traffic, assortment and analytics should reinforce each other.
8. Agents must use real business data from platform DB/API and must not invent metrics, SKU, segments, customers or sales.

## What is already implemented

### 1. Canonical registry exists

`backend/app/agents/agent_registry.py` contains the canonical 8-agent registry aligned with `GLAME_AI_Agent_System_Prompts_v1_2.md`:

- `director-agent`
- `personal-media-agent`
- `brand-media-agent`
- `crm-agent`
- `pr-partnerships-agent`
- `traffic-growth-agent`
- `analytics-agent`
- `assortment-agent`

It also defines legacy aliases, which is important because older code still refers to `content-agent`, `communication-agent`, and `marketing-inventory-agent`.

### 2. Task and interaction data model exists

`backend/app/models/agent_interaction.py` implements:

- `AgentInteractionTask`
- `AgentInteractionLog`
- `AgentValidationRule`
- `AgentContentHandoff`

The model supports source/target agents, task type, context, input data, requirements, constraints, priorities, validation results, output data, deadlines, retries, statuses and audit logs.

### 3. Prompt versioning exists

`backend/app/models/agent_system_prompt.py` implements:

- `AgentSystemPrompt`
- `AgentPromptVersionHistory`
- `AgentPromptGenerationRequest`

`backend/app/api/agent_system_prompts.py` exposes prompt CRUD/versioning, activation, marketer review and prompt generation endpoints.

### 4. v1_2 prompt parser mostly exists

`POST /api/agent-system-prompts/seed-defaults` can parse v1_2-style prompt docs by extracting top-level sections like `# 1. AI MARKETING DIRECTOR — SYSTEM PROMPT` and mapping them to canonical agent IDs.

### 5. Task API exists

`backend/app/api/agent_interactions.py` exposes task lifecycle endpoints:

- create/list/get/update task
- validate
- queue
- process
- cancel/delete
- approve/reject/revise
- prioritized task list
- logs/chat/audit chain
- validation rules
- escalation checks/stats
- CRM mass-mailing preparation/run
- segment binding

### 6. Board aggregation API exists

`backend/app/api/ai_marketer.py` exposes:

- `GET /api/ai-marketer/boards/{board_id}`
- `POST /api/ai-marketer/boards/{board_id}/tasks/ensure`

This gives frontend boards a shared task aggregation/idempotent task creation surface.

### 7. Frontend board shell exists for all boards

The Next.js AI marketer area already has pages for:

- `/ai-marketer/boards/command`
- `/ai-marketer/boards/content`
- `/ai-marketer/boards/crm`
- `/ai-marketer/boards/partnership`
- `/ai-marketer/boards/personal-media`
- `/ai-marketer/boards/product`
- `/ai-marketer/boards/traffic`
- `/ai-marketer/boards/analytics`
- `/ai-marketer/tasks`
- `/ai-marketer/tasks/[id]`

`AgentBoardChat.tsx` provides a generic board/agent chat component that can create a board task and then call `/api/agent-interactions/tasks/{task_id}/chat`.

### 8. Some live data context exists

`agent_interactions.py` injects live context for:

- `analytics-agent` via `_get_analytics_agent_context_text()`
- `assortment-agent` via `_get_assortment_agent_context_text()`
- CRM segment binding and auto-segment creation logic

This is a strong step toward the docs requirement that agents use DB/API data, not invented facts.

## Main gaps versus documentation

### Gap 1 — Structured agent communication is not first-class yet

Docs define explicit structured objects:

```json
{
  "from_agent": "AI Marketing Director",
  "to_agent": "AI Brand Media",
  "type": "task_assignment",
  "priority": "P1",
  "context": "...",
  "task": "...",
  "deadline": "...",
  "expected_output": "...",
  "status": "Briefed"
}
```

Current implementation stores similar data across `AgentInteractionTask` fields, but there is no explicit canonical message/envelope contract with:

- `from_agent`
- `to_agent`
- `communication_type`
- `expected_output`
- `approval_policy`
- `dependencies`
- `handoff_payload`
- `director_decision`
- `agent_report`

Result: agents can chat and tasks can exist, but cross-agent handoff remains loosely typed.

### Gap 2 — Director is not yet a real workflow orchestrator

`DirectorAgent` has a large prompt and memory/data logic, but the active inter-agent flow is still mostly UI/API driven:

- board pages create tasks directly;
- task chat calls a generic LLM response;
- director QA is partially embedded in `chat_with_agent()`;
- there is no durable director workflow engine that decomposes a user request into subtasks, waits for specialist outputs, validates them and synthesizes final report.

Result: the Director is conceptually central, but operationally not yet the only coordination spine.

### Gap 3 — Specialist execution coverage is uneven

Canonical agents exist in registry and prompt mapping, but actual execution classes are legacy/partial:

- Brand/Personal Media route to `AdvancedContentAgent` through `content-agent` alias.
- CRM routes partly to `CommunicationAgent` and has strong segment logic in chat endpoint.
- Traffic/Growth has `MarketingAgent`, but not clearly wired as the canonical `traffic-growth-agent` executor in all flows.
- Analytics has data-context injection, but no dedicated full `AnalyticsAgent` class with structured reports.
- Assortment has inventory-related agents and live data context, but canonical `assortment-agent` execution is mostly prompt/data-context based.
- PR & Partnerships appears mostly board/prompt-level, not a dedicated executor.

Result: the system can answer as these agents in chat, but most agents are not independent workers with clear input/output contracts.

### Gap 4 — Prompt seeding default path is stale

`agent_system_prompts.py` default body for `/seed-defaults` is:

```py
"docs/admin/GLAME_AI_Agent_System_Prompts_v1.md"
```

But the actual file in `docs/admin/` is:

```text
GLAME_AI_Agent_System_Prompts_v1_2.md
```

If called without overriding `docs_path`, seed-defaults will 404. The parser supports v1_2, but the default path is wrong.

### Gap 5 — Approval policy is present but not normalized

There are statuses and endpoints for `approve`, `reject`, `revise`, and `pending_approval`. UI has approval buttons. However the docs require approval by decision category:

- strategy changes
- sensitive campaigns
- new offers
- discounts
- major CRM sends
- public positioning changes
- risky collaborations
- app push campaigns

Current tasks have `risk_level`, requirements and statuses, but no central approval policy engine that classifies tasks and enforces approval rules consistently.

### Gap 6 — Board UX exists, but many board-specific rules are still shallow

The docs describe board-specific operational logic: priority strip, weekly focus panel, agent status grid, operational timeline, approval queue, analytics snapshot, content calendar modes, campaign tracking, etc.

The frontend has pages for each board and real task/API integration, but much of the board behavior is currently derived from generic `agent_interaction_tasks` filtering and task fields. Some pages still contain placeholder/demo-ish text/empty-state logic.

Result: boards are usable shells, but not yet the polished operating system described in UI spec.

### Gap 7 — Memory system is fragmented

Docs define agent memories:

- Brand Media memory: successful reels, hooks, CTA, DNA/city performance.
- CRM memory: retention effectiveness, segment behaviour, repeat purchase patterns.
- Analytics memory: trends, correlations, seasonality.

Implementation has:

- director memory models;
- task dialog vector indexing;
- brand context vector search;
- task logs.

But there is no clear per-agent memory contract, no memory write/read policy per agent, and no distinction between temporary task history and reusable learnings.

### Gap 8 — Status taxonomy is inconsistent with docs

Docs use business statuses like:

- Briefed
- In Production
- Needs Approval
- Approved
- Scheduled
- Published
- Measured
- Done

Backend uses technical statuses:

- pending
- validating
- validated
- pending_approval
- approved
- queued
- processing
- completed
- failed
- rejected
- cancelled
- deleted

Frontend maps some statuses for display, but there is no explicit board-stage model. This makes board pipeline states fragile and inconsistent across boards.

### Gap 9 — Process endpoint and chat endpoint are not unified

There are two modes:

1. `/tasks/{id}/process` — executes some task types through hard-coded agents.
2. `/tasks/{id}/chat` — generic LLM chat with active prompt and context.

The docs imply one coherent operating model: assignment → execution → report → director review → approval/escalation. Current code has pieces of that, but not one unified lifecycle.

### Gap 10 — Me-as-Hermes interaction path is not formalized

The user wants this Hermes assistant to interact with platform agents. Right now the cleanest available path is through platform APIs/tasks/chats, but there is no explicit external-agent/operator contract for Hermes:

- create task as `hermes-agent` or `director-agent`?
- when to write to board task chat vs. director chat?
- how to mark outputs as verified?
- how to request Elena approval?
- how to avoid bypassing Director?

This should be formalized before relying on Hermes as an operator in the platform.

## Recommended implementation plan

### Phase 1 — Stabilize canonical contracts

1. Add a shared agent contract module, e.g. `backend/app/agents/contracts.py`:
   - canonical agent IDs;
   - communication types;
   - task stages;
   - approval categories;
   - P0/P1/P2/P3 mapping;
   - structured message schemas.
2. Make `agent_registry.py`, `agent_interactions.py`, `ai_marketer.py`, and frontend board definitions import/use the same canonical map.
3. Fix prompt seed default path to `GLAME_AI_Agent_System_Prompts_v1_2.md`.
4. Add tests for prompt parser: exactly 8 canonical agents are extracted and seeded.

### Phase 2 — Make Director the orchestration spine

1. Add a Director orchestration service:
   - `create_plan_from_user_request()`
   - `assign_subtasks()`
   - `collect_agent_reports()`
   - `evaluate_readiness()`
   - `request_human_approval()`
   - `finalize_report()`
2. Board tasks should generally be created by or through Director, unless they are direct board/manual tasks.
3. Add a visible audit chain: user request → Director plan → specialist tasks → specialist reports → Director synthesis → approval/final action.

### Phase 3 — Normalize task lifecycle and board stages

1. Keep technical statuses internally, but add business `stage` field or derived stage:
   - Briefed
   - Planned
   - In Production
   - Needs Approval
   - Approved
   - Scheduled
   - Published/Sent/Launched
   - Measured
   - Done
2. Add board-specific stage mappings for content, CRM, partnership, traffic, product, analytics.
3. Add validation that tasks cannot move to `Done/completed` without `output_data`, `result_summary`, or verified external artifact.

### Phase 4 — Formalize approval policy

1. Add `approval_policy` to tasks or requirements:
   - `required: bool`
   - `reason/category`
   - `approver_role`
   - `risk_level`
   - `blocking: bool`
2. Auto-classify high-risk categories from docs.
3. Prevent mass-mailing, discount/public positioning/push execution until approved.
4. Make Approval Queue use this policy, not only status.

### Phase 5 — Build real specialist workers

Create or normalize canonical executor classes:

- `BrandMediaAgent`
- `PersonalMediaAgent`
- `CRMAgent`
- `PRPartnershipsAgent`
- `TrafficGrowthAgent`
- `AnalyticsAgent`
- `AssortmentAgent`

Each should implement:

- accepted task types;
- required input schema;
- output/report schema;
- live data dependencies;
- memory reads/writes;
- escalation triggers.

Legacy classes can remain as implementation helpers, but public routing should use canonical agent IDs.

### Phase 6 — Per-agent memory and learning loop

1. Define `agent_memory_entries` or extend existing memory models.
2. Separate:
   - task dialog history;
   - reusable learnings;
   - performance facts;
   - strategy decisions;
   - approved brand/tone rules.
3. Add memory write gates: only write durable memory from verified performance results or explicit user/Director decision.

### Phase 7 — Hermes/operator integration

Recommended operating rule for this Hermes assistant:

1. Hermes should not bypass the Director for strategic/cross-agent tasks.
2. For platform-agent work, Hermes should create or update tasks through API as `source_agent = "hermes-agent"` only when it is acting as an external operator.
3. For multi-agent marketing work, Hermes should first create/consult a Director task, then let Director assign specialist tasks.
4. Hermes may use direct specialist board chat only for narrow implementation/debug questions.
5. Hermes must not mark tasks completed unless it verifies `output_data`, logs, linked artifact, sent campaign, segment, or external result.
6. Hermes should write clear audit logs into task chat when it performs out-of-band repo/API work.

## Immediate fixes recommended next

1. Fix `/api/agent-system-prompts/seed-defaults` default docs path.
2. Add a test for v1_2 prompt seeding.
3. Add canonical contract/schema module for agent messages.
4. Update `ensure_board_task` and `create_agent_task` to accept/store structured communication fields, even if initially stored in `task_context`.
5. Add explicit `approval_policy`/`requires_approval` enforcement.
6. Add a Director orchestration endpoint for turning one request into multiple specialist task assignments.
7. Make board frontend use `GET /api/ai-marketer/boards/{board_id}` consistently instead of duplicating filtering logic in each page.
8. Add `Hermes operator protocol` doc so this assistant knows exactly how to interact with platform agents.

## Practical current interaction mode for Hermes

Until the orchestration layer is finished, the safest interaction pattern is:

1. Inspect current tasks through `GET /api/agent-interactions/tasks` or board state through `GET /api/ai-marketer/boards/{board_id}`.
2. For broad marketing/product decisions: create or use a `director-agent` task and write in its task chat.
3. For narrow specialist execution: use the relevant board task chat:
   - content → `brand-media-agent` / `personal-media-agent`
   - CRM → `crm-agent`
   - product/stock → `assortment-agent`
   - analytics → `analytics-agent`
   - traffic → `traffic-growth-agent`
   - partnerships → `pr-partnerships-agent`
4. Always preserve task status truth:
   - no `completed` without verified result;
   - if waiting on Elena/user approval, status should remain `pending_approval`;
   - if actively being worked, `processing`;
   - if ready but not active, `approved` or `queued` depending on queue semantics.
5. Log what Hermes did in the task chat/audit trail, especially if the change was made in repo/backend rather than by the platform agent itself.

## Bottom line

The platform already has the important foundation: canonical registry, prompt docs/parser, task model, logs, approvals, board pages, chat endpoint and some live data context. The missing layer is not another UI page; it is a stricter operating contract: structured inter-agent messages, Director-led orchestration, normalized approvals/statuses, canonical specialist workers and explicit Hermes/operator rules.
